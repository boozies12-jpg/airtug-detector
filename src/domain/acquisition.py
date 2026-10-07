import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .models import NormalizedBleRecord, ClassificationResult, CandidateGroup
from .normalizer import normalize_ble_data
from .classifier import ClassifierEngine
from .signal_processor import SignalProcessor
from .session_manager import SessionManager

class AcquisitionOrchestrator:
    """
    Acquisition orchestrator managing continuous Bleak scanner,
    synthetic Demo feed, signal processing, classification, and session storage.
    """
    def __init__(
        self,
        classifier: ClassifierEngine,
        signal_processor: SignalProcessor,
        session_manager: SessionManager,
        event_callback: Optional[Callable[[str, Any], None]] = None
    ):
        self.classifier = classifier
        self.signal_processor = signal_processor
        self.session_manager = session_manager
        self.event_callback = event_callback

        self.is_scanning = False
        self.is_demo = False
        self.selected_target_address: Optional[str] = None
        self.pinned_addresses: List[str] = []
        self.found_addresses: Dict[str, Dict[str, Any]] = {}

        # Aggregated state per address:
        # address -> {"record": NormalizedBleRecord, "classification": ClassificationResult}
        self.devices: Dict[str, Dict[str, Any]] = {}

        self._scanner: Optional[BleakScanner] = None
        self._demo_task: Optional[asyncio.Task] = None
        self._scan_start_mono: float = 0.0

    async def start_scan(self, session_name: str = "", demo_mode: bool = False):
        if self.is_scanning:
            return

        self.is_demo = demo_mode
        self.is_scanning = True
        self._scan_start_mono = time.monotonic()
        self.signal_processor.clear()
        self.devices.clear()

        # Start persistent session
        cat = self.classifier.catalog
        self.session_manager.start_session(
            session_name=session_name,
            rule_catalog_version=cat.version,
            rule_catalog_hash=cat.content_hash
        )

        if self.is_demo:
            self._demo_task = asyncio.create_task(self._run_demo_feed())
        else:
            try:
                self._scanner = BleakScanner(
                    detection_callback=self._handle_bleak_detection,
                    scanning_mode="active"
                )
                await self._scanner.start()
            except Exception as e:
                self.is_scanning = False
                if self.event_callback:
                    self.event_callback("scanner_error", {"error": str(e)})
                raise e

        if self.event_callback:
            self.event_callback("scan_started", {
                "session_id": self.session_manager.current_session_id,
                "is_demo": self.is_demo
            })

    async def stop_scan(self):
        if not self.is_scanning:
            return

        self.is_scanning = False
        if self._demo_task:
            self._demo_task.cancel()
            self._demo_task = None

        if self._scanner:
            try:
                await self._scanner.stop()
            except Exception:
                pass
            self._scanner = None

        self.session_manager.close_session()

        if self.event_callback:
            self.event_callback("scan_stopped", {})

    def select_target(self, address: Optional[str]):
        self.selected_target_address = address
        if self.event_callback:
            self.event_callback("target_selected", {"address": address})

    def toggle_pin(self, address: str):
        if address in self.pinned_addresses:
            self.pinned_addresses.remove(address)
        else:
            self.pinned_addresses.append(address)
        if self.event_callback:
            self.event_callback("pinned_updated", {"pinned": self.pinned_addresses})

    def mark_found(self, address: str, is_found: bool, notes: Optional[str] = None):
        if is_found:
            self.found_addresses[address] = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "notes": notes
            }
        else:
            self.found_addresses.pop(address, None)
        self.session_manager.record_found_action(address, is_found, notes)
        if self.event_callback:
            self.event_callback("found_updated", {"address": address, "is_found": is_found, "notes": notes})

    def _handle_bleak_detection(self, device: BLEDevice, adv_data: AdvertisementData):
        mono_s = time.monotonic()
        now_utc = datetime.now(timezone.utc).isoformat()

        # Merge with previously observed device state (e.g. delayed scan response)
        prev = self.devices.get(device.address)
        prev_name = prev["record"].local_name if prev else None
        prev_mfg = prev["record"].manufacturer_data if prev else {}
        prev_svc = prev["record"].service_data if prev else {}
        prev_uuids = prev["record"].service_uuids if prev else []

        new_mfg = dict(prev_mfg)
        if adv_data.manufacturer_data:
            for cid, b in adv_data.manufacturer_data.items():
                cid_hex = f"{cid:04x}"
                new_mfg[cid_hex] = b.hex() if isinstance(b, bytes) else bytes(b).hex()

        new_svc = dict(prev_svc)
        if adv_data.service_data:
            for suuid, b in adv_data.service_data.items():
                norm_u = suuid.lower().replace("-", "")
                if len(norm_u) == 32 and norm_u.startswith("0000") and norm_u.endswith("00001000800000805f9b34fb"):
                    norm_u = norm_u[4:8]
                new_svc[norm_u] = b.hex() if isinstance(b, bytes) else bytes(b).hex()

        new_uuids = list(set(prev_uuids + [u.lower() for u in (adv_data.service_uuids or [])]))
        current_name = adv_data.local_name or device.name or prev_name

        record = normalize_ble_data(
            address=device.address,
            rssi=adv_data.rssi,
            local_name=current_name,
            manufacturer_data_raw=new_mfg,
            service_data_raw=new_svc,
            service_uuids_raw=new_uuids,
            tx_power=adv_data.tx_power,
            now_utc=now_utc,
            mono_s=mono_s
        )

        # Update signal processor
        if adv_data.rssi is not None:
            self.signal_processor.add_observation(record.address, record.rssi, mono_s)

        # Run classification
        classification = self.classifier.classify(record)

        self.devices[record.address] = {
            "record": record,
            "classification": classification,
            "last_seen_mono": mono_s
        }

        # Log observation continuously
        self.session_manager.log_observation(record, classification)

        # Dispatch event
        if self.event_callback:
            summary = self.signal_processor.get_summary(record.address, mono_s)
            self.event_callback("device_updated", {
                "address": record.address,
                "local_name": record.local_name,
                "classification": classification.model_dump(),
                "signal": summary.model_dump(),
                "is_pinned": record.address in self.pinned_addresses,
                "is_found": record.address in self.found_addresses,
                "found_notes": self.found_addresses.get(record.address, {}).get("notes")
            })

    async def _run_demo_feed(self):
        """
        High-fidelity Demo feed reproducing exact captured frames from Product Spec:
          - Specimen 1: Xiaomi Tag (frames 1-5 from Spec Section 6)
          - Specimen 2: Verbatim My Finder (frames 1-5 from Spec Section 9)
          - Specimen 3: Apple AirTag setup sample (frames 1-5 from Spec Section 8)
          - Unrelated devices (Apple proximity pairing, Microsoft beacons)
        """
        specimens = [
            # 1. Xiaomi Tag: FEAA payload + delayed scan response
            {
                "address": "C2:9F:5B:4C:F3:69",
                "local_name": "Xiaomi Tag",
                "service_data": {"feaa": "409870c3dbac216705d74478fe934f363e60d0fee206"},
                "rssi_base": -38
            },
            # 2. Verbatim My Finder: FD44 21-byte provisional rule
            {
                "address": "E4:C1:38:BA:C5:D5",
                "local_name": "My Finder",
                "service_data": {"fd44": "f3253682d8a77c3401000000000000000000000001"},
                "rssi_base": -52
            },
            # 3. Apple AirTag Setup Specimen: 004C manufacturer payload type 07
            {
                "address": "D7:1F:26:3B:CF:67",
                "local_name": None,
                "manufacturer_data": {"004c": "07190912561000000150cf02a018fc4f6d8d3da635d3e7177b3f4a"},
                "rssi_base": -65
            },
            # 4. Apple Find My Type 12 Offline Finding Broadcast (synthetic fixture)
            {
                "address": "F1:22:33:44:55:66",
                "local_name": None,
                "manufacturer_data": {"004c": "1219" + "aabbccddeeff00112233445566778899aabbccddeeff00"},
                "rssi_base": -44
            },
            # 5. Background non-candidate device (Microsoft beacon)
            {
                "address": "AA:BB:CC:DD:EE:01",
                "local_name": "Office Surface Laptop",
                "manufacturer_data": {"0006": "010f20227065d4b26d11d444d6cd782d0ed31f243757edb8791de6"},
                "rssi_base": -72
            }
        ]

        t_idx = 0
        while self.is_scanning:
            await asyncio.sleep(0.4)
            t_idx += 1
            mono_s = time.monotonic()
            now_utc = datetime.now(timezone.utc).isoformat()

            for spec in specimens:
                # Add small realistic RSSI fluctuation
                fluctuation = ((t_idx * 7 + hash(spec["address"])) % 9) - 4
                cur_rssi = spec["rssi_base"] + fluctuation

                record = normalize_ble_data(
                    address=spec["address"],
                    rssi=cur_rssi,
                    local_name=spec["local_name"],
                    manufacturer_data_raw=spec.get("manufacturer_data"),
                    service_data_raw=spec.get("service_data"),
                    now_utc=now_utc,
                    mono_s=mono_s
                )

                self.signal_processor.add_observation(record.address, record.rssi, mono_s)
                classification = self.classifier.classify(record)

                self.devices[record.address] = {
                    "record": record,
                    "classification": classification,
                    "last_seen_mono": mono_s
                }

                self.session_manager.log_observation(record, classification)

                if self.event_callback:
                    summary = self.signal_processor.get_summary(record.address, mono_s)
                    self.event_callback("device_updated", {
                        "address": record.address,
                        "local_name": record.local_name,
                        "classification": classification.model_dump(),
                        "signal": summary.model_dump(),
                        "is_pinned": record.address in self.pinned_addresses,
                        "is_found": record.address in self.found_addresses,
                        "found_notes": self.found_addresses.get(record.address, {}).get("notes")
                    })
