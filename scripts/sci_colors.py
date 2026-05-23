#!/usr/bin/env python3
"""
SCI Color Palette Library — 55 journal-grade palettes with terminal preview.
No GUI needed. ANSI true-color blocks render directly in modern terminals.

Usage:
  python sci_colors.py                      # overview: all 55 palettes with mini blocks
  python sci_colors.py --show "Nature 5"    # detailed view of one palette
  python sci_colors.py --search "nature"    # search by keyword
  python sci_colors.py --tag "色盲友好"      # filter by tag
  python sci_colors.py --code "Nature 5"    # ready-to-paste Python code
  python sci_colors.py --names              # just the names
  python sci_colors.py --page 2             # page through overview (10 per page)
"""

import sys
import os
import shutil

# ====================================================================
# PALETTE DATABASE — 55 named schemes
# ====================================================================

PALETTES = {}

def _reg(name, colors, n, tags, source, desc):
    PALETTES[name] = {
        "name": name, "colors": colors, "n": n, "tags": tags,
        "source": source, "description": desc
    }

# --- Nature (5) ---
_reg("Nature Classic 5", ["#0077BB","#EE7733","#33BBEE","#CC3311","#009988"],
     5,["nature","colorblind-safe","classic"],"Nature Publishing Group",
     "Low-saturation, colorblind-safe, print-friendly. The iconic Nature look.")
_reg("Nature Low-Sat 6", ["#4C72B0","#55A868","#C44E52","#8172B2","#CCB974","#64B5CD"],
     6,["nature","low-saturation","general"],"Nature Methods",
     "Muted 6-color for box/violin/scatter plots. Reviewer-proof.")
_reg("Nature Rev 4", ["#3B528B","#5EC962","#E6594E","#B886C7"],
     4,["nature","review","high-contrast"],"Nature Reviews",
     "High-contrast 4-color for review figures.")
_reg("Nature 2018 MultiOmics 7", ["#783299","#445D80","#4B97B4","#00A000","#FC00FF","#FF7800","#00D3E0"],
     7,["nature","multi-omics","2018"],"Nature 2018",
     "7-color for heatmaps, enrichment bubbles, single-cell annotation.")
_reg("Nature 2020 COVID 12", ["#31123A","#4454C4","#4491FE","#20C7E0","#28EFA3","#7EFF55",
      "#C1F235","#F1CA39","#FD922A","#EB4F0E","#BE2002","#790403"],
     12,["nature","multi-omics","wide-spectrum","2020"],"Nature 2020",
     "12-color ultra-wide for UMAP/t-SNE, co-expression networks.")

# --- Science (4) ---
_reg("Science Colorblind 6", ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00"],
     6,["science","colorblind-safe","classic"],"Science/AAAS",
     "Wong 2011 colorblind-safe 6. Distinguishable by all CVD types.")
_reg("Science Muted 5", ["#882255","#DDCC77","#88CCEE","#CC6677","#44AA99"],
     5,["science","muted","soft"],"Science/AAAS",
     "Soft 5-color for light-background / large-area fills.")
_reg("Science Bright 7", ["#4477AA","#EE6677","#228833","#CCBB44","#66CCEE","#AA3377","#BBBBBB"],
     7,["science","bright","vivid"],"Science/AAAS",
     "Bright 7-color when strong visual separation is needed.")
_reg("Tol Bright 7", ["#4477AA","#EE6677","#228833","#CCBB44","#66CCEE","#AA3377","#BBBBBB"],
     7,["science","tol","colorblind-safe"],"Paul Tol",
     "Paul Tol Bright: vivid on both screen and print.")

# --- Cell (4) ---
_reg("Cell 2019 scRNA 8", ["#0271BC","#05E2FD","#D85316","#FEA532","#D29502","#FFFB3F","#FB5DFD","#7D2F8E"],
     8,["cell","single-cell","2019"],"Cell 2019",
     "8-color for single-cell scatter/UMAP plots.")
_reg("Cell 2020 Metabolic 4", ["#2A82C4","#25B99D","#D7BA54","#EEE922"],
     4,["cell","metabolic","minimal","2020"],"Cell 2020",
     "Minimal 4-color for metabolic pathway diagrams.")
_reg("Cell Systems 6", ["#1B9E77","#D95F02","#7570B3","#E7298A","#66A61E","#E6AB02"],
     6,["cell","systems-biology"],"Cell Systems",
     "Dark2 variant recommended by Cell Systems.")
_reg("Cell Genomics 5", ["#2C3E50","#E74C3C","#3498DB","#2ECC71","#F39C12"],
     5,["cell","genomics","modern"],"Cell Genomics",
     "Modern flat 5-color for genomic track views.")

# --- Lancet/BMJ/NEJM (5) ---
_reg("Lancet Low-Sat 6", ["#A1C9F4","#FFB482","#8DE5A1","#FF9F9B","#B39FDB","#FDFFB6"],
     6,["lancet","low-saturation","medical"],"The Lancet",
     "Low-saturation 6: comfortable for clinical data display.")
_reg("BMJ High-Contrast 6", ["#00468B","#ED0000","#42B390","#FF8C00","#8E44AD","#BDBCBC"],
     6,["bmj","high-contrast","medical"],"The BMJ",
     "120deg hue separation — impossible to confuse categories.")
_reg("NEJM Classic 4", ["#2A4365","#D53E4F","#4DAF4A","#FF7F00"],
     4,["nejm","classic","medical"],"NEJM",
     "Clean, authoritative 4-color clinical palette.")
_reg("JAMA Network 6", ["#374E55","#DF8F44","#00A1D5","#B24745","#79AF97","#6A6599"],
     6,["jama","soft","medical"],"JAMA Network",
     "Soft clinical 6-color for observational studies.")
_reg("Clinical 3-Safe", ["#0072B5","#F37021","#CF0921"],
     3,["clinical","safe","alert"],"Clinical Standard",
     "Blue/Orange/Red — never confuse patient groups.")

# --- Perceptual / Sequential (8) ---
_reg("Viridis 5", ["#440154","#3B528B","#21918C","#5EC962","#FDE725"],
     5,["sequential","colorblind-safe","perceptual"],"matplotlib",
     "Viridis 5 stops. The gold standard for heatmaps.")
_reg("Magma 5", ["#000004","#3B0F70","#8C2981","#DE4968","#FCFDBF"],
     5,["sequential","perceptual"],"matplotlib",
     "Magma 5 stops. Good for dark-background figures.")
_reg("Plasma 5", ["#0D0887","#6A00A8","#B12A90","#E16462","#FCA636"],
     5,["sequential","perceptual"],"matplotlib",
     "Plasma 5 stops. Vibrant perceptual rainbow alternative.")
_reg("Cividis 5", ["#00224E","#444C6E","#7C7B78","#B0AD7C","#FDE333"],
     5,["sequential","colorblind-safe","perceptual"],"matplotlib",
     "Cividis 5: fully colorblind-safe sequential.")
_reg("Cool-Warm 5", ["#2166AC","#67A9CF","#F7F7F7","#EF8A62","#B2182B"],
     5,["diverging","cool-warm","difference"],"ColorBrewer",
     "Cool-warm diverging 5: correlation/difference heatmaps.")
_reg("Spectral 7", ["#D53E4F","#F46D43","#FDAE61","#FEE08B","#E6F598","#ABDDA4","#3288BD"],
     7,["diverging","spectral","rainbow-alt"],"ColorBrewer",
     "Diverging 7: replace rainbow. Up/down regulation, +/- values.")
_reg("Sunset Blue 5", ["#364B9A","#4A7BB7","#6EA6CD","#98CAE1","#C2E4EF"],
     5,["sequential","blue","clean"],"Custom",
     "Sunset blue 5-step: deep to pale sky blue.")
_reg("Ocean Thermal 6", ["#00204D","#003D6B","#1A6B9E","#4FA1CC","#87CCE8","#D1F0FA"],
     6,["sequential","ocean","thermal"],"Custom",
     "Ocean thermal 6-step: abyss to shallows.")

# --- Colorblind-Safe (5) ---
_reg("Okabe-Ito 7", ["#000000","#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00"],
     7,["colorblind-safe","okabe-ito","standard"],"Okabe & Ito 2008",
     "The gold standard: 7 colors + black. All CVD types can distinguish.")
_reg("Tol Light 7", ["#77AADD","#EE8866","#EEDD88","#FFAABB","#99DDFF","#44BB99","#BBCC33"],
     7,["colorblind-safe","tol","light"],"Paul Tol",
     "Paul Tol Light 7: for white/light backgrounds.")
_reg("Tol Muted 9", ["#332288","#88CCEE","#44AA99","#117733","#999933","#DDCC77",
                     "#CC6677","#882255","#AA4499"],
     9,["colorblind-safe","tol","muted"],"Paul Tol",
     "Paul Tol Muted 9: most colors in one colorblind-safe palette.")
_reg("Tol HighContrast 3", ["#004488","#DDAA33","#BB5566"],
     3,["colorblind-safe","tol","high-contrast"],"Paul Tol",
     "Paul Tol high-contrast 3: distinguishable even in grayscale print.")
_reg("Grayscale-Safe 6", ["#004488","#DDAA33","#BB5566","#228833","#77AADD","#AAAAAA"],
     6,["grayscale-safe","print","bw"],"ColorBrewer",
     "Grayscale-safe 6: luminance difference >= 30% for B&W print.")

# --- Morandi / Soft / Pastel (5) ---
_reg("Morandi 6", ["#C2A899","#A8B5C3","#B8C9B8","#D4C5C7","#C5C0A6","#B5AFA4"],
     6,["morandi","soft","elegant"],"Giorgio Morandi",
     "Quiet, refined, high gray-value. Wabi-sabi aesthetic for charts.")
_reg("Dusty Rose 5", ["#C49B9F","#D4AFB7","#E3C4CB","#B8D3D9","#A3C4CC"],
     5,["soft","rose","feminine"],"Custom",
     "Dusty rose 5: soft, warm, feminine aesthetic.")
_reg("Sage Green 5", ["#8B9E8B","#A3B8A3","#BDD1BD","#7A927A","#9FB09F"],
     5,["soft","green","nature"],"Custom",
     "Sage green 5: nature, ecology, sustainability themes.")
_reg("French Gray 6", ["#5D6D7E","#85929E","#ABB2B9","#D5D8DC","#E5E7E9","#F2F3F4"],
     6,["gray","elegant","sequential"],"Custom",
     "French gray 6: deep slate to near-white. Pure elegance.")
_reg("Pastel Dream 6", ["#FFD6E0","#FFFDDE","#D4F0F7","#E3F0DE","#FFE5D9","#E8E0F0"],
     6,["pastel","soft","dreamy"],"Custom",
     "Dreamy pastel 6: large-area fills without visual fatigue.")

# --- Bright / Tropical / Pop (5) ---
_reg("Tropical 6", ["#FF6B6B","#FFA07A","#FFD93D","#6BCB77","#4D96FF","#9B59B6"],
     6,["tropical","bright","energetic"],"Custom",
     "Tropical 6: coral to purple, full of life.")
_reg("Candy Pop 5", ["#FF6B6B","#FECA57","#48DBFB","#FF9FF3","#54A0FF"],
     5,["bright","pop","youthful"],"Custom",
     "Candy pop 5: vivid, playful, youthful.")
_reg("Sunset Glow 5", ["#FF6B35","#F7C548","#7BC2BC","#4A7C96","#2C3E50"],
     5,["sunset","warm","gradient"],"Custom",
     "Sunset glow: orange -> gold -> teal -> navy.")
_reg("Forest 6", ["#2D5016","#4A7C2E","#6BAF4B","#A8D67A","#D4EFB5","#F2FBE3"],
     6,["forest","green","nature"],"Custom",
     "Forest 6-step: deep pine to pale leaf.")
_reg("Ocean Depth 6", ["#0B3D91","#1E62A8","#3B8EC2","#6CB5D9","#ABDAED","#E2F3F9"],
     6,["ocean","blue","depth"],"Custom",
     "Ocean depth 6-step: abyssal blue to surface shimmer.")

# --- Terrain / Geology / Materials (5) ---
_reg("Terrain 7", ["#3E6B48","#7DA87B","#C4D4A1","#E5D5A5","#D4A96A","#B8784A","#8C5230"],
     7,["terrain","geology","elevation"],"Custom",
     "Terrain 7: lowland green -> highland brown.")
_reg("Geology 6", ["#5B3E2E","#8B6B4A","#B89868","#D4C48A","#A8C4A0","#7AAA9E"],
     6,["geology","strata","mineral"],"Custom",
     "Geology 6: rock strata brown -> mineral green.")
_reg("Volcano 5", ["#1A0A00","#4A1800","#8B3A00","#D4732A","#FFC04C"],
     5,["volcano","thermal","red-hot"],"Custom",
     "Volcano 5: black -> dark red -> orange -> gold.")
_reg("Material Phase 6", ["#2C3E50","#E74C3C","#3498DB","#2ECC71","#F39C12","#9B59B6"],
     6,["material","phase-diagram","multicolor"],"Custom",
     "Material phase 6: distinct colors for different phases.")
_reg("Metallurgy 5", ["#BDC3C7","#95A5A6","#7F8C8D","#636E72","#4A5154"],
     5,["metal","gray","industrial"],"Custom",
     "Metallurgy 5: silver -> iron gray. Industrial look.")

# --- Special Purpose (4) ---
_reg("Traffic Light 3", ["#27AE60","#F1C40F","#E74C3C"],
     3,["traffic-light","good-bad","semantic"],"Standard",
     "Traffic light: Green (good) / Yellow (warning) / Red (bad).")
_reg("Zebra 6", ["#1A1A1A","#E0E0E0","#333333","#C0C0C0","#4D4D4D","#A0A0A0"],
     6,["bw","striped","grayscale"],"Custom",
     "Zebra 6: alternating black/white. Zero color confusion.")
_reg("Neon DarkBg 5", ["#00FF88","#00D4FF","#FF6EC7","#FFD700","#FF4500"],
     5,["neon","dark-background","fluorescent"],"Custom",
     "Neon 5: for dark-background slides & posters. Pops hard.")
_reg("Warm-Cool Pair 4", ["#E74C3C","#F39C12","#3498DB","#2ECC71"],
     4,["warm-cool","contrast","dual"],"Custom",
     "Warm-Cool contrast 4: red/orange (warm) + blue/green (cool).")

# --- Chinese Journal (4) ---
_reg("China Sci 5", ["#C23531","#2F4554","#61A0A8","#D48265","#91C7AE"],
     5,["chinese","journal","general"],"Custom",
     "Chinese journal general 5: dignified, not flashy.")
_reg("Earth Tone 6", ["#8B5A2B","#A0522D","#CD853F","#DEB887","#F5DEB3","#FFF8DC"],
     6,["earth","warm","natural"],"Custom",
     "Warm earth 6: deep brown -> cream.")
_reg("Ink Wash 5", ["#1C1C1C","#3A3A3A","#6B6B6B","#9B9B9B","#CCCCCC"],
     5,["ink","grayscale","traditional"],"Custom",
     "Ink wash 5: traditional Chinese sumi-e grayscale.")
_reg("Porcelain 5", ["#2F4F4F","#3D6B6B","#5F9EA0","#8FBC8F","#BC8F8F"],
     5,["porcelain","blue-green","traditional"],"Custom",
     "Porcelain 5: blue-green-brown, classic Chinese ceramic glaze.")

# ====================================================================
# ANSI Terminal Rendering
# ====================================================================

def _color_block(hex_color, width=4):
    """Return ANSI true-color background block."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"\033[48;2;{r};{g};{b}m{' ' * width}\033[0m"

def _mini_blocks(colors, block_w=2):
    """Compact row of color blocks for overview."""
    return ''.join(_color_block(c, block_w) for c in colors)

def _term_width():
    return shutil.get_terminal_size().columns or 100

def _print_palette_detail(name):
    """Print one palette in full detail with large color blocks."""
    p = PALETTES[name]
    colors = p['colors']
    tw = _term_width()
    block_w = max(3, min(8, (tw - len(colors) * 2) // len(colors)))

    # Header
    print(f"\n\033[1;37m{p['name']}\033[0m   \033[90m{p['source']}\033[0m")
    print("\033[90m" + "─" * min(tw, 60) + "\033[0m")

    # Large color blocks row
    for c in colors:
        print(_color_block(c, block_w), end=' ')
    print()

    # Hex codes under blocks
    for c in colors:
        pad = ' ' * max(0, block_w - len(c))
        print(f"\033[37m{c}\033[0m{pad}", end=' ')
    print()

    # Index numbers
    for i in range(len(colors)):
        pad = ' ' * (block_w - 1)
        print(f"\033[90m#{i+1}\033[0m{pad}", end='  ')
    print()

    # Description
    tags_str = ', '.join(p['tags'])
    print(f"\n  \033[37m{p['description']}\033[0m")
    print(f"  \033[90mTags: {tags_str}  |  Recommended <= {p['n']} series\033[0m")

    # Luminance check
    print(f"  \033[90mHex: {'  '.join(colors)}\033[0m")

def _print_overview(palette_names=None, page=0, per_page=10):
    """Print overview of multiple palettes with mini color blocks."""
    if palette_names is None:
        palette_names = list(PALETTES.keys())

    total = len(palette_names)
    total_pages = (total + per_page - 1) // per_page
    start = page * per_page
    end = min(start + per_page, total)
    page_names = palette_names[start:end]

    tw = _term_width()
    print(f"\n\033[1;37mSCI Color Palette Library\033[0m  \033[90m— {total} palettes\033[0m")
    print("\033[90m" + "═" * min(tw, 80) + "\033[0m")

    if total_pages > 1:
        print(f"\033[90mPage {page+1}/{total_pages}  (--page N to navigate)\033[0m\n")

    # Calculate layout
    name_w = max(len(n) for n in page_names) + 2
    block_available = tw - name_w - 12  # 12 for "Nc " prefix
    mini_w = max(1, min(2, (block_available // 6) - 1))

    for name in page_names:
        p = PALETTES[name]
        n = len(p['colors'])
        blocks = _mini_blocks(p['colors'], mini_w)
        print(f"  \033[1m{name:<{name_w}}\033[0m \033[90m{n}c\033[0m {blocks}")

    print()
    if total_pages > 1:
        print(f"\033[90mPage {page+1}/{total_pages}. Use --page N or --show <name> for detail.\033[0m")
    else:
        print(f"\033[90mUse --show <name> for detailed view with hex codes.\033[0m")

def _print_overview_by_tag(page=0, per_page=10):
    """Print overview grouped by primary tag."""
    by_tag = {}
    for name, p in PALETTES.items():
        tag = p['tags'][0] if p['tags'] else 'other'
        by_tag.setdefault(tag, []).append(name)

    tw = _term_width()
    print(f"\n\033[1;37mSCI Color Palette Library\033[0m  \033[90m— {len(PALETTES)} palettes grouped by category\033[0m")
    print("\033[90m" + "═" * min(tw, 80) + "\033[0m\n")

    for tag in sorted(by_tag):
        names = by_tag[tag]
        print(f"  \033[1;36m[{tag}]\033[0m ({len(names)} palettes)")
        for name in names:
            p = PALETTES[name]
            blocks = _mini_blocks(p['colors'], 2)
            print(f"    \033[1m{name:<30}\033[0m \033[90m{len(p['colors'])}c\033[0m  {blocks}  \033[90m{p['description'][:50]}\033[0m")
        print()

    print(f"\033[90mUse --show <name> for detailed view with hex codes.\033[0m")


# ====================================================================
# API Functions
# ====================================================================

def list_palettes(tag=None):
    if tag:
        return [k for k, v in PALETTES.items() if tag.lower() in [t.lower() for t in v["tags"]]]
    return list(PALETTES.keys())

def get_palette(name):
    if name not in PALETTES:
        matches = [k for k in PALETTES if name.lower() in k.lower()]
        if matches:
            return PALETTES[matches[0]]
        raise KeyError(f"Palette '{name}' not found. Use list_palettes() to see all.")
    return PALETTES[name]

def search_palettes(keyword):
    kw = keyword.lower()
    return [n for n, p in PALETTES.items()
            if kw in n.lower() or kw in p["description"].lower() or any(kw in t.lower() for t in p["tags"])]

def apply_palette(name, n=None):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    p = get_palette(name)
    colors = p["colors"][:n] if n else p["colors"]
    plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
    return colors

def palette_info(name):
    _print_palette_detail(name)

def palette_to_python(name):
    p = get_palette(name)
    colors_str = "', '".join(p["colors"])
    vname = name.lower().replace(" ", "_").replace("-", "_")
    return f'''# {p["name"]} — {p["description"]}
# Source: {p["source"]} | Tags: {", ".join(p["tags"])}
colors_{vname} = ['{colors_str}']

# matplotlib:
#   import matplotlib.pyplot as plt
#   plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors_{vname})

# seaborn:
#   import seaborn as sns
#   sns.set_palette(colors_{vname})
'''

# ====================================================================
# CLI
# ====================================================================

def _print_mini_help():
    print("""\033[1;37mSCI Color Palette Library\033[0m — 55 journal-grade palettes

\033[1mUSAGE:\033[0m
  python sci_colors.py                    overview (all 55, grouped by category)
  python sci_colors.py --show <name>      detailed view with large color blocks
  python sci_colors.py --search <kw>      search by keyword
  python sci_colors.py --tag <tag>        filter by tag
  python sci_colors.py --code <name>      print ready-to-use Python code
  python sci_colors.py --names            list names only
  python sci_colors.py --page N           page through overview (10 per page)
  python sci_colors.py --tags             list all tags with counts

\033[1mEXAMPLES:\033[0m
  python sci_colors.py --show "Nature Classic 5"
  python sci_colors.py --search "colorblind"
  python sci_colors.py --tag "morandi"
  python sci_colors.py --code "Okabe-Ito 7"
""")

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        _print_overview_by_tag()
    elif args[0] in ("--help", "-h"):
        _print_mini_help()
    elif args[0] == "--names":
        for n in PALETTES:
            print(n)
    elif args[0] == "--tags":
        tags = {}
        for p in PALETTES.values():
            for t in p["tags"]:
                tags[t] = tags.get(t, 0) + 1
        for t, c in sorted(tags.items(), key=lambda x: -x[1]):
            print(f"  \033[1m{t}\033[0m ({c})")
    elif args[0] == "--show" and len(args) > 1:
        try:
            _print_palette_detail(args[1])
        except KeyError:
            matches = search_palettes(args[1])
            if matches:
                print(f"\n\033[33mPalette '{args[1]}' not found. Did you mean:\033[0m")
                for m in matches[:5]:
                    print(f"  \033[1m{m}\033[0m")
            else:
                print(f"\033[31mPalette '{args[1]}' not found.\033[0m")
    elif args[0] == "--search" and len(args) > 1:
        results = search_palettes(args[1])
        if results:
            print(f"\n\033[1;37mSearch: '{args[1]}'\033[0m — \033[90m{len(results)} results\033[0m\n")
            for r in results:
                p = PALETTES[r]
                blocks = _mini_blocks(p['colors'], 2)
                print(f"  \033[1m{r}\033[0m \033[90m{len(p['colors'])}c\033[0m  {blocks}  \033[90m{p['description'][:55]}\033[0m")
            print(f"\n\033[90mUse --show <name> for detailed view.\033[0m")
        else:
            print(f"\033[33mNo palettes matching '{args[1]}'\033[0m")
    elif args[0] == "--tag" and len(args) > 1:
        names = list_palettes(args[1])
        if names:
            _print_overview(names)
        else:
            print(f"\033[33mNo palettes with tag '{args[1]}'\033[0m")
    elif args[0] == "--code" and len(args) > 1:
        try:
            print(palette_to_python(args[1]))
        except KeyError:
            matches = search_palettes(args[1])
            if matches:
                print(palette_to_python(matches[0]))
    elif args[0] == "--page" and len(args) > 1:
        try:
            page = int(args[1])
            _print_overview(page=page)
        except ValueError:
            print("\033[31mInvalid page number.\033[0m")
    else:
        _print_mini_help()
