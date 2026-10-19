import os
import asyncio
import time
from typing import List, Dict, Any, Optional, Literal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, PlainTextResponse, FileResponse
from pydantic import BaseModel, Field, SecretStr
from urllib.parse import urlsplit

from ..domain.classifier import RuleCatalog, ClassifierEngine
from ..domain.signal_processor import SignalProcessor
from ..domain.session_manager import SessionManager
from ..domain.acquisition import AcquisitionOrchestrator
from ..domain.models import CheckpointRecord, CandidateGroup
from ..domain.wifi_control import WifiControl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_DIR = os.path.join(BASE_DIR, "rules")
DATA_DIR = os.path.join(BASE_DIR, "data")
DIST_DIR = os.path.join(BASE_DIR, "dist")
wifi = WifiControl(os.environ['BLE_WIFI_INTERFACE'], os.path.join(DATA_DIR, 'wifi-control.json')) if os.environ.get('BLE_WIFI_INTERFACE') else None

# Initialize Domain Core
catalog = RuleCatalog(RULES_DIR)
catalog.load()

classifier = ClassifierEngine(catalog)
signal_processor = SignalProcessor(bucket_duration_s=0.25)
session_manager = SessionManager(DATA_DIR)

app = FastAPI(title="Windows BLE Tracker Search API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Background broadcast hook
loop = None

def on_acquisition_event(event_type: str, data: Any):
    global loop
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({"event": event_type, "data": data}),
            loop
        )

orchestrator = AcquisitionOrchestrator(
    classifier=classifier,
    signal_processor=signal_processor,
    session_manager=session_manager,
    event_callback=on_acquisition_event
)

@app.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()

# API Endpoints
class WifiConnectRequest(BaseModel):
    ssid: str = Field(default='', max_length=128)
    password: SecretStr = SecretStr('')
    saved_workshop: bool = False


def require_local_wifi_request(request: Request):
    if wifi is None:
        raise HTTPException(404, 'Wi-Fi control is available only on the configured board.')
    origin = request.headers.get('origin')
    if (origin and urlsplit(origin).netloc != request.headers.get('host')) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Open Wi-Fi settings directly on the board interface.')


@app.get('/api/network')
async def network_status():
    if wifi is None:
        return {'enabled': False}
    try:
        return await wifi.status()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.post('/api/network/connect')
async def network_connect(body: WifiConnectRequest, request: Request):
    require_local_wifi_request(request)
    try:
        return await wifi.connect(body.ssid, body.password.get_secret_value(), body.saved_workshop)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.post('/api/network/confirm')
async def network_confirm(request: Request):
    require_local_wifi_request(request)
    try:
        return await wifi.confirm()
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.post('/api/network/field')
async def network_field(request: Request):
    require_local_wifi_request(request)
    try:
        return await wifi.field()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


class StartScanRequest(BaseModel):
    session_name: Optional[str] = ""
    demo_mode: bool = False
    source: Literal['computer', 'sdr'] = 'computer'
    sdr_uri: str = 'ip:192.168.2.1'

scan_lock = asyncio.Lock()

@app.on_event('shutdown')
async def shutdown_event():
    await orchestrator.stop_scan()

@app.post("/api/scan/start")
async def start_scan(req: StartScanRequest):
    try:
        async with scan_lock:
            if orchestrator.is_scanning:
                raise HTTPException(status_code=409, detail='Stop the current scan before changing receivers')
            await orchestrator.start_scan(session_name=req.session_name or "", demo_mode=req.demo_mode,
                                          source=req.source, sdr_uri=req.sdr_uri)
        return {"status": "started", "session_id": session_manager.current_session_id, "demo_mode": req.demo_mode}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scan/stop")
async def stop_scan():
    async with scan_lock:
        await orchestrator.stop_scan()
    return {"status": "stopped"}

@app.get("/api/status")
async def get_status():
    mono_now = time.monotonic()
    target_summary = None
    if orchestrator.selected_target_address:
        target_summary = signal_processor.get_summary(orchestrator.selected_target_address, mono_now).model_dump()

    return {
        "is_scanning": orchestrator.is_scanning,
        "scan_elapsed_s": max(0, mono_now - orchestrator._scan_start_mono) if orchestrator._scan_start_mono else 0,
        "is_demo": orchestrator.is_demo,
        "capture_source": orchestrator.source,
        "signal_unit": signal_processor.signal_unit,
        "capture_health": orchestrator.capture_health,
        "scanner_error": orchestrator.last_error,
        "current_session_id": session_manager.current_session_id,
        "selected_target_address": orchestrator.selected_target_address,
        "selected_target_summary": target_summary,
        "pinned_addresses": orchestrator.pinned_addresses,
        "rule_catalog_version": catalog.version,
        "rule_catalog_hash": catalog.content_hash,
        "rule_count": len(catalog.rules)
    }

@app.get("/api/candidates")
async def get_candidates(compact: bool = False):
    mono_now = time.monotonic()
    candidates = []
    for addr, dev in orchestrator.devices.items():
        cls = dev["classification"]
        if cls.is_candidate:
            rec = dev["record"]
            summary = signal_processor.get_summary(addr, mono_now, include_history=not compact)
            candidates.append({
                "address": addr,
                "local_name": rec.local_name,
                "classification": cls.model_dump(),
                "signal": summary.model_dump(),
                "is_pinned": addr in orchestrator.pinned_addresses,
                "is_found": addr in orchestrator.found_addresses,
                "found_notes": orchestrator.found_addresses.get(addr, {}).get("notes")
            })
    return candidates

@app.get("/api/other-devices")
async def get_other_devices(compact: bool = False):
    mono_now = time.monotonic()
    others = []
    for addr, dev in orchestrator.devices.items():
        cls = dev["classification"]
        if not cls.is_candidate:
            rec = dev["record"]
            summary = signal_processor.get_summary(addr, mono_now, include_history=not compact)
            others.append({
                "address": addr,
                "local_name": rec.local_name,
                "classification": cls.model_dump(),
                "signal": summary.model_dump(),
                "is_pinned": addr in orchestrator.pinned_addresses,
                "is_found": addr in orchestrator.found_addresses,
                "found_notes": orchestrator.found_addresses.get(addr, {}).get("notes")
            })
    return others

class TargetSelectRequest(BaseModel):
    address: Optional[str] = None

@app.post("/api/target/select")
async def select_target(req: TargetSelectRequest):
    orchestrator.select_target(req.address)
    return {"status": "ok", "target": req.address}

class PinRequest(BaseModel):
    address: str

@app.post("/api/target/pin")
async def toggle_pin(req: PinRequest):
    orchestrator.toggle_pin(req.address)
    return {"status": "ok", "pinned": orchestrator.pinned_addresses}

class MarkFoundRequest(BaseModel):
    address: str
    is_found: bool
    notes: Optional[str] = None

@app.post("/api/target/found")
async def mark_found(req: MarkFoundRequest):
    orchestrator.mark_found(req.address, req.is_found, req.notes)
    return {"status": "ok", "is_found": req.is_found}

class CheckpointCreateRequest(BaseModel):
    position_label: str
    duration_s: float = 30.0
    notes: Optional[str] = None

@app.post("/api/checkpoint")
async def record_checkpoint(req: CheckpointCreateRequest):
    if not orchestrator.selected_target_address:
        raise HTTPException(status_code=400, detail="No candidate target selected for checkpoint measurement")

    addr = orchestrator.selected_target_address
    mono_now = time.monotonic()
    summary = signal_processor.get_summary(addr, mono_now)

    checkpoint = CheckpointRecord(
        source=orchestrator.source,
        signal_unit=signal_processor.signal_unit,
        checkpoint_id=f"cp_{int(time.time())}",
        position_label=req.position_label,
        target_address=addr,
        start_time_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - req.duration_s)),
        end_time_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        duration_s=req.duration_s,
        group_count=summary.summary_20s_count,
        coverage_s=summary.summary_20s_coverage_s,
        median_rssi=summary.summary_20s_median,
        min_rssi=None,
        max_rssi=None,
        status="Valid" if summary.summary_20s_count >= 3 and summary.summary_20s_coverage_s >= 10.0 else "Insufficient Data",
        notes=req.notes
    )

    session_manager.add_checkpoint(checkpoint)
    return checkpoint.model_dump()

@app.get("/api/sessions")
async def list_sessions():
    return session_manager.list_sessions()

@app.get("/api/sessions/{session_id}/export/csv")
async def export_session_csv(session_id: str):
    csv_content = session_manager.export_csv(session_id)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={session_id}_export.csv"}
    )

@app.get("/api/rules")
async def list_rules():
    return {
        "catalog_version": catalog.version,
        "catalog_hash": catalog.content_hash,
        "rules": [r.model_dump() for r in catalog.rules.values()]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keepalive / incoming messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# Serve built frontend static files if present
if os.path.exists(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(DIST_DIR, "index.html"))
