# HTML 组装和导出

## 运行环境

```bash
bash skills/slides/scripts/run.sh bootstrap --stage static
bash skills/slides/scripts/run.sh doctor --stage static
```

`static` 安装 Playwright Chromium、FontTools 和内置字体，`audio` 安装语音依赖。`narrated` 安装两者及用于拼接旁白的 FFmpeg。`video` 安装页面工具、FFmpeg 和 ffprobe，可用来导出已组装的演示。省略阶段安装全部。Linux 缺 Chromium 系统库时，用虚拟环境的 Python 运行 `python -m playwright install --with-deps chromium`。Windows 的入口为 `scripts/run.ps1`。

## 可双击打开的演示

`assemble-html --project PROJECT` 使用当前审批和 SVG 资源生成演示目录与同名 ZIP。打开 `index.html` 后，可用左右键翻页，空格开始或暂停，`F` 全屏。阅读按钮展开页面终态。进度条可跳到任意时间点。把演示目录上传静态服务器也可播放。

CSS、字体子集和图片引用编译到页面内。带旁白时，`narration.mp3` 和 `index.html` 同目录。分发时提供完整目录或 ZIP，包括使用的字体许可证。

## 导出

```bash
bash skills/slides/scripts/run.sh export-pages --project PROJECT \
  --pages 2,4-6 --format pdf --output selected.pdf
bash skills/slides/scripts/run.sh export-pages --project PROJECT \
  --format png --output page-images
bash skills/slides/scripts/run.sh export-video --project PROJECT
```

选页默认为全稿，PDF 与图像直接渲染各页终态。PNG 和 JPG 输出到目录，单页也可指定同格式文件。PDF 每页尺寸为对应的 16:9 画布。网页、PDF 和视频使用同一 Chromium 渲染与随包字体。网页静态验收须通过后再导出。

视频使用 `1920×1080`、30 fps、H.264 和 BT.709 limited range。按帧序号渲染时间轴，复用静止画面，带旁白时合入 AAC。无旁白的每页停留由 `seconds_per_page` 决定，默认为 5 秒。旁白视频要求当前 standard QA。FFmpeg 编码后用 ffprobe 核对轨道、帧率、分辨率、色彩范围和时长。导出文件与 `video/video_export.json` 在检查通过后发布。

## 一次性迁移旧项目

```bash
bash skills/slides/scripts/run.sh migrate-html --project OLD --output NEW \
  --template-source theme.css
```

所需输入是含有 `project.json`、原稿、逐页稿和 SVG 的 v2 项目目录。原项目只读取。静态和动画项目对应转换，旁白和旧视频项目变为 `narrated_html`。使用默认 CSS 或另行提供品牌模板。`video/html_migration.json` 记录待补素材、图层映射、字体替换和有效审批。复用已生成的逐页 MP3 前运行 audio QA。重新确认 HTML 样页，再批准视觉、组装和验收。
