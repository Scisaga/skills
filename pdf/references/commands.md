# PDF Commands

Read this file when you need the exact script entry points, key arguments, or dependency reminders.

## Bootstrap

首次使用先执行：

```bash
bash pdf/bootstrap.sh
```

- 会安装 `pdf/requirements.txt` 里的依赖。
- 会自动创建或复用 `pdf/.venv`，避免系统 Python 的外部管理限制。
- 会执行环境检查，确认各工作流依赖和内置字体是否就绪。

## Unified entry

优先使用统一入口：

```bash
bash pdf/scripts/run.sh check
```

## Scripts

### Replace a page

```bash
bash pdf/scripts/run.sh replace-page source.pdf replacement.pdf 3 output.pdf
```

- `replacement.pdf` must contain exactly one page.
- The page number is 1-based.
- Dependency: `PyMuPDF`
- 也可以直接调用 `python3 pdf/scripts/pdf_page_replace.py ...`，脚本启动时会自动提示缺失依赖。

### Add a visible watermark while keeping the text layer

```bash
bash pdf/scripts/run.sh overlay-watermark source.pdf output.pdf \
  --wm-text "Internal Use Only" \
  --wm-font pdf/assets/fonts/Consolas-with-Yahei.ttf \
  --wm-font-size 42 \
  --wm-color "#666666" \
  --wm-opacity 0.12 \
  --wm-angle -30 \
  --wm-spacing 220
```

- Dependency: `PyPDF2`, `reportlab`, `Pillow`
- Use this when the PDF should remain searchable/selectable and the watermark only needs to be visibly overlaid.
- `--wm-img` can be used instead of `--wm-text` to tile an image watermark.
- 也可以直接调用 `python3 pdf/scripts/pdf_overlay_watermark.py ...`，脚本启动时会自动提示缺失依赖。

### Rasterize and burn in a text watermark

```bash
bash pdf/scripts/run.sh watermark source.pdf output.pdf \
  --dpi 225 \
  --wm-text "Internal Use Only" \
  --wm-font pdf/assets/fonts/Consolas-with-Yahei.ttf \
  --wm-font-size 60 \
  --wm-opacity 0.08 \
  --wm-angle -30 \
  --wm-spacing 520 \
  --image-format jpeg \
  --jpeg-quality 88
```

- Dependency: `PyMuPDF`, `Pillow`
- Use this when the result should be image-only and the watermark should be hard-burned into the page image.
- `--wm-img` can be used instead of `--wm-text` to tile an image watermark.
- `--password` can be used for encrypted PDFs.
- 也可以直接调用 `python3 pdf/scripts/pdf_to_image_pdf_with_watermark.py ...`，脚本启动时会自动提示缺失依赖。

### Add a seam seal

```bash
bash pdf/scripts/run.sh seam-seal source.pdf seal.png output.pdf \
  --side right \
  --height-ratio 0.8 \
  --dpi 560
```

- Dependency: `PyPDF2`, `reportlab`, `Pillow`
- `seal.png` should be a transparent PNG.
- The script slices the seal into vertical strips and distributes them across all pages.
- 也可以直接调用 `python3 pdf/scripts/add_qifeng_seal.py ...`，脚本启动时会自动提示缺失依赖。

### Page operations

```bash
bash pdf/scripts/run.sh page-ops merge out/merged.pdf a.pdf b.pdf c.pdf
bash pdf/scripts/run.sh page-ops split source.pdf out/pages
bash pdf/scripts/run.sh page-ops extract source.pdf out/extract.pdf 1,3,5-7
bash pdf/scripts/run.sh page-ops remove source.pdf out/removed.pdf 2,4
bash pdf/scripts/run.sh page-ops reorder source.pdf out/reordered.pdf 3,1,2
bash pdf/scripts/run.sh page-ops rotate source.pdf out/rotated.pdf 90 --pages 1-2
```

- Dependency: `PyPDF2`
- All page ranges are 1-based and support forms like `1,3,5-7`.
- `rotate` supports `--pages all`.
- 也可以直接调用 `python3 pdf/scripts/pdf_page_ops.py ...`，脚本启动时会自动提示缺失依赖。

### Batch processing

```bash
bash pdf/scripts/run.sh batch overlay-watermark in-pdfs out-pdfs \
  --recursive \
  --wm-text "Draft"

bash pdf/scripts/run.sh batch rasterize-watermark in-pdfs out-pdfs \
  --suffix -burned \
  --wm-text "Internal Use Only" \
  --dpi 225

bash pdf/scripts/run.sh batch seam-seal in-pdfs out-pdfs seal.png \
  --side right
```

- Dependency: `PyMuPDF`, `Pillow`, `PyPDF2`, `reportlab`
- Outputs go to a separate directory and keep the relative folder structure when `--recursive` is used.
- Default suffixes are `-overlay`, `-rasterized`, `-sealed`.
- 也可以直接调用 `python3 pdf/scripts/pdf_batch.py ...`，脚本启动时会自动提示缺失依赖。

### Images and PDF conversion

```bash
bash pdf/scripts/run.sh images-to-pdf out/album.pdf a.png b.jpg c.jpeg --dpi 150
bash pdf/scripts/run.sh pdf-to-images source.pdf out/images --pages 1,3-4 --dpi 200 --format png
```

- Dependency: `PyMuPDF`, `Pillow`
- `images-to-pdf` creates one PDF page per input image.
- `pdf-to-images` supports page-range export and PNG/JPEG output.
- 也可以直接调用 `python3 pdf/scripts/pdf_image_convert.py ...`，脚本启动时会自动提示缺失依赖。

## Notes

- The scripts are local utilities, so prefer them over online PDF services.
- For user-facing explanations, call out whether the output keeps text selectable.
- `overlay-watermark` keeps the text layer, while `watermark` turns the result into an image-only PDF.
- If a task needs OCR, text extraction, form filling, or redaction, that is outside the current skill scope and may require extending the skill first.
