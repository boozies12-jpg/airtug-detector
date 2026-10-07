import json
import os
import hashlib
from typing import Dict, List, Optional, Any, Set
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except (ImportError, Exception):
    HAS_JSONSCHEMA = False
from pydantic import BaseModel
from .models import (
    NormalizedBleRecord,
    ClassificationResult,
    CandidateGroup,
    BrandSource,
    Maturity,
    RuleKind
)

class RuleDefinition(BaseModel):
    rule_id: str
    revision: int
    schema_version: str
    enabled: bool
    maturity: Maturity
    kind: RuleKind
    description: str
    evidence_references: List[Dict[str, Any]]
    output: Dict[str, Any]
    conditions: Dict[str, Any]

class RuleCatalog:
    """
    Extensible JSON rule catalog. Validates loaded rules against schema.json.
    Computes catalog hash and version for session tracking.
    """
    def __init__(self, rules_dir: str):
        self.rules_dir = rules_dir
        self.rules: Dict[str, RuleDefinition] = {}
        self.content_hash: str = ""
        self.version: str = "1.0.0"
        self._schema: Optional[Dict[str, Any]] = None

    def load(self):
        schema_path = os.path.join(self.rules_dir, "schema.json")
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema not found at {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            self._schema = json.load(f)

        rules_list: List[RuleDefinition] = []
        raw_contents: List[bytes] = []

        # Recursively find all json files except schema.json
        for root, _, files in sorted(os.walk(self.rules_dir)):
            for file in sorted(files):
                if file.endswith(".json") and file != "schema.json":
                    p = os.path.join(root, file)
                    with open(p, "rb") as f:
                        data = f.read()
                        raw_contents.append(data)
                        rule_dict = json.loads(data.decode("utf-8"))

                    # Schema validation
                    if HAS_JSONSCHEMA and self._schema:
                        jsonschema.validate(instance=rule_dict, schema=self._schema)
                    rule_def = RuleDefinition(**rule_dict)
                    if rule_def.rule_id in self.rules:
                        raise ValueError(f"Duplicate rule_id found: {rule_def.rule_id}")
                    rules_list.append(rule_def)

        # Hash computation
        hasher = hashlib.sha256()
        for c in raw_contents:
            hasher.update(c)
        self.content_hash = hasher.hexdigest()[:16]

        self.rules = {r.rule_id: r for r in rules_list if r.enabled}

    def get_rule(self, rule_id: str) -> Optional[RuleDefinition]:
        return self.rules.get(rule_id)

class ClassifierEngine:
    """
    Deterministic rule-based classification engine.
    Evaluates protocol matches and brand refinements with explicit dependency resolution.
    """
    def __init__(self, catalog: RuleCatalog):
        self.catalog = catalog

    def _eval_condition(self, cond: Dict[str, Any], record: NormalizedBleRecord, matched_ids: Set[str]) -> bool:
        if "all_of" in cond:
            return all(self._eval_condition(sub, record, matched_ids) for sub in cond["all_of"])

        if "any_of" in cond:
            return any(self._eval_condition(sub, record, matched_ids) for sub in cond["any_of"])

        if "depends_on_rule_id" in cond:
            dep_id = cond["depends_on_rule_id"]
            return dep_id in matched_ids

        if "company_id" in cond:
            cid = cond["company_id"].lower()
            if cid not in record.manufacturer_data:
                return False

        if "service_uuid" in cond:
            suuid = cond["service_uuid"].lower()
            if suuid not in record.service_data and suuid not in record.service_uuids:
                return False

        if "payload_length_in" in cond:
            src = cond.get("source", "service_data")
            allowed = cond["payload_length_in"]
            if src == "service_data":
                matched = False
                for payload_hex in record.service_data.values():
                    if (len(payload_hex) // 2) in allowed:
                        matched = True
                        break
                if not matched:
                    return False
            elif src == "manufacturer_data":
                matched = False
                for payload_hex in record.manufacturer_data.values():
                    if (len(payload_hex) // 2) in allowed:
                        matched = True
                        break
                if not matched:
                    return False

        if "apple_record_type" in cond:
            req_type = cond["apple_record_type"]
            req_len = cond.get("apple_body_length")
            matched = False
            for rec in record.parsed_apple_records:
                if rec.record_type == req_type:
                    if req_len is None or rec.length == req_len:
                        matched = True
                        break
            if not matched:
                return False

        if "byte_matches" in cond:
            for bm in cond["byte_matches"]:
                src = bm["source"]
                offset = bm["offset"]
                exp = bm["expected_hex"].lower()
                matched_bm = False
                if src == "service_data":
                    for payload_hex in record.service_data.values():
                        b = bytes.fromhex(payload_hex)
                        if offset < len(b) and f"{b[offset]:02x}" == exp:
                            matched_bm = True
                            break
                elif src == "manufacturer_data":
                    for payload_hex in record.manufacturer_data.values():
                        b = bytes.fromhex(payload_hex)
                        if offset < len(b) and f"{b[offset]:02x}" == exp:
                            matched_bm = True
                            break
                elif src == "parsed_apple_body":
                    for rec in record.parsed_apple_records:
                        b = bytes.fromhex(rec.body_hex)
                        if offset < len(b) and f"{b[offset]:02x}" == exp:
                            matched_bm = True
                            break
                if not matched_bm:
                    return False

        if "masked_flags" in cond:
            for mf in cond["masked_flags"]:
                src = mf["source"]
                offset = mf["offset"]
                mask = int(mf["mask_hex"], 16)
                exp = int(mf["expected_hex"], 16)
                matched_mf = False
                if src == "service_data":
                    for payload_hex in record.service_data.values():
                        b = bytes.fromhex(payload_hex)
                        if offset < len(b) and (b[offset] & mask) == exp:
                            matched_mf = True
                            break
                elif src == "manufacturer_data":
                    for payload_hex in record.manufacturer_data.values():
                        b = bytes.fromhex(payload_hex)
                        if offset < len(b) and (b[offset] & mask) == exp:
                            matched_mf = True
                            break
                if not matched_mf:
                    return False

        if "exact_local_name" in cond:
            if not record.local_name:
                return False
            name_cfg = cond["exact_local_name"]
            req_name = name_cfg["name"]
            case_sens = name_cfg.get("case_sensitive", True)
            if case_sens:
                if record.local_name != req_name:
                    return False
            else:
                if record.local_name.lower() != req_name.lower():
                    return False

        return True

    def classify(self, record: NormalizedBleRecord) -> ClassificationResult:
        # Phase 1: Evaluate protocol rules
        matched_protocol_rules: List[RuleDefinition] = []
        matched_ids: Set[str] = set()

        for rule in self.catalog.rules.values():
            if rule.kind == RuleKind.PROTOCOL:
                if self._eval_condition(rule.conditions, record, matched_ids):
                    matched_protocol_rules.append(rule)
                    matched_ids.add(rule.rule_id)

        # Phase 2: Evaluate brand refinement rules
        matched_brand_rules: List[RuleDefinition] = []
        for rule in self.catalog.rules.values():
            if rule.kind == RuleKind.BRAND_REFINEMENT:
                if self._eval_condition(rule.conditions, record, matched_ids):
                    matched_brand_rules.append(rule)
                    matched_ids.add(rule.rule_id)

        all_matched = matched_protocol_rules + matched_brand_rules
        if not all_matched:
            # Check for non-candidate recognized patterns like Apple proximity pairing (type 07)
            for rec in record.parsed_apple_records:
                if rec.record_type == 7:
                    return ClassificationResult(
                        is_candidate=False,
                        protocol_family=None,
                        brand=None,
                        status_text="Apple proximity pairing (non-tracker)",
                        matched_rule_ids=[]
                    )
            return ClassificationResult(
                is_candidate=False,
                status_text="Unknown device",
                matched_rule_ids=[]
            )

        # Merge results deterministically
        protocol_families = set()
        brands = set()
        candidate_groups = set()
        status_texts = []
        conflicts = []

        for r in all_matched:
            out = r.output
            if out.get("protocol_family"):
                protocol_families.add(out["protocol_family"])
            if out.get("brand"):
                brands.add((out["brand"], out.get("model"), out.get("brand_source")))
            if out.get("candidate_group"):
                candidate_groups.add(out["candidate_group"])
            if out.get("status_text"):
                status_texts.append(out["status_text"])

        if len(protocol_families) > 1:
            conflicts.append(f"Multiple conflicting protocol families: {list(protocol_families)}")

        chosen_proto = next(iter(protocol_families)) if protocol_families else None
        chosen_brand = None
        chosen_model = None
        chosen_brand_source = None

        if brands:
            b, m, bs = next(iter(brands))
            chosen_brand = b
            chosen_model = m
            chosen_brand_source = BrandSource(bs) if bs else None

        chosen_group = None
        if CandidateGroup.PROTOCOL_MATCH in candidate_groups:
            chosen_group = CandidateGroup.PROTOCOL_MATCH
        elif CandidateGroup.POSSIBLE_TRACKER in candidate_groups:
            chosen_group = CandidateGroup.POSSIBLE_TRACKER

        return ClassificationResult(
            is_candidate=True,
            candidate_group=chosen_group,
            protocol_family=chosen_proto,
            brand=chosen_brand,
            model=chosen_model,
            brand_source=chosen_brand_source,
            status_text=" | ".join(status_texts) if status_texts else "Candidate match",
            matched_rule_ids=[r.rule_id for r in all_matched],
            conflicts=conflicts,
            evidence={
                "local_name": record.local_name,
                "service_uuids": record.service_uuids,
                "service_data_keys": list(record.service_data.keys()),
                "mfg_keys": list(record.manufacturer_data.keys()),
                "rules": [r.rule_id for r in all_matched]
            }
        )
