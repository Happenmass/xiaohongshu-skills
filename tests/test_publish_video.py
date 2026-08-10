from __future__ import annotations

from pathlib import Path

import pytest
from xhs.errors import PublishError, UploadTimeoutError
from xhs.publish_video import (
    _set_video_cover,
    _upload_video,
    _wait_for_publish_button_clickable,
    _wait_for_video_editor_ready,
)
from xhs.selectors import (
    PUBLISH_BUTTON,
    UPLOAD_INPUT,
    VIDEO_COVER_FILE_INPUT,
    VIDEO_COVER_OPEN,
    VIDEO_COVER_UPLOAD_BUTTON,
)


class FakePage:
    def __init__(self, states: list[object] | None = None) -> None:
        self.states = list(states or [])
        self.evaluations: list[str] = []
        self.files: list[tuple[str, list[str]]] = []
        self.clicks: list[str] = []
        self.mouse_clicks: list[tuple[float, float]] = []

    def evaluate(self, expression: str) -> object:
        self.evaluations.append(expression)
        if "const buttons" in expression:
            return {"x": 10, "y": 20}
        if "h1,h2,h3,h4,h5,h6" in expression:
            return False
        if self.states:
            return self.states.pop(0)
        return False

    def has_element(self, selector: str) -> bool:
        return selector in {
            UPLOAD_INPUT,
            VIDEO_COVER_OPEN,
            VIDEO_COVER_UPLOAD_BUTTON,
            VIDEO_COVER_FILE_INPUT,
        }

    def set_file_input(self, selector: str, files: list[str]) -> None:
        self.files.append((selector, files))

    def click_element(self, selector: str) -> None:
        self.clicks.append(selector)

    def mouse_click(self, x: float, y: float) -> None:
        self.mouse_clicks.append((x, y))


def test_video_upload_stops_when_editor_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    page = FakePage(
        [
            {"editor_ready": False, "filename_visible": True, "hd_detected": False},
            {"editor_ready": True, "filename_visible": True, "hd_detected": True},
        ]
    )
    monkeypatch.setattr("xhs.publish_video.EDITOR_READY_INTERVAL", 0)

    state = _upload_video(page, str(video))

    assert state == {"editor_ready": True, "filename_visible": True, "hd_detected": True}
    assert page.files == [(UPLOAD_INPUT, [str(video)])]
    assert not any(PUBLISH_BUTTON in expression for expression in page.evaluations)


def test_video_editor_check_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage([False, False, False])
    monkeypatch.setattr("xhs.publish_video.EDITOR_READY_INTERVAL", 0)

    with pytest.raises(UploadTimeoutError, match="不要重新上传视频"):
        _wait_for_video_editor_ready(page, "video.mp4")

    assert len(page.evaluations) == 3


def test_publish_button_check_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage([False, False, False])
    monkeypatch.setattr("xhs.publish_video.PUBLISH_READY_INTERVAL", 0)

    with pytest.raises(UploadTimeoutError, match="不要重新上传视频"):
        _wait_for_publish_button_clickable(page)

    assert len(page.evaluations) == 3


def test_custom_video_cover_is_applied(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"png")
    page = FakePage()

    applied = _set_video_cover(page, str(cover))

    assert applied is True
    assert page.clicks == [VIDEO_COVER_OPEN]
    assert page.files == [(VIDEO_COVER_FILE_INPUT, [str(cover)])]
    assert page.mouse_clicks == [(10.0, 20.0)]


def test_cover_path_must_be_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage()
    monkeypatch.setattr("xhs.publish_video.os.path.exists", lambda _: True)

    with pytest.raises(PublishError, match="绝对路径"):
        _set_video_cover(page, "cover.png")
