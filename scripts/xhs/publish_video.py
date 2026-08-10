"""视频发布，对应 Go xiaohongshu/publish_video.go。"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .cdp import Page
from .errors import PublishError, UploadTimeoutError
from .publish import (
    _click_publish_tab,
    _find_content_element,
    _input_tags,
    _navigate_to_publish_page,
    _set_schedule_publish,
    _set_visibility,
)
from .selectors import (
    FILE_INPUT,
    PUBLISH_BUTTON,
    TITLE_INPUT,
    UPLOAD_INPUT,
    VIDEO_COVER_FILE_INPUT,
    VIDEO_COVER_OPEN,
    VIDEO_COVER_UPLOAD_BUTTON,
)
from .types import PublishVideoContent

logger = logging.getLogger(__name__)

EDITOR_READY_ATTEMPTS = 3
EDITOR_READY_INTERVAL = 1.0
PUBLISH_READY_ATTEMPTS = 3
PUBLISH_READY_INTERVAL = 1.0


def publish_video_content(page: Page, content: PublishVideoContent) -> None:
    """发布视频内容（填写表单 + 点击发布）。

    Args:
        page: CDP 页面对象。
        content: 视频发布内容。

    Raises:
        PublishError: 发布失败。
        UploadTimeoutError: 上传/处理超时。
    """
    fill_publish_video_form(page, content)
    click_publish_video_button(page)


def fill_publish_video_form(page: Page, content: PublishVideoContent) -> dict[str, Any]:
    """填写视频发布表单，不点击发布按钮。

    Args:
        page: CDP 页面对象。
        content: 视频发布内容。

    Raises:
        PublishError: 填写失败。
        UploadTimeoutError: 上传/处理超时。

    Returns:
        可供自动化调用方判断预填进度的结构化状态。
    """
    if not content.video_path:
        raise PublishError("视频不能为空")

    # 导航到发布页
    _navigate_to_publish_page(page)

    # 点击"上传视频" TAB
    _click_publish_tab(page, "上传视频")
    time.sleep(1)

    # 上传视频
    upload_state = _upload_video(page, content.video_path)

    # 填写表单（不点击发布）
    _fill_publish_video_form(
        page,
        content.title,
        content.content,
        content.tags,
        content.schedule_time,
        content.visibility,
    )

    cover_applied = False
    if content.cover_path:
        cover_applied = _set_video_cover(page, content.cover_path)

    return {
        "video_selected": True,
        "editor_ready": upload_state["editor_ready"],
        "filename_visible": upload_state["filename_visible"],
        "hd_detected": upload_state["hd_detected"],
        "title_filled": True,
        "tags_requested": content.tags,
        "cover_requested": bool(content.cover_path),
        "cover_applied": cover_applied,
        "visibility_requested": content.visibility or "公开可见",
        "publish_clicked": False,
    }


def click_publish_video_button(page: Page) -> None:
    """点击视频发布按钮。

    Args:
        page: CDP 页面对象。
    """
    _wait_for_publish_button_clickable(page)
    page.click_element(PUBLISH_BUTTON)
    time.sleep(3)
    logger.info("视频发布完成")


def _upload_video(page: Page, video_path: str) -> dict[str, bool]:
    """选择视频文件并用有限检查确认编辑器可用。"""
    if not os.path.exists(video_path):
        raise PublishError(f"视频文件不存在: {video_path}")
    if not os.path.isabs(video_path):
        raise PublishError("视频文件必须使用绝对路径")

    # 查找上传输入框
    selector = UPLOAD_INPUT if page.has_element(UPLOAD_INPUT) else FILE_INPUT
    page.set_file_input(selector, [video_path])

    # 小红书视频上传没有可靠完成回调。只检查编辑表单是否出现，不等待发布按钮。
    state = _wait_for_video_editor_ready(page, os.path.basename(video_path))
    logger.info("视频已进入编辑页: %s", state)
    return state


def _wait_for_video_editor_ready(page: Page, filename: str) -> dict[str, bool]:
    """最多检查三次编辑器状态，避免等待不存在的视频上传回调。"""
    last_state = {"editor_ready": False, "filename_visible": False, "hd_detected": False}

    for attempt in range(EDITOR_READY_ATTEMPTS):
        state = page.evaluate(
            f"""
            (() => {{
                const title = document.querySelector({_js_str(TITLE_INPUT)});
                const titleReady = Boolean(title && title.getBoundingClientRect().width > 0);
                const bodyText = document.body ? document.body.innerText : '';
                return {{
                    editor_ready: titleReady,
                    filename_visible: bodyText.includes({_js_str(filename)}),
                    hd_detected: bodyText.includes('检测为高清视频')
                }};
            }})()
            """
        )
        if isinstance(state, dict):
            last_state = {
                "editor_ready": bool(state.get("editor_ready")),
                "filename_visible": bool(state.get("filename_visible")),
                "hd_detected": bool(state.get("hd_detected")),
            }
        if last_state["editor_ready"]:
            return last_state
        if attempt < EDITOR_READY_ATTEMPTS - 1:
            time.sleep(EDITOR_READY_INTERVAL)

    raise UploadTimeoutError(
        "视频文件已提交，但编辑表单在有限检查内未出现。请保留当前页面并改用 Chrome "
        "继续预填；不要重新上传视频。"
    )


def _wait_for_publish_button_clickable(page: Page) -> None:
    """有限检查发布按钮，避免等待不存在的视频处理回调。"""
    for attempt in range(PUBLISH_READY_ATTEMPTS):
        clickable = page.evaluate(
            f"""
            (() => {{
                const btn = document.querySelector({_js_str(PUBLISH_BUTTON)});
                if (!btn) return false;
                const rect = btn.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                if (btn.disabled) return false;
                if (btn.classList.contains('disabled')) return false;
                return true;
            }})()
            """
        )
        if clickable:
            return
        if attempt < PUBLISH_READY_ATTEMPTS - 1:
            time.sleep(PUBLISH_READY_INTERVAL)

    raise UploadTimeoutError(
        "发布按钮尚不可用。请保留当前页面，稍后重试确认发布；不要重新上传视频。"
    )


def _set_video_cover(page: Page, cover_path: str) -> bool:
    """上传自定义视频封面并应用。"""
    if not os.path.exists(cover_path):
        raise PublishError(f"封面文件不存在: {cover_path}")
    if not os.path.isabs(cover_path):
        raise PublishError("封面文件必须使用绝对路径")

    if not page.has_element(VIDEO_COVER_OPEN):
        raise PublishError("没有找到视频封面设置入口")
    page.click_element(VIDEO_COVER_OPEN)

    if not _wait_for_element_bounded(page, VIDEO_COVER_UPLOAD_BUTTON):
        raise PublishError("视频封面编辑器未打开")
    if not page.has_element(VIDEO_COVER_FILE_INPUT):
        raise PublishError("没有找到视频封面文件输入框")

    page.set_file_input(VIDEO_COVER_FILE_INPUT, [cover_path])

    for attempt in range(EDITOR_READY_ATTEMPTS):
        button_box = page.evaluate(
            """
            (() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const button = buttons.find((item) => {
                    if (item.textContent.trim() !== '确定' || item.disabled) return false;
                    const rect = item.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
                if (!button) return null;
                const rect = button.getBoundingClientRect();
                return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
            })()
            """
        )
        if isinstance(button_box, dict):
            page.mouse_click(float(button_box["x"]), float(button_box["y"]))
            if _wait_for_cover_dialog_closed(page):
                logger.info("视频封面已应用: %s", cover_path)
                return True
        if attempt < EDITOR_READY_ATTEMPTS - 1:
            time.sleep(EDITOR_READY_INTERVAL)

    raise PublishError("视频封面已选择，但未能确认应用")


def _wait_for_element_bounded(page: Page, selector: str) -> bool:
    """有限检查元素是否出现。"""
    for attempt in range(EDITOR_READY_ATTEMPTS):
        if page.has_element(selector):
            return True
        if attempt < EDITOR_READY_ATTEMPTS - 1:
            time.sleep(EDITOR_READY_INTERVAL)
    return False


def _wait_for_cover_dialog_closed(page: Page) -> bool:
    """有限检查封面弹窗是否关闭。"""
    for attempt in range(EDITOR_READY_ATTEMPTS):
        is_open = page.evaluate(
            """
            (() => Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
                .some((item) => item.textContent.trim() === '设置封面'))()
            """
        )
        if not is_open:
            return True
        if attempt < EDITOR_READY_ATTEMPTS - 1:
            time.sleep(EDITOR_READY_INTERVAL)
    return False


def _fill_publish_video_form(
    page: Page,
    title: str,
    content: str,
    tags: list[str],
    schedule_time: str | None,
    visibility: str,
) -> None:
    """填写视频表单（不点击发布）。"""
    # 标题
    page.input_text(TITLE_INPUT, title)
    time.sleep(1)

    # 正文 + 标签
    content_selector = _find_content_element(page)
    page.input_content_editable(content_selector, content)

    # 回点标题
    time.sleep(1)
    page.click_element(TITLE_INPUT)

    if tags:
        _input_tags(page, content_selector, tags)
    time.sleep(1)

    # 定时发布
    if schedule_time:
        _set_schedule_publish(page, schedule_time)

    # 可见范围
    _set_visibility(page, visibility)

    logger.info("视频表单填写完成，等待确认发布")


def _js_str(s: str) -> str:
    """将 Python 字符串转为 JS 字面量。"""
    import json

    return json.dumps(s)
