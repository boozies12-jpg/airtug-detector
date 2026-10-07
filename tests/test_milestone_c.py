import os
import shutil
import tempfile
import pytest
from src.domain.session_manager import SessionManager, sanitize_csv_field
from src.domain.normalizer import normalize_ble_data
from src.domain.models import CheckpointRecord, ClassificationResult, CandidateGroup

def test_csv_sanitization_formula_injection():
    assert sanitize_csv_field("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert sanitize_csv_field("+12345") == "'+12345"
    assert sanitize_csv_field("-danger") == "'-danger"
    assert sanitize_csv_field("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_field("Safe Name 123") == "Safe Name 123"

def test_session_manager_persistence_and_export():
    tmp_dir = tempfile.mkdtemp()
    try:
        sm = SessionManager(tmp_dir)
        session_id = sm.start_session("Test Search", "1.0.0", "hash123")
        assert session_id is not None

        # Log observation
        rec = normalize_ble_data(
            address="C2:9F:5B:4C:F3:69",
            rssi=-35,
            local_name="Xiaomi Tag",
            service_data_raw={"feaa": "409870c3dbac216705d74478fe934f363e60d0fee206"}
        )
        cls = ClassificationResult(
            is_candidate=True,
            candidate_group=CandidateGroup.PROTOCOL_MATCH,
            protocol_family="Google Find Hub",
            brand="Xiaomi",
            model="Xiaomi Tag",
            status_text="Test match"
        )
        sm.log_observation(rec, cls)

        # Mark found
        sm.record_found_action("C2:9F:5B:4C:F3:69", True, notes="In zipper pocket")

        # Checkpoint
        cp = CheckpointRecord(
            checkpoint_id="cp1",
            position_label="Luggage Tag A",
            target_address="C2:9F:5B:4C:F3:69",
            start_time_utc="2026-10-06T10:00:00Z",
            end_time_utc="2026-10-06T10:00:30Z",
            duration_s=30.0,
            group_count=10,
            coverage_s=25.0,
            median_rssi=-35.0,
            status="Valid",
            notes="Strong signal"
        )
        sm.add_checkpoint(cp)
        sm.close_session()

        # Export CSV
        csv_out = sm.export_csv(session_id)
        assert "Timestamp UTC" in csv_out
        assert "C2:9F:5B:4C:F3:69" in csv_out
        assert "Xiaomi Tag" in csv_out
        assert "Google Find Hub" in csv_out

    finally:
        shutil.rmtree(tmp_dir)
