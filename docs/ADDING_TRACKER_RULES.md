# Adding Tracker Rules — Operator & Developer Guide

This document describes how to add new tracker detection rules, protocols, brands, and experimental signatures to the **Windows BLE Tracker Search** system.

In accordance with Section 4A of the Product Specification, rule additions are **declarative and data-driven**. You do not need to modify the BLE scanner, signal processor, or UI codebase.

---

## 1. Directory Structure

Rules live in the `rules/` directory:

- `rules/schema.json`: Formal JSON Schema (draft-07) validating all rule definitions.
- `rules/protocols/`: Detection rules for core finding networks (e.g. `google_find_hub.json`, `apple_find_my.json`).
- `rules/brands/`: Brand and model refinement rules that depend on protocol matches (e.g. `xiaomi_tag.json`).
- `rules/experimental/`: Provisional, unvalidated signatures (e.g. `apple_find_my_fd44.json`, `xiaomi_fast_pair.json`).

---

## 2. Rule Schema & Fields

Every rule JSON file must validate against `rules/schema.json`. A complete rule consists of:

| Field | Type | Description |
|---|---|---|
| `rule_id` | `string` | Unique, stable identifier (e.g. `protocol.google_find_hub`, `brand.xiaomi_tag`). |
| `revision` | `integer` | Monotonically increasing revision number (starts at `1`). |
| `schema_version` | `string` | Version of the schema (currently `"1.0.0"`). |
| `enabled` | `boolean` | Whether the rule is actively evaluated. |
| `maturity` | `string` | `"validated"` (hardware-confirmed) or `"experimental"` (provisional). |
| `kind` | `string` | `"protocol"` or `"brand_refinement"`. |
| `description` | `string` | Human-readable explanation of the pattern. |
| `evidence_references` | `array` | External specifications, test captures, or papers justifying the rule. |
| `output` | `object` | Classified attributes when matched: `protocol_family`, `brand`, `model`, `status_text`. |
| `conditions` | `object` | Bound condition tree: `all_of`, `any_of`, `company_id`, `service_uuid`, `payload_length_in`, `byte_matches`, `masked_flags`, `hex_prefix`, `exact_local_name`, `depends_on_rule_id`. |

---

## 3. Supported Matching Primitives

All byte matching primitives require an explicit byte source (`service_data`, `manufacturer_data`, or `parsed_body`):

1. **Company ID & Service UUID**:
   ```json
   { "company_id": "004c" }
   { "service_uuid": "feaa" }
   ```
2. **Payload Length Restriction**:
   ```json
   { "payload_length_in": [21, 22, 33, 34], "source": "service_data" }
   ```
3. **Byte Match at Exact Offset**:
   ```json
   { "byte_matches": [{ "offset": 0, "expected_hex": "40", "source": "service_data" }] }
   ```
4. **Masked Bitflags**:
   ```json
   { "masked_flags": [{ "offset": 21, "mask_hex": "03", "expected_hex": "02", "source": "service_data" }] }
   ```
5. **Exact Advertised Local Name**:
   ```json
   { "exact_local_name": { "name": "Xiaomi Tag", "case_sensitive": true } }
   ```
6. **Protocol Dependency (Brand Refinement)**:
   ```json
   { "depends_on_rule_id": "protocol.google_find_hub" }
   ```

---

## 4. Complete Worked Example: Adding a New Brand Refinement

Suppose a newly discovered tracker emits standard `Google Find Hub` (`FEAA`) packets, but when a scan response is requested, it advertises the local name `"Chipolo Point"`.

### Step 1: Create `rules/brands/chipolo_point.json`

```json
{
  "rule_id": "brand.chipolo_point",
  "revision": 1,
  "schema_version": "1.0.0",
  "enabled": true,
  "maturity": "validated",
  "kind": "brand_refinement",
  "description": "Chipolo Point branded Google Find Hub tracker accessory",
  "evidence_references": [
    {
      "source": "observed_excerpt",
      "description": "Chipolo Point test specimen scan response with complete local name"
    }
  ],
  "output": {
    "brand": "Chipolo",
    "model": "Chipolo Point",
    "brand_source": "advertised_name"
  },
  "conditions": {
    "all_of": [
      {
        "depends_on_rule_id": "protocol.google_find_hub"
      },
      {
        "exact_local_name": {
          "name": "Chipolo Point",
          "case_sensitive": true
        }
      }
    ]
  }
}
```

### Step 2: Add Test Fixtures in `tests/fixtures/classification/fixtures.json`

Add labeled positive and negative fixtures to ensure the new rule matches when both conditions are satisfied, but does not match when only the name or only the protocol is present:

```json
{
  "id": "chipolo_point_positive",
  "origin": "synthetic",
  "record": {
    "address": "AA:BB:CC:DD:EE:01",
    "service_data": {
      "feaa": "400102030405060708090a0b0c0d0e0f101112131406"
    },
    "local_name": "Chipolo Point"
  },
  "expected": {
    "matched_rules": ["protocol.google_find_hub", "brand.chipolo_point"],
    "protocol_family": "Google Find Hub",
    "brand": "Chipolo",
    "model": "Chipolo Point",
    "brand_source": "advertised_name"
  }
}
```

### Step 3: Run the Test Suite

Execute pytest to ensure all schemas validate and all fixtures pass:
```bash
python3 -m pytest tests/test_milestone_a.py -k test_rule_catalog
```

---

## 5. Offline Catalog Validation Command

You can validate the rule catalog offline without starting the server:
```bash
python3 -c "
from src.domain.classifier import RuleCatalog
catalog = RuleCatalog('rules')
catalog.load()
print(f'Catalog loaded successfully! Version: {catalog.version}, Total rules: {len(catalog.rules)}')
for r in catalog.rules.values():
    print(f' - [{r.kind}] {r.rule_id} (rev {r.revision}) enabled={r.enabled}')
"
```
