---
name: sci-color
description: Terminal-based SCI color palette browser. Use when user asks about color schemes, scientific plotting colors, beautiful palettes, journal-grade colors, chart aesthetics. Active if user says "color", "palette", "配色", "颜色", or "sci-color".
license: MIT
---

# SCI Color Palette Browser

55 journal-grade palettes. ALL output is pure terminal ANSI — no PNG, no GUI, no matplotlib needed for viewing.

## Commands

```bash
python <scripts_dir>/sci_colors.py                          # overview (grouped by category)
python <scripts_dir>/sci_colors.py --show "Nature Classic 5" # detail: large blocks + hex codes
python <scripts_dir>/sci_colors.py --search "colorblind"     # search by keyword
python <scripts_dir>/sci_colors.py --tag "morandi"           # filter by tag
python <scripts_dir>/sci_colors.py --code "Nature Classic 5" # copy-paste Python code
python <scripts_dir>/sci_colors.py --names                   # bare names for scripting
```

## Behavior Rules

1. **When user asks for colors/palettes**: run `--show` or `--search` directly — show terminal output, don't generate images
2. **When user is vague** ("I need pretty colors for a bar chart"): ask about (a) number of categories, (b) journal target or aesthetic preference, (c) any constraints (colorblind-safe? print?). Then `--search` for matching palettes
3. **When user wants to use colors in code**: run `--code <name>` to produce copy-paste Python snippet
4. **Never generate PNG files** for color preview. Terminal ANSI blocks are instant and sufficient

## Quick Recommendations

| Scenario | Palette |
|----------|---------|
| 3-5 category bar/line | Nature Classic 5 / Science Colorblind 6 |
| Heatmap / continuous | Viridis 5 / Cool-Warm 5 |
| Colorblind-safe (reviewer-proof) | Okabe-Ito 7 / Tol Muted 9 |
| Single-cell / multi-omics | Nature 2020 COVID 12 / Cell 2019 scRNA 8 |
| Soft / elegant / artsy | Morandi 6 / Dusty Rose 5 / French Gray 6 |
| Dark background (PPT/poster) | Neon DarkBg 5 |
| Good/Warning/Bad semantic | Traffic Light 3 |
| Grayscale print safe | Grayscale-Safe 6 / Zebra 6 |
