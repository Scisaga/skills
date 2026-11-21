# SVG、CSS 与动画

## 静态页和视觉审批

统一 `1600×900` 透明 SVG 画布，图文主体放在 `template.safe_area`。`template.css` 负责全局背景、标题、Logo、页脚、页码和品牌样式。`init --template-source THEME.css` 将用户样式保存到 `inputs/` 和工作模板。封面、图表及高密度页面应先选 1–4 张作为代表页，确认排版后执行 `approve --stage visual --pages 3,7,10`。

若迁移页的 SVG 已绘制整张幻灯片，可在 `template.css` 用 `.canvas h1, .canvas footer { display: none; }` 采用该页的标题和页脚。

`visual.style_preset` 支持默认项目风格和 `technical-infographic`，主题可为浅色或深色。技术图示优先让读者从主体看清结构、机理和步骤。 [风格规范](technical-infographic-style.md) · [图示案例](visual-reference-cases.md)

## 字体与资源

CSS 可使用 `--font-sans`、`--font-serif`、`--font-mono`。内置思源黑体 SC、思源宋体 SC、Inter 和 JetBrains Mono。页面正文默认以 Inter 排英数、思源黑体排中文，衬线主题选思源宋体，代码选 JetBrains Mono。组装时按实际使用的字族、字重和字符嵌入 WOFF2 子集，并附许可证。

品牌字体可在 `template.css` 通过 `@font-face` 引用项目内已获分发授权的字体。每个字体目录含 `LICENSE.txt`，支持 OTF、TTF 和 WOFF2。可在模板中写入以下 CSS。

```css
@font-face {
  font-family: "Brand Sans";
  src: url("assets/fonts/brand/Brand-Regular.woff2");
  font-weight: 400;
}
:root { --font-sans: "Brand Sans", "Source Han Sans SC", sans-serif; }
```

旧 SVG 的微软雅黑与 Noto Sans CJK SC 映射到思源黑体，宋体映射到思源宋体，Arial 映射到 Inter。项目提供同名字体时优先使用项目版本。图片和样式均使用本地资源或内嵌图像。组装报告列出字体替换涉及的页码。

## 图层和时间点

`animation_manifest.json` 每页提供 `source_svg`。动画页的 `beats[]` 按顺序列出入场分组，首个为 `title`，每页最多六组。效果为 `fade`、`wipe_left`、`wipe_right`、`wipe_up`、`wipe_down`。截图使用淡入。浏览器按 `id` 绑定源 SVG 内的同名 `<g>`。也可以用 `svg_layer_plan.json` 的 `layers[].file` 指定项目内的完整画布 SVG，全页按 `base`、`title` 和各内容组排列，并以原稿摘要校验分层。

```json
{"id":"step_2","effect":"wipe_right","start_ms":3200,"duration_ms":280}
```

`start_ms` 为本页开始后的毫秒数，带旁白时以本页旁白起点为零。`duration_ms` 为入场时长。省略时标题从 0ms 开始，首个内容组从 120ms 开始，后续组每隔 130ms，持续 280ms。手动时间点可放到本页任意有效时点。开始须早于实际音频或本页时长的末端，结束须在过渡前。视频和网页使用相同的动画计算。

## 单页 SVG 改稿

只读目标页 SVG、模板安全区和所选视觉规范。调整目标页后检查 XML、画布、资源引用、文字边界、图文重叠及事实表达，同时查看 `1600×900` 和 `400×225` 渲染。若要同步正式演示，按仍有效的审批与受影响的派生产物重新组装验收。
