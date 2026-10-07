from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Maturity(str, Enum):
    VALIDATED = "validated"
    EXPERIMENTAL = "experimental"

class RuleKind(str, Enum):
    PROTOCOL = "protocol"
    BRAND_REFINEMENT = "brand_refinement"

class BrandSource(str, Enum):
    ADVERTISED_NAME = "advertised_name"
    OPERATOR_LABELED = "operator_labeled"
    INFERRED = "inferred"

class CandidateGroup(str, Enum):
    PROTOCOL_MATCH = "protocol_match"
    POSSIBLE_TRACKER = "possible_tracker"

class SignalFreshness(str, Enum):
    RECENT = "Recent observation"               # age <= 3s
    WAITING = "Waiting for next observation"      # 3s < age <= 30s
    NO_RECENT = "No recent signal"                # 30s < age <= 60s
    LOST = "Signal Lost"                          # age > 60s

class TrendDirection(str, Enum):
    STRONGER = "Stronger"
    WEAKER = "Weaker"
    STABLE = "Stable"
    INSUFFICIENT_DATA = "Insufficient Data"

class ParsedAppleRecord(BaseModel):
    record_type: int
    length: int
    body_hex: str

class NormalizedBleRecord(BaseModel):
    address: str
    rssi: Optional[int] = None
    local_name: Optional[str] = None
    manufacturer_data: Dict[str, str] = Field(default_factory=dict)
    service_data: Dict[str, str] = Field(default_factory=dict)
    service_uuids: List[str] = Field(default_factory=list)
    parsed_apple_records: List[ParsedAppleRecord] = Field(default_factory=list)
    tx_power: Optional[int] = None
    reception_timestamp_utc: str
    monotonic_timestamp_s: float
    raw_hci_metadata: Dict[str, Any] = Field(default_factory=dict)

class ClassificationResult(BaseModel):
    is_candidate: bool = False
    candidate_group: Optional[CandidateGroup] = None
    protocol_family: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    brand_source: Optional[BrandSource] = None
    status_text: str = "Unknown device"
    matched_rule_ids: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    conflicts: List[str] = Field(default_factory=list)

class SignalSummary(BaseModel):
    current_rssi: Optional[int] = None
    current_age_s: float = 0.0
    freshness: SignalFreshness = SignalFreshness.WAITING
    summary_20s_median: Optional[float] = None
    summary_20s_count: int = 0
    summary_20s_coverage_s: float = 0.0
    trend_20s: TrendDirection = TrendDirection.INSUFFICIENT_DATA
    trend_diff_db: Optional[float] = None
    recent_history: List[Dict[str, Any]] = Field(default_factory=list)

class CheckpointRecord(BaseModel):
    checkpoint_id: str
    position_label: str
    target_address: str
    start_time_utc: str
    end_time_utc: str
    duration_s: float
    group_count: int
    coverage_s: float
    median_rssi: Optional[float] = None
    min_rssi: Optional[int] = None
    max_rssi: Optional[int] = None
    status: str
    notes: Optional[str] = None
