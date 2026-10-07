import os
import json
import pytest
from src.domain.classifier import RuleCatalog, ClassifierEngine
from src.domain.normalizer import normalize_ble_data, normalize_company_id, normalize_uuid, parse_apple_tlv_records

RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules")
FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "classification", "fixtures.json")

def test_normalization_primitives():
    # Test 16-bit UUID normalization
    assert normalize_uuid("feaa") == "feaa"
    assert normalize_uuid("0xfeaa") == "feaa"
    assert normalize_uuid("0000feaa-0000-1000-8000-00805f9b34fb") == "feaa"

    # Test company ID normalization
    assert normalize_company_id(76) == "004c"
    assert normalize_company_id("0x004c") == "004c"
    assert normalize_company_id("4c") == "004c"

    # Test Apple TLV record parser bounds checking
    # 0x12 (type), 0x02 (length), 0xAA, 0xBB -> valid
    # 0x07 (type), 0x10 (length 16) but only 2 bytes available -> truncated, should be safely ignored
    malformed = bytes.fromhex("1202aabb0710ffff")
    records = parse_apple_tlv_records(malformed)
    assert len(records) == 1
    assert records[0].record_type == 0x12
    assert records[0].length == 2
    assert records[0].body_hex == "aabb"

def test_rule_catalog_loading_and_hash():
    catalog = RuleCatalog(RULES_DIR)
    catalog.load()
    assert len(catalog.rules) >= 5
    assert catalog.content_hash != ""
    assert "protocol.google_find_hub" in catalog.rules
    assert "protocol.apple_find_my" in catalog.rules
    assert "brand.xiaomi_tag" in catalog.rules
    assert "protocol.apple_find_my_fd44" in catalog.rules
    assert "protocol.samsung_smarttag" in catalog.rules
    assert "protocol.samsung_smarttag_fd5a" in catalog.rules

def test_samsung_smarttag_classification():
    catalog = RuleCatalog(RULES_DIR)
    catalog.load()
    classifier = ClassifierEngine(catalog)

    # 1. Exact 24-byte manufacturer data payload with 0x0075 and 4204 prefix from samsong.pcapng
    record_24b = normalize_ble_data(
        address="D0:03:DF:BE:F0:8D",
        rssi=-65,
        manufacturer_data_raw={
            "0075": "4204018060d003dfbef08dd203dfbef08c014cc6fcf1d4c3"
        }
    )
    res_24b = classifier.classify(record_24b)
    assert res_24b.is_candidate is True
    assert res_24b.candidate_group.value == "protocol_match"
    assert res_24b.protocol_family == "Samsung SmartThings Find"
    assert res_24b.brand == "Samsung"
    assert res_24b.model == "Galaxy SmartTag"
    assert "protocol.samsung_smarttag" in res_24b.matched_rule_ids

    # 2. 20-byte Service UUID FD5A broadcast from samsong.pcapng
    record_fd5a = normalize_ble_data(
        address="68:82:53:B7:3C:5D",
        rssi=-26,
        service_data_raw={
            "fd5a": "12245a038612137f87e9bfbab70000009e8e759c"
        },
        service_uuids_raw=["fd5a"]
    )
    res_fd5a = classifier.classify(record_fd5a)
    assert res_fd5a.is_candidate is True
    assert res_fd5a.candidate_group.value == "protocol_match"
    assert res_fd5a.protocol_family == "Samsung SmartThings Find"
    assert res_fd5a.brand == "Samsung"
    assert res_fd5a.model == "Galaxy SmartTag"
    assert "protocol.samsung_smarttag_fd5a" in res_fd5a.matched_rule_ids

def test_fixtures_classification():
    catalog = RuleCatalog(RULES_DIR)
    catalog.load()
    classifier = ClassifierEngine(catalog)

    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for fixture in data["fixtures"]:
        rec_data = fixture["record"]
        exp = fixture["expected"]

        record = normalize_ble_data(
            address=rec_data["address"],
            rssi=rec_data.get("rssi"),
            local_name=rec_data.get("local_name"),
            manufacturer_data_raw=rec_data.get("manufacturer_data"),
            service_data_raw=rec_data.get("service_data")
        )

        res = classifier.classify(record)

        assert res.is_candidate == exp["is_candidate"], f"Failed is_candidate for {fixture['id']}"
        if exp["is_candidate"]:
            assert res.candidate_group.value == exp["candidate_group"], f"Failed candidate_group for {fixture['id']}"
            assert res.protocol_family == exp["protocol_family"], f"Failed protocol_family for {fixture['id']}"
            assert res.brand == exp["brand"], f"Failed brand for {fixture['id']}"
            assert res.model == exp["model"], f"Failed model for {fixture['id']}"
            assert set(res.matched_rule_ids) == set(exp["matched_rules"]), f"Failed matched_rules for {fixture['id']}"
        else:
            assert len(res.matched_rule_ids) == 0
