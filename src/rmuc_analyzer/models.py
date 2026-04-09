from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class TeamRecord:
    school: str
    team: str


@dataclass
class DistanceRecord:
    school: str
    city: str
    to_changsha: int
    to_jinan: int
    to_shenyang: int


@dataclass
class NationalTierRecord:
    school: str
    team: str
    tier: str
    rank_order: int
    award_level: str = "-"
    in_top32: bool = False
    is_resurrection_team: bool = False


@dataclass
class QingflowSnapshot:
    fetched_at: datetime
    region_counts: Dict[str, int]
    region_schools: Dict[str, List[str]]
    source_url: str
    stale: bool = False


@dataclass
class QuotaItem:
    region: str
    base_quota: int
    floating_quota: int
    total_quota: int
    top16_count: int
    eligible: bool
    remainder: float


@dataclass
class QuotaResult:
    items: Dict[str, QuotaItem]
    tie_break_trace: List[str] = field(default_factory=list)


@dataclass
class ReallocationMove:
    school: str
    from_region: str
    to_region: str
    distance_km: int
    ranking_value: Optional[int]
    confidence: str
    reason: str


@dataclass
class PressureItem:
    region: str
    volunteers: int
    capacity: int
    deficit: int
    surplus: int


@dataclass
class AnalyzerReport:
    generated_at: datetime
    submitted_teams: int
    expected_teams: int
    quota_result: QuotaResult
    pressure: Dict[str, PressureItem]
    reallocation_moves: List[ReallocationMove]
    historical_highlights: Dict[str, str]
    notes: List[str] = field(default_factory=list)
