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
    assert len(catalog.rules) >= 4
    assert catalog.content_hash != ""
    assert "protocol.google_find_hub" in catalog.rules
    assert "protocol.apple_find_my" in catalog.rules
    assert "brand.xiaomi_tag" in catalog.rules
    assert "protocol.apple_find_my_fd44" in catalog.rules

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
