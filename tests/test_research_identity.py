from pathlib import Path
from src.domain.classifier import ClassifierEngine, RuleCatalog
from src.domain.normalizer import normalize_ble_data
from src.domain.device_identity import identity_hints, OUI


def classify(**kwargs):
    catalog = RuleCatalog(str(Path(__file__).resolve().parents[1] / 'rules'))
    catalog.load()
    return ClassifierEngine(catalog).classify(normalize_ble_data(address='AA:BB:CC:DD:EE:FF', **kwargs))


def test_tile_web_signature_and_negative_control():
    result = classify(service_data_raw={'feed': bytes.fromhex('0200010203')})
    assert result.is_candidate and result.protocol_family == 'Tile'
    assert result.evidence_level == 'web_reference' and not result.lab_verified
    assert result.model is None and result.brand is None
    assert not classify(service_data_raw={'feed': bytes.fromhex('0300010203')}).is_candidate
    assert not classify(service_uuids_raw=['feed'], service_data_raw={'1234': bytes.fromhex('0200010203')}).is_candidate


def test_chipolo_service_is_not_spot_model_identification():
    result = classify(service_uuids_raw=['fe33'])
    assert result.is_candidate and result.model is None and not result.lab_verified
    assert result.candidate_group == 'possible_tracker'


def test_google_payload_cannot_borrow_other_service_length_or_bytes():
    result = classify(service_data_raw={'feaa': b'\x00', '1234': b'\x40' + bytes(20)})
    assert 'protocol.google_find_hub' not in result.matched_rule_ids
    valid = classify(service_data_raw={'feaa': b'\x40' + bytes(20)})
    assert valid.protocol_family == 'Google Find Hub' and valid.model is None
    assert any(p['name'] == 'Google Pixel Tag (2026)' for p in valid.evidence['compatible_profiles'])


def test_company_id_alone_never_classifies_huawei_tag():
    result = classify(manufacturer_data_raw={0x027d: b'\x01\x02'})
    assert not result.is_candidate
    assert result.evidence['company_names']


def test_oui_only_for_confirmed_public_address():
    prefix = next(k for k in OUI if not int(k[:2], 16) & 3)
    address = ':'.join([prefix[:2], prefix[2:4], prefix[4:], '11', '22', '33'])
    record = normalize_ble_data(address=address)
    assert identity_hints(record)['oui_registrant'] is None
    record.raw_sdr_metadata = {'address_type': 'random_static'}
    assert identity_hints(record)['oui_registrant'] is None
    record.raw_sdr_metadata = {'address_type': 'public'}
    assert identity_hints(record)['oui_registrant'] == OUI[prefix]
