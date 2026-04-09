"""Render the Flask dashboard to a static site under ``docs/``.

Produces ``docs/index.html`` (template rendered with the current payload baked
in) and ``docs/data.json`` (same payload for in-browser auto-refresh). The
output is suitable for hosting on GitHub Pages.

Usage::

    PYTHONPATH=src python scripts/build_static_site.py [--config config/config.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import rmuc_analyzer.web as web  # noqa: E402
from rmuc_analyzer.config import AnalyzerConfig  # noqa: E402


ORIGINAL_FETCH = 'fetch("/api/analysis", { cache: "no-store" })'
STATIC_FETCH = 'fetch("./data.json?t=" + Date.now(), { cache: "no-store" })'

# Link the static GH Pages mirror to the always-on HF Space so viewers who
# need per-request freshness can jump straight there.
LIVE_SPACE_URL = "https://liuskywalkerjskd-wheretogo.hf.space/"

ORIGINAL_TOOLBAR = (
    '<div class="toolbar">\n'
    '          <button class="btn" id="refreshBtn" type="button">立即刷新</button>\n'
    '        </div>'
)
STATIC_TOOLBAR = (
    '<div class="toolbar">\n'
    '          <button class="btn" id="refreshBtn" type="button">刷新快照</button>\n'
    f'          <a class="btn" href="{LIVE_SPACE_URL}" target="_blank" rel="noopener" '
    'style="background:#ffd4b8;">⚡ 真·实时版本</a>\n'
    '        </div>'
)

ORIGINAL_SUB = (
    '<p class="sub">排序规则：先按去年国赛排名，再按积分排名；被预测调剂的队伍会虚化并标注调入/调出状态。</p>'
)
STATIC_SUB = (
    '<p class="sub">排序规则：先按去年国赛排名，再按积分排名；被预测调剂的队伍会虚化并标注调入/调出状态。'
    '<br><span style="opacity:0.85;font-size:12px;">'
    '本页面为 GitHub Pages 静态快照（每 30 分钟由 Actions 刷新一次）。'
    f'需要秒级实时数据请点击右上角「⚡ 真·实时版本」前往 <a href="{LIVE_SPACE_URL}" '
    'target="_blank" rel="noopener" style="color:#ffd4b8;">Hugging Face Space</a>。'
    '</span></p>'
)


def build_payload(config_path: str) -> dict:
    config = AnalyzerConfig.load(config_path, ROOT)
    runtime = web._build_runtime(ROOT, config)
    return web._build_payload(runtime)


def render_html(payload: dict) -> str:
    template_dir = ROOT / "src" / "rmuc_analyzer" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    html = env.get_template("index.html").render(initial_payload=payload)

    for marker, label in (
        (ORIGINAL_FETCH, "fetch line"),
        (ORIGINAL_TOOLBAR, "toolbar block"),
        (ORIGINAL_SUB, "subtitle line"),
    ):
        if marker not in html:
            raise RuntimeError(
                f"Template {label} not found; static patch is out of sync with "
                "src/rmuc_analyzer/templates/index.html"
            )

    html = html.replace(ORIGINAL_FETCH, STATIC_FETCH)
    html = html.replace(ORIGINAL_TOOLBAR, STATIC_TOOLBAR)
    html = html.replace(ORIGINAL_SUB, STATIC_SUB)
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/config.json")
    parser.add_argument("--out-dir", default="docs")
    args = parser.parse_args()

    payload = build_payload(args.config)
    html = render_html(payload)

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / ".nojekyll").write_text("")

    print(
        f"Built static site: regions={len(payload['regions'])}, "
        f"submitted={payload['total_submitted']}/{payload['expected_total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
