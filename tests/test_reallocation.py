from datetime import datetime, timezone

from rmuc_analyzer.engine import predict_reallocation
from rmuc_analyzer.models import DistanceRecord, QingflowSnapshot
from rmuc_analyzer.sources.robomaster import infer_overseas_priority_schools_2026
from rmuc_analyzer.models import TeamRecord


def test_reallocation_same_distance_uses_worse_rank_first():
    snapshot = QingflowSnapshot(
        fetched_at=datetime.now(timezone.utc),
        source_url="test",
        region_counts={"南部": 4, "东部": 3, "北部": 2},
        region_schools={
            "南部": ["S1", "S2", "S3", "S4"],
            "东部": ["E1", "E2", "E3"],
            "北部": ["N1", "N2"],
        },
        stale=False,
    )

    distance_map = {
        "S1": DistanceRecord("S1", "A", 10, 20, 40),
        "S2": DistanceRecord("S2", "A", 10, 20, 30),
        "S3": DistanceRecord("S3", "A", 10, 20, 10),
        "S4": DistanceRecord("S4", "A", 10, 20, 10),
        "E1": DistanceRecord("E1", "B", 30, 10, 50),
        "E2": DistanceRecord("E2", "B", 30, 10, 60),
        "E3": DistanceRecord("E3", "B", 30, 10, 20),
        "N1": DistanceRecord("N1", "C", 80, 80, 0),
        "N2": DistanceRecord("N2", "C", 80, 80, 0),
    }

    ranking_map = {
        "S3": 50,
        "S4": 100,
    }

    moves = predict_reallocation(
        snapshot=snapshot,
        distance_map=distance_map,
        ranking_map=ranking_map,
        priority_schools=[],
        capacity=3,
        expected_total=9,
    )

    assert len(moves) == 1
    assert moves[0].school == "S4"
    assert moves[0].from_region == "南部"
    assert moves[0].to_region == "北部"


def test_no_reallocation_when_no_surplus_region():
    snapshot = QingflowSnapshot(
        fetched_at=datetime.now(timezone.utc),
        source_url="test",
        region_counts={"南部": 3, "东部": 3, "北部": 3},
        region_schools={"南部": ["S1", "S2", "S3"], "东部": ["E1", "E2", "E3"], "北部": ["N1", "N2", "N3"]},
        stale=False,
    )

    moves = predict_reallocation(
        snapshot=snapshot,
        distance_map={},
        ranking_map={},
        priority_schools=[],
        capacity=3,
        expected_total=9,
    )

    assert moves == []


def test_priority_school_is_excluded_from_reallocation_candidates():
    snapshot = QingflowSnapshot(
        fetched_at=datetime.now(timezone.utc),
        source_url="test",
        region_counts={"南部": 4, "东部": 4, "北部": 1},
        region_schools={
            "南部": ["A1", "A2", "A3", "A4"],
            "东部": ["E1", "E2", "E3", "E4"],
            "北部": ["N1"],
        },
        stale=False,
    )

    distance_map = {
        "A1": DistanceRecord("A1", "A", 10, 20, 1),
        "A2": DistanceRecord("A2", "A", 10, 20, 2),
        "A3": DistanceRecord("A3", "A", 10, 20, 10),
        "A4": DistanceRecord("A4", "A", 10, 20, 11),
        "E1": DistanceRecord("E1", "B", 20, 10, 3),
        "E2": DistanceRecord("E2", "B", 20, 10, 4),
        "E3": DistanceRecord("E3", "B", 20, 10, 12),
        "E4": DistanceRecord("E4", "B", 20, 10, 13),
        "N1": DistanceRecord("N1", "C", 80, 80, 0),
    }

    moves = predict_reallocation(
        snapshot=snapshot,
        distance_map=distance_map,
        ranking_map={},
        priority_schools=["A1"],
        capacity=3,
        expected_total=9,
    )

    moved_schools = {move.school for move in moves}
    assert "A1" not in moved_schools
    assert len(moves) == 2


def test_infer_overseas_priority_schools_from_city_and_name():
    teams = [
        TeamRecord(school="香港大学", team="A"),
        TeamRecord(school="香港科技大学", team="B"),
        TeamRecord(school="香港科技大学（广州）", team="BG"),
        TeamRecord(school="华南理工大学", team="C"),
    ]

    distance_map = {
        "香港大学": DistanceRecord("香港大学", "香港", 662, 1615, 2328),
        "香港科技大学": DistanceRecord("香港科技大学", "香港", 662, 1615, 2328),
        "香港科技大学(广州)": DistanceRecord("香港科技大学（广州）", "广州市", 564, 1549, 2281),
        "华南理工大学": DistanceRecord("华南理工大学", "广州市", 564, 1549, 2281),
    }

    overseas = infer_overseas_priority_schools_2026(teams, distance_map)

    assert "香港大学" in overseas
    assert "香港科技大学" in overseas
    assert "香港科技大学（广州）" not in overseas
    assert "华南理工大学" not in overseas
