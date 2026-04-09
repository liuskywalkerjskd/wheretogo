from datetime import datetime, timezone

from rmuc_analyzer.engine import build_historical_highlights
from rmuc_analyzer.models import NationalTierRecord, QingflowSnapshot


def test_historical_highlights_include_resurrection_label():
    snapshot = QingflowSnapshot(
        fetched_at=datetime.now(timezone.utc),
        source_url="test",
        region_counts={"南部": 1, "东部": 2, "北部": 0},
        region_schools={
            "南部": ["A校"],
            "东部": ["B校", "C校"],
            "北部": [],
        },
        stale=False,
    )

    records = {
        "A校": NationalTierRecord(
            school="A校",
            team="A",
            tier="十六强",
            rank_order=12,
            award_level="一等奖",
            in_top32=True,
            is_resurrection_team=False,
        ),
        "B校": NationalTierRecord(
            school="B校",
            team="B",
            tier="-",
            rank_order=45,
            award_level="二等奖",
            in_top32=False,
            is_resurrection_team=True,
        ),
        "C校": NationalTierRecord(
            school="C校",
            team="C",
            tier="-",
            rank_order=70,
            award_level="三等奖",
            in_top32=False,
            is_resurrection_team=False,
        ),
    }

    result = build_historical_highlights(snapshot, records)

    assert result["A校"] == "十六强"
    assert result["B校"] == "复活赛"
    assert result["C校"] == "三等奖"
