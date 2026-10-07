// Mobile-native classification and signal processing engine for iOS & Android
import { BleDeviceItem, SignalSummary, ClassificationResult, AppStatus } from '../types';

// Import all JSON rules bundled with Vite
const ruleModules = import.meta.glob('../../rules/**/*.json', { eager: true });

export interface RuleOutput {
  protocol_family?: string | null;
  brand?: string | null;
  model?: string | null;
  brand_source?: "advertised_name" | "operator_labeled" | "inferred" | null;
  status_text: string;
  is_candidate: boolean;
  candidate_group?: "protocol_match" | "possible_tracker";
}

export interface RuleCondition {
  all_of?: RuleCondition[];
  any_of?: RuleCondition[];
  company_id?: string;
  service_uuid?: string;
  payload_length_in?: number[];
  source?: "manufacturer_data" | "service_data" | "parsed_apple_body";
  apple_record_type?: number;
  apple_body_length?: number;
  byte_matches?: Array<{ offset: number; expected_hex: string; source: string }>;
  masked_flags?: Array<{ offset: number; mask_hex: string; expected_hex: string; source: string }>;
  hex_prefix?: { prefix: string; source: string };
  exact_local_name?: { name: string; case_sensitive?: boolean };
  depends_on_rule_id?: string;
}

export interface RuleDefinition {
  rule_id: string;
  revision: number;
  schema_version: string;
  enabled: boolean;
  maturity: "validated" | "experimental";
  kind: "protocol" | "brand_refinement";
  description: string;
  output: RuleOutput;
  conditions: RuleCondition;
}

export interface NormalizedRecord {
  address: string;
  rssi: number | null;
  local_name: string | null;
  manufacturer_data: Record<string, string>; // cid_hex -> payload_hex
  service_data: Record<string, string>;      // uuid_hex -> payload_hex
  service_uuids: string[];
  parsed_apple_records: Array<{ record_type: number; length: number; body_hex: string }>;
  tx_power?: number | null;
  monotonic_s: number;
}

export class MobileSignalProcessor {
  private rawHistory: Map<string, Array<{ t: number; rssi: number }>> = new Map();
  private bucketedGroups: Map<string, Array<{ t: number; rssi: number }>> = new Map();
  private bucketDurationS = 0.25;

  clear() {
    this.rawHistory.clear();
    this.bucketedGroups.clear();
  }

  addObservation(address: string, rssi: number | null, monoS: number) {
    if (rssi === null || rssi === undefined) return;
    if (!this.rawHistory.has(address)) {
      this.rawHistory.set(address, []);
      this.bucketedGroups.set(address, []);
    }
    this.rawHistory.get(address)!.push({ t: monoS, rssi });
    this.rebucket(address);
  }

  private rebucket(address: string) {
    const raw = this.rawHistory.get(address) || [];
    if (raw.length === 0) return;

    const buckets = new Map<number, number[]>();
    for (const obs of raw) {
      const idx = Math.floor(obs.t / this.bucketDurationS);
      if (!buckets.has(idx)) buckets.set(idx, []);
      buckets.get(idx)!.push(obs.rssi);
    }

    const sortedIdxs = Array.from(buckets.keys()).sort((a, b) => a - b);
    const groups: Array<{ t: number; rssi: number }> = [];
    for (const bIdx of sortedIdxs) {
      const midT = (bIdx + 0.5) * this.bucketDurationS;
      const vals = buckets.get(bIdx)!.sort((a, b) => a - b);
      const mid = Math.floor(vals.length / 2);
      const medRssi = vals.length % 2 !== 0 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2;
      groups.push({ t: midT, rssi: Math.round(medRssi) });
    }
    this.bucketedGroups.set(address, groups);
  }

  getSummary(address: string, currentMonoS: number): SignalSummary {
    const groups = this.bucketedGroups.get(address) || [];
    if (groups.length === 0) {
      return {
        current_rssi: null,
        current_age_s: 999,
        freshness: "Signal Lost",
        summary_20s_median: null,
        summary_20s_count: 0,
        summary_20s_coverage_s: 0,
        trend_20s: "Insufficient Data",
        trend_diff_db: null,
        recent_history: []
      };
    }

    const latest = groups[groups.length - 1];
    const ageS = Math.max(0, currentMonoS - latest.t);

    let freshness: SignalSummary["freshness"] = "Signal Lost";
    if (ageS <= 3.0) freshness = "Recent observation";
    else if (ageS <= 30.0) freshness = "Waiting for next observation";
    else if (ageS <= 60.0) freshness = "No recent signal";

    // 20s window: [currentMonoS - 20, currentMonoS]
    const w20Start = currentMonoS - 20.0;
    const w20 = groups.filter((g) => g.t >= w20Start && g.t <= currentMonoS);
    const count20 = w20.length;

    let med20: number | null = null;
    let cov20 = 0;
    if (count20 > 0) {
      const sVals = w20.map((g) => g.rssi).sort((a, b) => a - b);
      const mid = Math.floor(sVals.length / 2);
      med20 = sVals.length % 2 !== 0 ? sVals[mid] : Math.round((sVals[mid - 1] + sVals[mid]) / 2);
      cov20 = Math.round((w20[w20.length - 1].t - w20[0].t) * 10) / 10;
    }

    // Previous 20s window: [currentMonoS - 40, currentMonoS - 20]
    const wPrevStart = currentMonoS - 40.0;
    const wPrev = groups.filter((g) => g.t >= wPrevStart && g.t < w20Start);
    let trend: SignalSummary["trend_20s"] = "Insufficient Data";
    let trendDiff: number | null = null;

    if (w20.length >= 3 && wPrev.length >= 3 && med20 !== null) {
      const pVals = wPrev.map((g) => g.rssi).sort((a, b) => a - b);
      const midP = Math.floor(pVals.length / 2);
      const medPrev = pVals.length % 2 !== 0 ? pVals[midP] : Math.round((pVals[midP - 1] + pVals[midP]) / 2);

      const diff = med20 - medPrev;
      trendDiff = Math.abs(diff);
      if (diff >= 3) trend = "Stronger";
      else if (diff <= -3) trend = "Weaker";
      else trend = "Stable";
    }

    // Recent 30s history for sparkline
    const histStart = currentMonoS - 30.0;
    const recentHistory = groups
      .filter((g) => g.t >= histStart)
      .map((g) => ({
        t_rel_s: Math.round((g.t - currentMonoS) * 10) / 10,
        rssi: g.rssi
      }));

    return {
      current_rssi: latest.rssi,
      current_age_s: Math.round(ageS * 10) / 10,
      freshness,
      summary_20s_median: med20,
      summary_20s_count: count20,
      summary_20s_coverage_s: cov20,
      trend_20s: trend,
      trend_diff_db: trendDiff,
      recent_history: recentHistory
    };
  }
}

export class MobileClassifier {
  public rules: Map<string, RuleDefinition> = new Map();

  constructor() {
    this.loadBundledRules();
  }

  loadBundledRules() {
    for (const path in ruleModules) {
      if (path.endsWith("schema.json")) continue;
      const mod = ruleModules[path] as any;
      const rule = (mod.default || mod) as RuleDefinition;
      if (rule && rule.rule_id && rule.enabled) {
        this.rules.set(rule.rule_id, rule);
      }
    }
  }

  private evalCondition(cond: RuleCondition, rec: NormalizedRecord, matchedRules: Set<string>): boolean {
    if (cond.all_of) {
      for (const sub of cond.all_of) {
        if (!this.evalCondition(sub, rec, matchedRules)) return false;
      }
    }
    if (cond.any_of) {
      let anyOk = false;
      for (const sub of cond.any_of) {
        if (this.evalCondition(sub, rec, matchedRules)) {
          anyOk = true;
          break;
        }
      }
      if (!anyOk) return false;
    }
    if (cond.depends_on_rule_id) {
      if (!matchedRules.has(cond.depends_on_rule_id)) return false;
    }
    if (cond.company_id) {
      const cid = cond.company_id.toLowerCase().replace("0x", "");
      if (!(cid in rec.manufacturer_data)) return false;
    }
    if (cond.service_uuid) {
      const su = cond.service_uuid.toLowerCase().replace("0x", "");
      if (!(su in rec.service_data) && !rec.service_uuids.includes(su)) return false;
    }
    if (cond.payload_length_in) {
      const src = cond.source || "service_data";
      const allowed = cond.payload_length_in;
      if (src === "service_data") {
        let matched = false;
        for (const hex of Object.values(rec.service_data)) {
          if (allowed.includes(hex.length / 2)) {
            matched = true;
            break;
          }
        }
        if (!matched) return false;
      } else if (src === "manufacturer_data") {
        let matched = false;
        for (const hex of Object.values(rec.manufacturer_data)) {
          if (allowed.includes(hex.length / 2)) {
            matched = true;
            break;
          }
        }
        if (!matched) return false;
      }
    }
    if (cond.hex_prefix) {
      const prefix = cond.hex_prefix.prefix.toLowerCase();
      const src = cond.hex_prefix.source || "manufacturer_data";
      let matched = false;
      if (src === "manufacturer_data") {
        for (const hex of Object.values(rec.manufacturer_data)) {
          if (hex.toLowerCase().startsWith(prefix)) {
            matched = true;
            break;
          }
        }
      } else if (src === "service_data") {
        for (const hex of Object.values(rec.service_data)) {
          if (hex.toLowerCase().startsWith(prefix)) {
            matched = true;
            break;
          }
        }
      }
      if (!matched) return false;
    }
    if (cond.exact_local_name) {
      if (!rec.local_name) return false;
      const target = cond.exact_local_name.name;
      if (cond.exact_local_name.case_sensitive === false) {
        if (rec.local_name.toLowerCase() !== target.toLowerCase()) return false;
      } else {
        if (rec.local_name !== target) return false;
      }
    }
    return true;
  }

  classify(rec: NormalizedRecord): ClassificationResult {
    let bestResult: ClassificationResult = {
      is_candidate: false,
      candidate_group: undefined,
      protocol_family: null,
      brand: null,
      model: null,
      brand_source: null,
      status_text: "Background device",
      matched_rule_ids: [],
      evidence: {},
      conflicts: []
    };

    const matchedRuleIds = new Set<string>();

    // Pass 1: Protocol rules
    for (const [id, rule] of this.rules.entries()) {
      if (rule.kind === "protocol") {
        if (this.evalCondition(rule.conditions, rec, matchedRuleIds)) {
          matchedRuleIds.add(id);
          bestResult.is_candidate = rule.output.is_candidate;
          bestResult.candidate_group = rule.output.candidate_group;
          bestResult.protocol_family = rule.output.protocol_family;
          bestResult.brand = rule.output.brand;
          bestResult.model = rule.output.model;
          bestResult.brand_source = rule.output.brand_source;
          bestResult.status_text = rule.output.status_text;
          bestResult.matched_rule_ids.push(id);
        }
      }
    }

    // Pass 2: Brand refinement rules
    for (const [id, rule] of this.rules.entries()) {
      if (rule.kind === "brand_refinement") {
        if (this.evalCondition(rule.conditions, rec, matchedRuleIds)) {
          matchedRuleIds.add(id);
          if (rule.output.brand) bestResult.brand = rule.output.brand;
          if (rule.output.model) bestResult.model = rule.output.model;
          if (rule.output.brand_source) bestResult.brand_source = rule.output.brand_source;
          bestResult.matched_rule_ids.push(id);
        }
      }
    }

    return bestResult;
  }
}
