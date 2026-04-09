from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

from rmuc_analyzer.models import QingflowSnapshot
from rmuc_analyzer.utils import clean_text, normalize_school_name

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_REGION_PATTERN = re.compile(r"(东部赛区|南部赛区|北部赛区)\s*[·•]\s*(\d+)")
_REGION_NAME_MAP = {
    "南部赛区": "南部",
    "东部赛区": "东部",
    "北部赛区": "北部",
}
_VIEW_ID_PATTERN = re.compile(r"/shareView/([A-Za-z0-9]+)")


class QingflowParseError(RuntimeError):
    pass


def _extract_view_id(qingflow_url: str) -> str:
    match = _VIEW_ID_PATTERN.search(qingflow_url)
    if not match:
        raise QingflowParseError("无法从青流链接识别shareView ID")
    return match.group(1)


def _extract_school_from_board_row(row: Dict[str, object]) -> Optional[str]:
    answers = row.get("answers")
    if not isinstance(answers, list):
        return None

    preferred_titles = ("申请学校", "申请人")

    # 优先取明确字段，避免误抓到状态/时间等列。
    for preferred in preferred_titles:
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            title = clean_text(str(answer.get("queTitle", "")))
            if title != preferred:
                continue
            values = answer.get("values")
            if not isinstance(values, list) or not values:
                continue
            value = values[0] if isinstance(values[0], dict) else {}
            data_value = clean_text(str(value.get("dataValue") or value.get("value") or ""))
            if data_value:
                return data_value

    return None


def _fetch_snapshot_with_api(
    qingflow_url: str,
    known_school_map: Dict[str, str],
    timeout_sec: int,
) -> QingflowSnapshot:
    view_id = _extract_view_id(qingflow_url)
    base_info_url = f"https://qingflow.com/api/view/{view_id}/lane/baseInfo?pageNum=1&pageSize=20"
    board_filter_url = f"https://qingflow.com/api/view/{view_id}/lane/boardViewFilter"

    base_resp = requests.get(base_info_url, timeout=timeout_sec, headers=_HEADERS)
    base_resp.raise_for_status()
    base_json = base_resp.json()
    lane_info_list = (
        base_json.get("data", {}).get("laneBaseInfoList")
        if isinstance(base_json, dict)
        else None
    )
    if not isinstance(lane_info_list, list) or not lane_info_list:
        raise QingflowParseError("青流API未返回laneBaseInfoList")

    lane_region_map: Dict[int, str] = {}
    lane_ids: List[int] = []
    for lane_info in lane_info_list:
        if not isinstance(lane_info, dict):
            continue
        lane_name = clean_text(str(lane_info.get("laneName", "")))
        region = _REGION_NAME_MAP.get(lane_name)
        lane_id_raw = lane_info.get("laneId")
        if region is None:
            continue
        try:
            lane_id = int(lane_id_raw)
        except (TypeError, ValueError):
            continue

        lane_region_map[lane_id] = region
        lane_ids.append(lane_id)

    if not lane_ids:
        raise QingflowParseError("青流API未识别到东/南/北赛区lane")

    region_counts: Dict[str, int] = {"南部": 0, "东部": 0, "北部": 0}
    region_schools: Dict[str, List[str]] = {"南部": [], "东部": [], "北部": []}
    seen_by_region = {region: set() for region in region_schools}

    page_num = 1
    max_page = 1

    while page_num <= max_page:
        payload = {
            "filter": {
                "queryKey": None,
                "type": 8,
                "pageNum": page_num,
                "pageSize": 20,
                "sorts": [],
            },
            "laneList": lane_ids,
        }

        board_resp = requests.post(
            board_filter_url,
            json=payload,
            timeout=timeout_sec,
            headers=_HEADERS,
        )
        board_resp.raise_for_status()
        board_json = board_resp.json()
        board_result = (
            board_json.get("data", {}).get("boardViewApplyResult")
            if isinstance(board_json, dict)
            else None
        )
        if not isinstance(board_result, list):
            raise QingflowParseError("青流API未返回boardViewApplyResult")

        for lane in board_result:
            if not isinstance(lane, dict):
                continue

            lane_id_raw = lane.get("laneId")
            try:
                lane_id = int(lane_id_raw)
            except (TypeError, ValueError):
                continue

            region = lane_region_map.get(lane_id)
            if region is None:
                continue

            page_amount = lane.get("pageAmount")
            if isinstance(page_amount, int):
                max_page = max(max_page, page_amount)

            result_amount = lane.get("resultAmount")
            if isinstance(result_amount, int):
                region_counts[region] = max(region_counts[region], result_amount)

            records = lane.get("result")
            if not isinstance(records, list):
                continue

            for row in records:
                if not isinstance(row, dict):
                    continue
                raw_school = _extract_school_from_board_row(row)
                if not raw_school:
                    continue

                normalized = normalize_school_name(raw_school)
                canonical = known_school_map.get(normalized, raw_school)
                if normalized in seen_by_region[region]:
                    continue

                seen_by_region[region].add(normalized)
                region_schools[region].append(canonical)

        page_num += 1

    for region in region_counts:
        if region_counts[region] <= 0:
            region_counts[region] = len(region_schools[region])

    if not any(region_counts.values()):
        raise QingflowParseError("青流API返回为空")

    return QingflowSnapshot(
        fetched_at=datetime.now(timezone.utc),
        region_counts=region_counts,
        region_schools=region_schools,
        source_url=qingflow_url,
        stale=False,
    )


def _fetch_text_with_requests(url: str, timeout_sec: int = 20) -> str:
    response = requests.get(url, timeout=timeout_sec, headers=_HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.get_text("\n")


def _fetch_text_with_playwright(url: str, timeout_sec: int = 20) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise QingflowParseError(
            "requests链路解析失败，且Playwright不可用。请安装playwright并执行 playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        timeout_ms = max(timeout_sec, 45) * 1000
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # 页面存在异步渲染，补充短暂等待以提高稳定性。
        page.wait_for_timeout(3000)
        text = page.inner_text("body")
        browser.close()
    return text


def _extract_region_blocks(text: str) -> List[tuple[str, int, int, int]]:
    matches = list(_REGION_PATTERN.finditer(text))
    if not matches:
        return []

    blocks: List[tuple[str, int, int, int]] = []
    for idx, match in enumerate(matches):
        region_display = match.group(1)
        count = int(match.group(2))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        blocks.append((region_display, count, start, end))
    return blocks


def _extract_schools_from_segment(
    segment: str,
    known_school_map: Dict[str, str],
) -> List[str]:
    schools: List[str] = []
    seen = set()

    lines = [clean_text(line) for line in segment.splitlines()]
    for line in lines:
        if not line:
            continue
        normalized = normalize_school_name(line)
        school = known_school_map.get(normalized)
        if school and school not in seen:
            seen.add(school)
            schools.append(school)

    return schools


def parse_qingflow_snapshot(
    qingflow_url: str,
    known_schools: Optional[Iterable[str]] = None,
    timeout_sec: int = 20,
) -> QingflowSnapshot:
    parse_errors: List[str] = []

    known_school_map: Dict[str, str] = {}
    if known_schools:
        for school in known_schools:
            known_school_map[normalize_school_name(school)] = school

    try:
        return _fetch_snapshot_with_api(qingflow_url, known_school_map, timeout_sec)
    except Exception as exc:
        parse_errors.append(f"API链路失败: {exc}")

    try:
        text = _fetch_text_with_requests(qingflow_url, timeout_sec)
        blocks = _extract_region_blocks(text)
    except Exception as exc:
        blocks = []
        text = ""
        parse_errors.append(f"requests链路失败: {exc}")

    if not blocks:
        parse_errors.append("requests链路未识别到赛区统计块")
        try:
            text = _fetch_text_with_playwright(qingflow_url, timeout_sec)
            blocks = _extract_region_blocks(text)
        except Exception as exc:
            parse_errors.append(f"Playwright链路失败: {exc}")

    if not blocks:
        raise QingflowParseError("；".join(parse_errors) or "未识别到赛区统计块")

    region_counts: Dict[str, int] = {"南部": 0, "东部": 0, "北部": 0}
    region_schools: Dict[str, List[str]] = {"南部": [], "东部": [], "北部": []}

    for region_display, count, start, end in blocks:
        region = _REGION_NAME_MAP[region_display]
        segment = text[start:end]
        schools = _extract_schools_from_segment(segment, known_school_map)
        region_counts[region] = count
        region_schools[region] = schools

    return QingflowSnapshot(
        fetched_at=datetime.now(timezone.utc),
        region_counts=region_counts,
        region_schools=region_schools,
        source_url=qingflow_url,
        stale=False,
    )
