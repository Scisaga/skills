# PDF 命令参考

## 初始化与检查

```bash
bash skills/pdf/scripts/bootstrap.sh
bash skills/pdf/scripts/run.sh doctor
```

## 替换页面

```bash
bash skills/pdf/scripts/run.sh replace-page source.pdf replacement.pdf 3 output.pdf
```

## 普通水印

```bash
bash skills/pdf/scripts/run.sh overlay-watermark source.pdf output.pdf \
  --text "CONFIDENTIAL" \
  --font-size 28 \
  --opacity 0.18
```

## 栅格化并烧录水印

```bash
bash skills/pdf/scripts/run.sh watermark source.pdf output.pdf \
  --text "内部流转" \
  --dpi 200
```

## 骑缝章

```bash
bash skills/pdf/scripts/run.sh seam-seal source.pdf seal.png output.pdf --side right
```

## 页面编排

```bash
bash skills/pdf/scripts/run.sh page-ops merge out/merged.pdf a.pdf b.pdf c.pdf
bash skills/pdf/scripts/run.sh page-ops split source.pdf out/pages
bash skills/pdf/scripts/run.sh page-ops extract source.pdf out/extract.pdf 1,3,5-7
bash skills/pdf/scripts/run.sh page-ops remove source.pdf out/removed.pdf 2,4
bash skills/pdf/scripts/run.sh page-ops reorder source.pdf out/reordered.pdf 3,1,2
bash skills/pdf/scripts/run.sh page-ops rotate source.pdf out/rotated.pdf 90 --pages 1-2
```

## 批量处理

```bash
bash skills/pdf/scripts/run.sh batch overlay-watermark in-pdfs out-pdfs --text "已审核"
bash skills/pdf/scripts/run.sh batch rasterize-watermark in-pdfs out-pdfs --text "内部"
bash skills/pdf/scripts/run.sh batch seam-seal in-pdfs out-pdfs seal.png --side right
```

## 图片与 PDF 互转

```bash
bash skills/pdf/scripts/run.sh images-to-pdf out/album.pdf a.png b.jpg c.jpeg --dpi 150
bash skills/pdf/scripts/run.sh pdf-to-images source.pdf out/images --pages 1,3-4 --dpi 200 --format png
```
