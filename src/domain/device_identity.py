"""Offline identity hints; protocol identifiers are not physical-brand proof."""
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / 'catalog'
COMPANIES = json.loads((CATALOG / 'company_identifiers.json').read_text(encoding='utf-8'))
OUI = json.loads((CATALOG / 'oui_ma_l.json').read_text(encoding='utf-8'))
PROFILES = json.loads((CATALOG / 'tracker_profiles.json').read_text(encoding='utf-8'))


def identity_hints(record):
    address_type = record.raw_sdr_metadata.get('address_type', 'unknown')
    prefix = record.address.replace(':', '').upper()[:6]
    registrant = OUI.get(prefix) if address_type == 'public' else None
    return dict(address_type=address_type, oui_registrant=registrant,
                oui_note='IEEE MA-L registrant; not verified product manufacturer' if registrant else
                'No OUI attribution: random/unknown address type or prefix absent from MA-L snapshot',
                company_names=[COMPANIES.get(key, 'Unknown company') + ' (0x' + key.upper() + ')'
                               for key in sorted(record.manufacturer_data)],
                company_note='Advertised Bluetooth company identifiers; not proof of physical manufacturer',
                mfg_keys=sorted(record.manufacturer_data), service_data_keys=sorted(record.service_data))
