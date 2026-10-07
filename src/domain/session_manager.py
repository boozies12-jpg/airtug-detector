import os
import json
import csv
import io
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from .models import NormalizedBleRecord, CheckpointRecord, ClassificationResult

def sanitize_csv_field(val: Any) -> str:
    """Protect against spreadsheet formula injection (leading =, +, -, @, tab, cr)."""
    if val is None:
        return ""
    s = str(val).strip()
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s

class SessionManager:
    """
    Session persistence and export manager adhering to Section 11 of the specification.
    Continuous append-only logging of observations and audit events.
    """
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.sessions_dir = os.path.join(data_dir, "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)

        self.current_session_id: Optional[str] = None
        self.session_metadata: Dict[str, Any] = {}
        self.observations_file = None
        self.events_file = None

        # In-memory tracking for fast queries
        self.checkpoints: List[CheckpointRecord] = []
        self.operator_actions: List[Dict[str, Any]] = []

    def start_session(self, session_name: str, rule_catalog_version: str, rule_catalog_hash: str) -> str:
        if self.current_session_id:
            self.close_session()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.current_session_id = f"session_{timestamp}"
        session_folder = os.path.join(self.sessions_dir, self.current_session_id)
        os.makedirs(session_folder, exist_ok=True)

        self.session_metadata = {
            "session_id": self.current_session_id,
            "session_name": session_name or f"Search {timestamp}",
            "start_time_utc": datetime.now(timezone.utc).isoformat(),
            "rule_catalog_version": rule_catalog_version,
            "rule_catalog_hash": rule_catalog_hash,
            "status": "active"
        }

        # Write initial metadata
        with open(os.path.join(session_folder, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(self.session_metadata, f, indent=2)

        self.observations_file = open(os.path.join(session_folder, "observations.jsonl"), "a", encoding="utf-8")
        self.events_file = open(os.path.join(session_folder, "events.jsonl"), "a", encoding="utf-8")
        self.log_event("session_started", self.session_metadata)
        return self.current_session_id

    def log_observation(self, record: NormalizedBleRecord, classification: Optional[ClassificationResult] = None):
        if not self.observations_file:
            return
        entry = {
            "timestamp_utc": record.reception_timestamp_utc,
            "mono_s": record.monotonic_timestamp_s,
            "address": record.address,
            "rssi": record.rssi,
            "local_name": record.local_name,
            "service_uuids": record.service_uuids,
            "service_data": record.service_data,
            "manufacturer_data": record.manufacturer_data,
            "classification": classification.model_dump() if classification else None
        }
        self.observations_file.write(json.dumps(entry) + "\n")
        self.observations_file.flush()

    def log_event(self, event_type: str, details: Dict[str, Any]):
        if not self.events_file:
            return
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details
        }
        self.events_file.write(json.dumps(entry) + "\n")
        self.events_file.flush()

    def record_found_action(self, address: str, is_found: bool, notes: Optional[str] = None):
        action = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "address": address,
            "is_found": is_found,
            "notes": notes
        }
        self.operator_actions.append(action)
        self.log_event("operator_marked_found", action)

    def add_checkpoint(self, checkpoint: CheckpointRecord):
        self.checkpoints.append(checkpoint)
        self.log_event("checkpoint_recorded", checkpoint.model_dump())

    def close_session(self):
        if not self.current_session_id:
            return
        session_folder = os.path.join(self.sessions_dir, self.current_session_id)
        self.session_metadata["end_time_utc"] = datetime.now(timezone.utc).isoformat()
        self.session_metadata["status"] = "closed"

        with open(os.path.join(session_folder, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(self.session_metadata, f, indent=2)

        if self.observations_file:
            self.observations_file.close()
            self.observations_file = None
        if self.events_file:
            self.events_file.close()
            self.events_file = None

        self.current_session_id = None
        self.checkpoints.clear()
        self.operator_actions.clear()

    def list_sessions(self) -> List[Dict[str, Any]]:
        res = []
        if not os.path.exists(self.sessions_dir):
            return res
        for s_id in sorted(os.listdir(self.sessions_dir), reverse=True):
            p = os.path.join(self.sessions_dir, s_id, "metadata.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    res.append(json.load(f))
        return res

    def export_csv(self, session_id: str) -> str:
        s_folder = os.path.join(self.sessions_dir, session_id)
        obs_path = os.path.join(s_folder, "observations.jsonl")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Timestamp UTC",
            "Address",
            "RSSI",
            "Local Name",
            "Candidate Group",
            "Protocol Family",
            "Brand",
            "Model",
            "Status Text"
        ])

        if os.path.exists(obs_path):
            with open(obs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    cls = row.get("classification") or {}
                    writer.writerow([
                        sanitize_csv_field(row.get("timestamp_utc")),
                        sanitize_csv_field(row.get("address")),
                        sanitize_csv_field(row.get("rssi")),
                        sanitize_csv_field(row.get("local_name")),
                        sanitize_csv_field(cls.get("candidate_group")),
                        sanitize_csv_field(cls.get("protocol_family")),
                        sanitize_csv_field(cls.get("brand")),
                        sanitize_csv_field(cls.get("model")),
                        sanitize_csv_field(cls.get("status_text"))
                    ])
        return output.getvalue()
