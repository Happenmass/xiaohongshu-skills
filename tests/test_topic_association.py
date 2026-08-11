from __future__ import annotations

import pytest
from xhs.errors import PublishError
from xhs.publish import _input_single_tag, _input_tags


class FakeTopicPage:
    def __init__(self, points: list[object] | None = None) -> None:
        self.points = list(points or [])
        self.typed: list[str] = []
        self.mouse_clicks: list[tuple[float, float]] = []
        self.evaluations: list[str] = []

    def type_text(self, text: str, delay_ms: int = 0) -> None:
        self.typed.append(text)

    def evaluate(self, expression: str) -> object:
        self.evaluations.append(expression)
        if "const container" in expression:
            return self.points.pop(0) if self.points else None
        return 1

    def mouse_click(self, x: float, y: float) -> None:
        self.mouse_clicks.append((x, y))


def test_single_tag_clicks_exact_system_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakeTopicPage([None, {"x": 12, "y": 34}])
    monkeypatch.setattr("xhs.publish.time.sleep", lambda _: None)
    monkeypatch.setattr("xhs.publish.TAG_SUGGESTION_INTERVAL", 0)

    associated = _input_single_tag(page, "div.ql-editor", "Agent记忆")

    assert associated is True
    assert "".join(page.typed) == "#Agent记忆"
    assert page.mouse_clicks == [(12.0, 34.0)]
    suggestion_script = next(x for x in page.evaluations if "const container" in x)
    assert "firstLine === target" in suggestion_script


def test_single_tag_does_not_fallback_to_plain_hashtag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakeTopicPage()
    monkeypatch.setattr("xhs.publish.time.sleep", lambda _: None)
    monkeypatch.setattr("xhs.publish.TAG_SUGGESTION_INTERVAL", 0)

    associated = _input_single_tag(page, "div.ql-editor", "不存在的话题")

    assert associated is False
    assert "".join(page.typed) == "#不存在的话题"
    assert page.mouse_clicks == []


def test_input_tags_stops_when_topic_is_not_associated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakeTopicPage()
    monkeypatch.setattr("xhs.publish.time.sleep", lambda _: None)
    monkeypatch.setattr("xhs.publish._input_single_tag", lambda *_: False)

    with pytest.raises(PublishError, match="未完成关联"):
        _input_tags(page, "div.ql-editor", ["Agent记忆"])
