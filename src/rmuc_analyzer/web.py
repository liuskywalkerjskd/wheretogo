from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template

from rmuc_analyzer.cache import load_snapshot, save_snapshot
from rmuc_analyzer.config import AnalyzerConfig
from rmuc_analyzer.constants import REGION_DISPLAY, REGION_ORDER
from rmuc_analyzer.engine import (
    compute_national_quotas,
    estimate_resurrection_quotas,
    fallback_ranking_from_national,
    infer_top16_counts,
    load_rmu_ranking,
    predict_reallocation,
)
from rmuc_analyzer.sources.qingflow import parse_qingflow_snapshot
from rmuc_analyzer.sources.robomaster import (
    infer_overseas_priority_schools_2026,
    localize_announcement_sources,
    parse_distance_table_2026,
    parse_national_tiers_2025,
    parse_rmu_ranking_2025,
    parse_rmul_host_schools_2026,
    parse_teams_2026,
)
from rmuc_analyzer.utils import normalize_school_name


@dataclass
class AnalyzerRuntime:
    root_dir: Path
    config: AnalyzerConfig
    cache_file: Path
    teams: List[Any]
    known_school_names: List[str]
    distance_map: Dict[str, Any]
    national_records: Dict[str, Any]
    ranking_map: Dict[str, int]
    priority_schools: List[str]
    quota_result: Any
    static_notes: List[str]


def _write_ranking_csv(csv_path: Path, rows: List[Dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["school", "rank", "score"])
        writer.writeheader()
        writer.writerows(rows)


def _build_runtime(root_dir: Path, config: AnalyzerConfig) -> AnalyzerRuntime:
    announcement_sources = localize_announcement_sources(
        config.announcement_urls,
        root_dir=root_dir,
        timeout_sec=config.request_timeout_sec,
        local_dir=config.announcement_local_dir,
        local_only=config.announcement_local_only,
    )

    teams = parse_teams_2026(announcement_sources["teams_2026"], config.request_timeout_sec)
    distance_map = parse_distance_table_2026(announcement_sources["rules_2026"], config.request_timeout_sec)
    national_records = parse_national_tiers_2025(announcement_sources["national_2025"], config.request_timeout_sec)

    ranking_csv = config.resolve_path(root_dir, config.rmu_ranking_csv)
    ranking_map = load_rmu_ranking(str(ranking_csv))
    notes: List[str] = []

    ranking_url = announcement_sources.get("ranking_2025")
    if ranking_url:
        try:
            ranking_rows = parse_rmu_ranking_2025(ranking_url, config.request_timeout_sec)
            _write_ranking_csv(ranking_csv, ranking_rows)
            ranking_map = load_rmu_ranking(str(ranking_csv))
            notes.append(f"积分榜来源: 已从1884公告抓取并写入本地 {ranking_csv}")
        except Exception as exc:
            notes.append(f"积分榜抓取失败，继续使用本地CSV: {exc}")

    if not ranking_map:
        ranking_map = fallback_ranking_from_national(national_records)
        notes.append("积分榜来源: 未提供RMU积分榜CSV，已使用去年国赛顺位兜底")

    top16_counts, missing = infer_top16_counts(national_records, distance_map)
    if config.manual_top16_counts:
        top16_counts = {region: int(config.manual_top16_counts.get(region, 0)) for region in REGION_ORDER}
        notes.append("国赛名额来源: manual_top16_counts配置")
    else:
        notes.append("国赛名额来源: 去年前16按距离推断（模拟）")
    if missing:
        notes.append(f"去年前16缺少距离数据: {', '.join(missing)}")

    quota_result = compute_national_quotas(top16_counts)

    priority_schools = list(config.priority_schools)
    merged = {normalize_school_name(s): s for s in priority_schools}

    rmul_url = announcement_sources.get("rmul_hosts_2026")
    if rmul_url:
        try:
            rmul_hosts = parse_rmul_host_schools_2026(rmul_url, config.request_timeout_sec)
            for school in rmul_hosts:
                key = normalize_school_name(school)
                if key not in merged:
                    merged[key] = school
                    priority_schools.append(school)
            notes.append(f"优先: 已纳入RMUL承办院校 {', '.join(rmul_hosts)}")
        except Exception as exc:
            notes.append(f"优先: RMUL承办院校解析失败({exc})")

    overseas = infer_overseas_priority_schools_2026(teams, distance_map)
    for school in overseas:
        key = normalize_school_name(school)
        if key not in merged:
            merged[key] = school
            priority_schools.append(school)
    if overseas:
        notes.append(f"优先: 已纳入海外队伍 {', '.join(overseas)}")

    return AnalyzerRuntime(
        root_dir=root_dir,
        config=config,
        cache_file=config.resolve_path(root_dir, config.cache_file),
        teams=teams,
        known_school_names=[team.school for team in teams],
        distance_map=distance_map,
        national_records=national_records,
        ranking_map=ranking_map,
        priority_schools=priority_schools,
        quota_result=quota_result,
        static_notes=notes,
    )


def _snapshot_with_cache(runtime: AnalyzerRuntime):
    notes: List[str] = []
    try:
        snapshot = parse_qingflow_snapshot(
            runtime.config.qingflow_url,
            known_schools=runtime.known_school_names,
            timeout_sec=runtime.config.request_timeout_sec,
        )
        save_snapshot(runtime.cache_file, snapshot)
    except Exception as exc:
        cached = load_snapshot(runtime.cache_file)
        if cached is None:
            raise RuntimeError(f"青流抓取失败且无缓存: {exc}") from exc
        snapshot = cached
        notes.append(f"青流抓取失败，已回退缓存: {exc}")
    return snapshot, notes


def _school_sort_key(school: str, national_records: Dict[str, Any], ranking_map: Dict[str, int]):
    key = normalize_school_name(school)
    rec = national_records.get(key)
    nat_missing = 1 if rec is None else 0
    nat_rank = rec.rank_order if rec is not None else 10**9
    point_rank = ranking_map.get(key, 10**9)
    return (nat_missing, nat_rank, point_rank, school)


def _format_performance(rec: Optional[Any]) -> str:
    if rec is None:
        return "-"
    if rec.in_top32 and rec.tier != "-":
        return rec.tier
    if rec.is_resurrection_team:
        return "复活赛"
    return rec.award_level or "-"


def _build_payload(runtime: AnalyzerRuntime) -> Dict[str, Any]:
    snapshot, runtime_notes = _snapshot_with_cache(runtime)

    resurrection = estimate_resurrection_quotas(
        runtime.quota_result,
        snapshot.region_counts,
        resurrection_total=16,
        min_total_advancement=8,
        max_total_advancement=16,
    )

    moves = predict_reallocation(
        snapshot=snapshot,
        distance_map=runtime.distance_map,
        ranking_map=runtime.ranking_map,
        priority_schools=runtime.priority_schools,
        capacity=runtime.config.capacity_per_region,
        expected_total=runtime.config.expected_total_teams,
    )
    move_map = {normalize_school_name(m.school): m.to_region for m in moves}
    priority_key_set = {normalize_school_name(s) for s in runtime.priority_schools}

    regions_payload: List[Dict[str, Any]] = []
    for region in REGION_ORDER:
        schools = sorted(
            list(snapshot.region_schools.get(region, [])),
            key=lambda s: _school_sort_key(s, runtime.national_records, runtime.ranking_map),
        )

        school_rows: List[Dict[str, Any]] = []
        for idx, school in enumerate(schools, start=1):
            key = normalize_school_name(school)
            rec = runtime.national_records.get(key)
            point_rank = runtime.ranking_map.get(key)
            reallocate_to = move_map.get(key)

            school_rows.append(
                {
                    "sort_index": idx,
                    "school": school,
                    "national_rank": rec.rank_order if rec else None,
                    "performance": _format_performance(rec),
                    "point_rank": point_rank,
                    "priority": key in priority_key_set,
                    "possible_reallocation": f"{reallocate_to}赛区" if reallocate_to else "-",
                    "empty": False,
                }
            )

        # 网页固定展示32席位，便于观察缺口。
        target_slots = runtime.config.capacity_per_region
        for idx in range(len(school_rows) + 1, target_slots + 1):
            school_rows.append(
                {
                    "sort_index": idx,
                    "school": "空位",
                    "national_rank": None,
                    "performance": "-",
                    "point_rank": None,
                    "priority": False,
                    "possible_reallocation": "-",
                    "empty": True,
                }
            )

        national_quota = runtime.quota_result.items[region].total_quota
        resurrection_quota = resurrection.get(region, 0)
        volunteers = snapshot.region_counts.get(region, 0)

        regions_payload.append(
            {
                "region": region,
                "region_display": REGION_DISPLAY[region],
                "national_quota": national_quota,
                "resurrection_quota": resurrection_quota,
                "volunteers": volunteers,
                "capacity": runtime.config.capacity_per_region,
                "schools": school_rows,
            }
        )

    total_submitted = sum(snapshot.region_counts.get(region, 0) for region in REGION_ORDER)
    notes = list(runtime.static_notes)
    notes.extend(runtime_notes)
    notes.append("复活赛名额为模拟估算，官方最终分配以组委会公告为准")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_submitted": total_submitted,
        "expected_total": runtime.config.expected_total_teams,
        "regions": regions_payload,
        "notes": notes,
    }


def create_app(config_path: Optional[str] = None) -> Flask:
    root_dir = Path(__file__).resolve().parents[2]
    config = AnalyzerConfig.load(config_path, root_dir)
    runtime = _build_runtime(root_dir, config)

    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
    )

    @app.get("/")
    def index():
        payload = _build_payload(runtime)
        return render_template("index.html", initial_payload=payload)

    @app.get("/api/analysis")
    def api_analysis():
        return jsonify(_build_payload(runtime))

    return app


def main() -> int:
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
