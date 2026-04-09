from pathlib import Path

import pytest

from rmuc_analyzer.sources import robomaster


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_fetch_html_supports_local_file(tmp_path: Path):
    sample = tmp_path / "sample.html"
    sample.write_text("<html>ok</html>", encoding="utf-8")

    html = robomaster.fetch_html(str(sample), timeout_sec=1)

    assert html == "<html>ok</html>"


def test_localize_announcement_sources_downloads_to_local(monkeypatch, tmp_path: Path):
    url = "https://www.robomaster.com/zh-CN/resource/pages/announcement/1909"

    def fake_get(target_url, timeout, headers):
        assert target_url == url
        return _DummyResponse("<html>remote-1909</html>")

    monkeypatch.setattr(robomaster.requests, "get", fake_get)

    localized = robomaster.localize_announcement_sources(
        {"teams_2026": url},
        root_dir=tmp_path,
        timeout_sec=5,
        local_dir="data/announcements",
        local_only=False,
    )

    local_path = Path(localized["teams_2026"])
    assert local_path.exists()
    assert local_path.name.endswith("1909.html")
    assert local_path.read_text(encoding="utf-8") == "<html>remote-1909</html>"


def test_localize_announcement_sources_local_only_requires_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        robomaster.localize_announcement_sources(
            {"teams_2026": "https://www.robomaster.com/zh-CN/resource/pages/announcement/1909"},
            root_dir=tmp_path,
            timeout_sec=5,
            local_dir="data/announcements",
            local_only=True,
        )


def test_localize_announcement_sources_uses_cached_file_on_download_failure(monkeypatch, tmp_path: Path):
    url = "https://www.robomaster.com/zh-CN/resource/pages/announcement/1910"
    target_dir = tmp_path / "data" / "announcements"
    target_dir.mkdir(parents=True, exist_ok=True)
    cached = target_dir / "rules_2026_1910.html"
    cached.write_text("<html>cached-1910</html>", encoding="utf-8")

    def failing_get(*args, **kwargs):
        raise RuntimeError("network failed")

    monkeypatch.setattr(robomaster.requests, "get", failing_get)

    localized = robomaster.localize_announcement_sources(
        {"rules_2026": url},
        root_dir=tmp_path,
        timeout_sec=5,
        local_dir="data/announcements",
        local_only=False,
    )

    assert Path(localized["rules_2026"]).read_text(encoding="utf-8") == "<html>cached-1910</html>"
