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


def build_payload(config_path: str) -> dict:
    config = AnalyzerConfig.load(config_path, ROOT)
    runtime = web._build_runtime(ROOT, config)
    return web._build_payload(runtime)


def render_html(payload: dict) -> str:
    template_dir = ROOT / "src" / "rmuc_analyzer" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    html = env.get_template("index.html").render(initial_payload=payload)
    if ORIGINAL_FETCH not in html:
        raise RuntimeError(
            "Template fetch line not found; the static patch is out of sync with "
            "src/rmuc_analyzer/templates/index.html"
        )
    return html.replace(ORIGINAL_FETCH, STATIC_FETCH)


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
