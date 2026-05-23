---
name: sci-color
description: Query SCI-level scientific color palettes for matplotlib/plotting. Use when user asks about color schemes, scientific plotting colors, needs beautiful palettes for charts/figures, wants Nature/Science/Cell-level aesthetics, or says "配色"/"颜色"/"sci颜色"/sci-color.
license: MIT
---

# SCI Color Palette Library

55 SCI journal-level color schemes accessible from Python and CLI. Covers Nature, Science, Cell, Lancet, BMJ, colorblind-safe, and Chinese journal styles.

## CLI Quick Reference

```bash
python <scripts_dir>/sci_colors.py                          # list all 55 palettes
python <scripts_dir>/sci_colors.py --search "nature"        # search by keyword
python <scripts_dir>/sci_colors.py --show "Nature Classic 5" # visual preview
python <scripts_dir>/sci_colors.py --info "Science Colorblind 6" # terminal preview
python <scripts_dir>/sci_colors.py --code "Nature Classic 5" # copy-paste Python code
python <scripts_dir>/sci_colors.py --tag "色盲友好"          # filter by tag
python <scripts_dir>/sci_colors.py --names                   # list names only
```

## Python API

```python
from sci_colors import get_palette, list_palettes, apply_palette, search_palettes

# Get colors
colors = get_palette("Nature Classic 5")["colors"]
# ['#0077BB', '#EE7733', '#33BBEE', '#CC3311', '#009988']

# Search by keyword
results = search_palettes("色盲安全")
# ['Science Colorblind 6', 'Okabe-Ito 7', 'Tol Light 7', ...]

# Apply directly to matplotlib
apply_palette("Nature Classic 5")

# Get ready-to-paste Python code
print(palette_to_python("Science Colorblind 6"))
```

## Palette Categories (55 total)

| Category | Count | Examples |
|----------|-------|---------|
| Nature 系列 | 5 | Classic 5, Low-Sat 6, COVID 12 |
| Science 系列 | 4 | Colorblind 6, Tol Bright 7 |
| Cell 系列 | 4 | scRNA 8, Metabolic 4 |
| Lancet/BMJ/NEJM | 5 | Low-Sat 6, High-Contrast 6 |
| 渐变/Perceptual | 8 | Viridis, Cool-Warm, Spectral |
| 色盲友好 | 5 | Okabe-Ito 7, Tol Muted 9 |
| 莫兰迪/柔和 | 5 | Morandi 6, Sage Green 5 |
| 明亮/活力 | 5 | Tropical 6, Candy Pop 5 |
| 地形/地质/材料 | 5 | Terrain 7, Geology 6 |
| 特殊用途 | 4 | Traffic Light 3, Neon DarkBg 5 |
| 中文期刊 | 4 | China Sci 5, Ink Wash 5 |

## Usage Workflow

When user asks for plot colors:

1. Ask about the context: journal target, number of categories, any constraints (colorblind-safe? print-friendly?)
2. Search with `search_palettes(keyword)` or recommend from the best-matching category
3. Show the palette with `--show` for visual preview
4. Provide `--code` output for copy-paste into their script
5. For matplotlib users, suggest `apply_palette(name)` for quick setup
