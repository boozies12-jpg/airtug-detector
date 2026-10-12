"""Materialize reviewed web-reference rules, never mark them as lab verified."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / 'rules'
for path in RULES.rglob('*.json'):
    if path.name == 'schema.json':
        continue
    data = json.loads(path.read_text(encoding='utf-8'))
    data.setdefault('verification', {'level': 'web_reference', 'reviewed': '2026-10-12',
                            'note': 'Not lab verified. Legacy maturity is not a laboratory certification.'})
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

base = 'https://github.com/seemoo-lab/AirGuard/blob/main/app/src/main/java/de/seemoo/at_tracking_detection/database/models/device/types/'
for name, family, service, prefix, source in [('tile_web', 'Tile', 'feed', '0200', 'Tile.kt'),
                                             ('chipolo_web', 'Chipolo', 'fe33', None, 'Chipolo.kt')]:
    conditions = [{'service_uuid': service}]
    if prefix:
        conditions.append({'hex_prefix': {'prefix': prefix, 'source': 'service_data'}})
    data = dict(rule_id='experimental.' + name, revision=1, schema_version='1.0.0', enabled=True,
        maturity='experimental', kind='protocol', description=f'{family} advertised service heuristic from AirGuard; model and hardware not verified.',
        evidence_references=[dict(source='external_spec', description='AirGuard original implementation; reviewed 2026-10-12', url_or_ref=base + source)],
        verification=dict(level='web_reference', reviewed='2026-10-12', note='No local lab specimen'),
        output=dict(protocol_family=family, brand=None, model=None, brand_source=None,
                    status_text=f'Possible {family} tracker: web-reference service signature; model unknown; not lab verified',
                    is_candidate=True, candidate_group='possible_tracker'), conditions={'all_of': conditions})
    rule_path = RULES / 'experimental' / (name + '.json')
    if not rule_path.exists():
        rule_path.write_text(json.dumps(data, indent=2) + '\n')

schema_path = RULES / 'schema.json'
schema = json.loads(schema_path.read_text())
schema['properties']['verification'] = {'type': 'object', 'properties': {
    'level': {'enum': ['web_reference', 'lab_verified', 'unverified']},
    'lab_capture_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
    'reviewed': {'type': 'string'}, 'note': {'type': 'string'}}, 'required': ['level'],
    'allOf': [{'if': {'properties': {'level': {'const': 'lab_verified'}}}, 'then': {'required': ['lab_capture_sha256']}}]}
schema_path.write_text(json.dumps(schema, indent=2) + '\n')
print('Research rules written with explicit verification metadata.')
