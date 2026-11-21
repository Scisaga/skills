"""Open a presentation with the same Chromium settings for QA and exports."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


@contextmanager
def browser_page(width: int = 1600, height: int = 900):
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 Playwright，请运行 bootstrap --stage static") from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--force-color-profile=srgb"])
            try:
                context = browser.new_context(
                    viewport={"width": width, "height": height}, device_scale_factor=1,
                    locale="zh-CN", service_workers="block",
                )
                context.route(
                    "**/*",
                    lambda route: route.continue_()
                    if route.request.url.startswith(("file:", "data:", "about:"))
                    else route.abort(),
                )
                yield context.new_page()
            finally:
                browser.close()
    except Error as exc:
        raise RuntimeError(f"Chromium 渲染失败，请检查 bootstrap 安装与页面资源: {exc}") from exc


def open_deck(page, index: Path) -> None:
    response = page.goto(index.resolve().as_uri(), wait_until="load")
    if response is not None and not response.ok:
        raise RuntimeError(f"无法打开离线演示 {index}")
    page.evaluate("""async () => {
        if (!window.slides) throw new Error("播放器没有加载");
        await Promise.all([...document.fonts].map(face => face.load()));
        await document.fonts.ready;
        const failed = [...document.fonts].filter(font => font.status === "error");
        if (failed.length) throw new Error("字体加载失败 " + failed.map(f => f.family).join(", "));
        await Promise.all([...document.images].map(image => image.decode()));
    }""")
