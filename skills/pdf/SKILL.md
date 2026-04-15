---
name: pdf
description: 使用本地确定性脚本处理 PDF。适用于替换页面、普通水印、栅格化烧录水印、骑缝章、抽页删页重排旋转、批量处理目录，以及 PDF 和图片互转等场景。
---

# PDF

## 概述

这个 skill 只覆盖已经沉淀进 `skills/pdf/scripts/` 的稳定工作流。能直接复用脚本时，优先走现有入口，不临时重写处理逻辑。

## 工作流

1. 首次使用或环境不确定时，先运行 `bash skills/pdf/scripts/bootstrap.sh`
2. 日常统一走 `bash skills/pdf/scripts/run.sh`
3. 只做环境检查时，运行 `bash skills/pdf/scripts/run.sh doctor`
4. 需要命令模板和参数说明时，读 `references/commands.md`
5. 除非用户明确要求覆盖原文件，否则输出到新文件或新目录

## 命令模式

```bash
bash skills/pdf/scripts/run.sh doctor
bash skills/pdf/scripts/run.sh replace-page source.pdf replacement.pdf 3 output.pdf
bash skills/pdf/scripts/run.sh overlay-watermark source.pdf output.pdf --text "CONFIDENTIAL"
bash skills/pdf/scripts/run.sh watermark source.pdf output.pdf --text "内部流转"
bash skills/pdf/scripts/run.sh seam-seal source.pdf seal.png output.pdf
bash skills/pdf/scripts/run.sh page-ops merge out/merged.pdf a.pdf b.pdf
bash skills/pdf/scripts/run.sh batch overlay-watermark in-pdfs out-pdfs --text "已审核"
```

## 资源使用

- 环境准备：`scripts/bootstrap.sh`
- 统一入口：`scripts/run.sh`
- 环境检查：`scripts/doctor.py`
- 详细参数和更多示例：`references/commands.md`
- 中文字体资源：`assets/fonts/Consolas-with-Yahei.ttf`

## 输出规则

- 页码说明统一按 1 基页码
- 普通水印保留文本层，栅格化水印不会保留文本层
- 骑缝章如未指定左右侧，执行前先确认
- 批量处理要明确输出目录、文件名后缀和是否递归

