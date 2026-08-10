from __future__ import annotations

from cli import build_parser


def test_fill_publish_video_accepts_cover() -> None:
    args = build_parser().parse_args(
        [
            "fill-publish-video",
            "--title-file",
            "/tmp/title.txt",
            "--content-file",
            "/tmp/content.txt",
            "--video",
            "/tmp/video.mp4",
            "--cover",
            "/tmp/cover.png",
        ]
    )

    assert args.cover == "/tmp/cover.png"


def test_publish_video_accepts_cover() -> None:
    args = build_parser().parse_args(
        [
            "publish-video",
            "--title-file",
            "/tmp/title.txt",
            "--content-file",
            "/tmp/content.txt",
            "--video",
            "/tmp/video.mp4",
            "--cover",
            "/tmp/cover.png",
        ]
    )

    assert args.cover == "/tmp/cover.png"
