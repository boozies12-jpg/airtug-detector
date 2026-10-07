import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .models import NormalizedBleRecord, ParsedAppleRecord

def normalize_company_id(raw_id: Any) -> str:
    """Normalize company ID to 4-character lowercase hex string without 0x prefix."""
    if isinstance(raw_id, int):
        return f"{raw_id:04x}"
    if isinstance(raw_id, str):
        s = raw_id.strip().lower()
        if s.startswith("0x"):
            s = s[2:]
        return s.zfill(4)
    raise ValueError(f"Unsupported company ID type: {type(raw_id)}")

def normalize_uuid(uuid_str: str) -> str:
    """
    Normalize 16-bit, 32-bit, or 128-bit Bluetooth UUIDs.
    Returns 4-char lowercase hex for 16-bit UUIDs, or clean lowercase string for others.
    """
    s = str(uuid_str).strip().lower()
    # Bluetooth Base UUID: 0000xxxx-0000-1000-8000-00805f9b34fb
    if len(s) == 36 and s.startswith("0000") and s.endswith("-0000-1000-8000-00805f9b34fb"):
        return s[4:8]
    if len(s) == 4 or len(s) == 6 or len(s) == 8:
        if s.startswith("0x"):
            s = s[2:]
        return s[-4:].zfill(4)
    return s.replace("-", "")

def parse_apple_tlv_records(payload_bytes: bytes) -> List[ParsedAppleRecord]:
    """
    Parses Apple manufacturer payload into TLV records.
    Apple payload after 0x004C starts with:
      type (1 byte), length (1 byte), body (length bytes).
    Strict bounds checking ensures malformed/truncated records are safely ignored
    while preserving complete records.
    """
    records: List[ParsedAppleRecord] = []
    idx = 0
    total_len = len(payload_bytes)
    while idx + 2 <= total_len:
        rec_type = payload_bytes[idx]
        rec_len = payload_bytes[idx + 1]
        body_start = idx + 2
        body_end = body_start + rec_len
        if body_end > total_len:
            # Truncated record; stop parsing
            break
        records.append(ParsedAppleRecord(
            record_type=rec_type,
            length=rec_len,
            body_hex=payload_bytes[body_start:body_end].hex()
        ))
        idx = body_end
    return records

def normalize_ble_data(
    address: str,
    rssi: Optional[int] = None,
    local_name: Optional[str] = None,
    manufacturer_data_raw: Optional[Dict[Any, Any]] = None,
    service_data_raw: Optional[Dict[str, Any]] = None,
    service_uuids_raw: Optional[List[str]] = None,
    tx_power: Optional[int] = None,
    hci_metadata: Optional[Dict[str, Any]] = None,
    now_utc: Optional[str] = None,
    mono_s: Optional[float] = None
) -> NormalizedBleRecord:
    """Ingestion boundary normalizer adhering to Section 4 of the specification."""
    norm_mfg: Dict[str, str] = {}
    parsed_apple: List[ParsedAppleRecord] = []

    if manufacturer_data_raw:
        for comp_id_raw, data_bytes in manufacturer_data_raw.items():
            cid = normalize_company_id(comp_id_raw)
            if isinstance(data_bytes, str):
                b = bytes.fromhex(data_bytes)
            else:
                b = bytes(data_bytes)
            norm_mfg[cid] = b.hex()
            if cid == "004c":
                parsed_apple.extend(parse_apple_tlv_records(b))

    norm_svc: Dict[str, str] = {}
    if service_data_raw:
        for uuid_raw, data_bytes in service_data_raw.items():
            suuid = normalize_uuid(uuid_raw)
            if isinstance(data_bytes, str):
                b = bytes.fromhex(data_bytes)
            else:
                b = bytes(data_bytes)
            norm_svc[suuid] = b.hex()

    norm_uuids: List[str] = []
    if service_uuids_raw:
        for u in service_uuids_raw:
            norm_uuids.append(normalize_uuid(u))

    safe_tx_power = None
    if tx_power is not None and tx_power != 127:
        safe_tx_power = tx_power

    return NormalizedBleRecord(
        address=address.upper(),
        rssi=rssi,
        local_name=local_name.strip() if local_name else None,
        manufacturer_data=norm_mfg,
        service_data=norm_svc,
        service_uuids=norm_uuids,
        parsed_apple_records=parsed_apple,
        tx_power=safe_tx_power,
        reception_timestamp_utc=now_utc or datetime.now(timezone.utc).isoformat(),
        monotonic_timestamp_s=mono_s if mono_s is not None else time.monotonic(),
        raw_hci_metadata=hci_metadata or {}
    )
