---
name: pdf
description: 使用本地确定性脚本处理 PDF。适用于替换指定页面、保留文本层的普通水印、将 PDF 栅格化为纯图片版并烧录水印、为多页文档添加骑缝章、做基础页面编排、批量处理整个目录，以及图片与 PDF 互转等场景。凡是涉及骑缝章、页替换、抽页删页重排旋转、栅格化、图片化、普通水印、烧录水印、批量 PDF 处理或 PDF/图片互转的请求，都应优先使用这个 skill。
---

# PDF

## 概述

这个 skill 用于处理已经被内置脚本覆盖的 PDF 操作。只要任务命中现有能力，就优先调用这些脚本，而不是临时重写处理逻辑。

## 支持的工作流

1. 用另一个单页 PDF 替换原 PDF 中的某一页。
   优先通过统一入口 `scripts/run.sh replace-page` 调用，底层脚本是 `scripts/pdf_page_replace.py`。

2. 为 PDF 添加保留文本层的普通水印。
   优先通过统一入口 `scripts/run.sh overlay-watermark` 调用，底层脚本是 `scripts/pdf_overlay_watermark.py`。
   当用户需要可搜索、可复制、文件不要明显变大时，优先选这个流程。

3. 将 PDF 栅格化成纯图片版，并烧录平铺水印。
   优先通过统一入口 `scripts/run.sh watermark` 调用，底层脚本是 `scripts/pdf_to_image_pdf_with_watermark.py`。
   当需要去掉可选中文本，或要求水印直接成为页面图像的一部分时，优先选这个流程。

4. 用透明 PNG 为整份文档添加骑缝章。
   优先通过统一入口 `scripts/run.sh seam-seal` 调用，底层脚本是 `scripts/add_qifeng_seal.py`。
   这是处理中文文档骑缝章需求的首选流程。

5. 做基础页面编排。
   优先通过统一入口 `scripts/run.sh page-ops` 调用，底层脚本是 `scripts/pdf_page_ops.py`。
   适用于合并、拆分、抽页、删页、重排、旋转等场景。

6. 批量处理目录中的 PDF。
   优先通过统一入口 `scripts/run.sh batch` 调用，底层脚本是 `scripts/pdf_batch.py`。
   适用于目录级批量普通水印、批量栅格化烧录水印、批量骑缝章。

7. 做图片与 PDF 互转。
   优先通过统一入口 `scripts/run.sh images-to-pdf` 和 `scripts/run.sh pdf-to-images` 调用，底层脚本是 `scripts/pdf_image_convert.py`。
   适用于多图合 PDF、整份 PDF 拆图、指定页导出 PNG/JPEG。

## 工作流

1. 先确认需求属于哪一类。
   - 想保留文本层，只加可见水印时，走普通水印。
   - 想把文本烧进图片层、降低可编辑性时，走栅格化烧录水印。
   - 想处理页顺序或页集合时，走页面编排。
   - 想处理整个目录时，走批量处理。
   - 想在图片和 PDF 之间转换时，走互转工具。
2. 首次使用或环境不确定时，先执行 `bootstrap.sh` 安装依赖并跑环境检查。
3. 日常使用优先走统一入口 `scripts/run.sh`，这样子命令和底层脚本保持一致。
4. 需要准确命令示例或依赖说明时，读取 `references/commands.md`。
5. 除非用户明确要求覆盖源文件，否则输出到新文件。
6. 对于页码范围，统一按 1 基页码理解；支持 `1,3,5-7` 这类写法，`page-ops rotate` 和 `pdf-to-images` 还支持 `all`。
7. 如果需求超出这些工作流，先检查现有脚本输入参数，再判断是小幅扩展更安全，还是另起实现更合适。

## 资源使用

- 首次准备环境时运行 `bootstrap.sh`。
- 统一入口使用 `scripts/run.sh`。
- 环境检查可用 `scripts/run.sh check`。
- 命令模板、参数说明和依赖提醒见 `references/commands.md`。
- 水印文字需要内置中文字体时，使用 `assets/fonts/Consolas-with-Yahei.ttf`。
- 如果用户需要 CLI 暂未暴露的小变体，优先在 `scripts/` 里做小幅补丁。
- 普通水印脚本会保留底层文本层；栅格化脚本不会。
- 批量处理默认输出到新目录，不覆盖输入目录里的原文件。

## 输出规则

- 默认不要改动源 PDF。
- 直接调用底层 Python 脚本时，脚本启动阶段会自动检查缺失依赖并提示如何安装。
- `pdf_page_replace.py` 使用从 1 开始的页码，输出说明里要明确这一点。
- `pdf_page_ops.py` 和 `pdf_image_convert.py` 的页码范围也按 1 基说明。
- 普通水印要明确说明：输出仍保留可搜索、可复制文本层。
- 对于栅格化加水印的结果，要提示文本会变成不可选择。
- 对于骑缝章，如果用户没说放左侧还是右侧，运行前要先确认。
- 对于批量处理，要明确输出目录、文件名后缀以及是否递归子目录。
- 对于图片与 PDF 互转，要说明输出格式、DPI 和页范围。
- 如果用户要 OCR、文本提取、表单填写或真正安全的脱敏涂黑，这不属于当前 skill 已稳定覆盖的范围，除非先扩展脚本。
