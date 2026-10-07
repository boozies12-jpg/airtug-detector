export interface SignalSummary {
  current_rssi: number | null;
  current_age_s: number;
  freshness: "Recent observation" | "Waiting for next observation" | "No recent signal" | "Signal Lost";
  summary_20s_median: number | null;
  summary_20s_count: number;
  summary_20s_coverage_s: number;
  trend_20s: "Stronger" | "Weaker" | "Stable" | "Insufficient Data";
  trend_diff_db: number | null;
  recent_history: Array<{ t_rel_s: number; rssi: number }>;
}

export interface ClassificationResult {
  is_candidate: boolean;
  candidate_group?: "protocol_match" | "possible_tracker";
  protocol_family?: string | null;
  brand?: string | null;
  model?: string | null;
  brand_source?: "advertised_name" | "operator_labeled" | "inferred" | null;
  status_text: string;
  matched_rule_ids: string[];
  evidence: Record<string, any>;
  conflicts: string[];
}

export interface BleDeviceItem {
  address: string;
  local_name: string | null;
  classification: ClassificationResult;
  signal: SignalSummary;
  is_pinned: boolean;
  is_found: boolean;
  found_notes?: string;
}

export interface AppStatus {
  is_scanning: boolean;
  is_demo: boolean;
  current_session_id: string | null;
  selected_target_address: string | null;
  selected_target_summary?: SignalSummary | null;
  pinned_addresses: string[];
  rule_catalog_version: string;
  rule_catalog_hash: string;
  rule_count: number;
}
