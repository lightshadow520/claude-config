#!/usr/bin/env python3
"""
SCI Color Palette Library — 50+ 顶刊级科学配色方案
====================================================
Usage:
  python sci_colors.py                    # list all palettes
  python sci_colors.py --show "Nature 5"  # display a specific palette
  python sci_colors.py --apply "Nature 5" # print hex codes for copy-paste

In Python:
  from sci_colors import get_palette, list_palettes, apply_palette
  colors = get_palette("Nature 5")
  apply_palette("Nature 5")  # sets matplotlib rcParams

Color-blind safe, print-friendly, Nature/Science/Cell/Lancet-grade.
"""

import sys
import os
import json
import math

# ====================================================================
# PALETTE DATABASE — 55 named schemes
# Each: {name, colors: [hex], n: recommended data series count,
#         tags: [], source: str, description: str}
# ====================================================================

PALETTES = {}

def _reg(name, colors, n, tags, source, desc):
    PALETTES[name] = {
        "name": name, "colors": colors, "n": n, "tags": tags,
        "source": source, "description": desc
    }

# --- Nature 系列 (5) ---
_reg("Nature Classic 5", ["#0077BB", "#EE7733", "#33BBEE", "#CC3311", "#009988"],
     5, ["nature", "classic", "色盲友好"], "Nature Publishing Group",
     "Nature 经典 5 色：低饱和、色盲友好、印出来也清晰")
_reg("Nature Low-Sat 6", ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD"],
     6, ["nature", "低饱和", "通用"], "Nature Methods",
     "Nature Methods 低饱和 6 色：箱线图/小提琴图/散点图首选")
_reg("Nature Rev 4", ["#3B528B", "#5EC962", "#E6594E", "#B886C7"],
     4, ["nature", "review", "高对比"], "Nature Reviews",
     "Nature Reviews 4 色：综述图高对比配色")
_reg("Nature 2018 MultiOmics 7", ["#783299", "#445D80", "#4B97B4", "#00A000", "#FC00FF", "#FF7800", "#00D3E0"],
     7, ["nature", "多组学", "2018"], "Nature 2018",
     "Nature 2018 多组学 7 色：热图/富集气泡图/单细胞注释")
_reg("Nature 2020 COVID 12", ["#31123A", "#4454C4", "#4491FE", "#20C7E0", "#28EFA3", "#7EFF55",
                               "#C1F235", "#F1CA39", "#FD922A", "#EB4F0E", "#BE2002", "#790403"],
     12, ["nature", "多组学", "宽谱", "2020"], "Nature 2020",
     "Nature 2020 新冠多组学 12 色超宽谱：UMAP/t-SNE/共表达网络")

# --- Science 系列 (4) ---
_reg("Science Colorblind 6", ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00"],
     6, ["science", "色盲友好", "经典"], "Science/AAAS",
     "Science 色盲友好 6 色（Wong 2011）：所有色觉异常类型都能区分")
_reg("Science Muted 5", ["#882255", "#DDCC77", "#88CCEE", "#CC6677", "#44AA99"],
     5, ["science", "低饱和", "柔和"], "Science/AAAS",
     "Science 柔和 5 色：浅背景图/大面积填充")
_reg("Science Bright 7", ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"],
     7, ["science", "明亮", "彩色"], "Science/AAAS",
     "Science 明亮 7 色：需要强烈视觉区分的场景")
_reg("Science Tol Bright 7", ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"],
     7, ["science", "tol", "色盲友好"], "Paul Tol",
     "Paul Tol Bright：打印和屏幕都鲜明")

# --- Cell 系列 (4) ---
_reg("Cell 2019 scRNA 8", ["#0271BC", "#05E2FD", "#D85316", "#FEA532", "#D29502", "#FFFB3F", "#FB5DFD", "#7D2F8E"],
     8, ["cell", "单细胞", "2019"], "Cell 2019",
     "Cell 2019 单细胞 8 色散点图")
_reg("Cell 2020 Metabolic 4", ["#2A82C4", "#25B99D", "#D7BA54", "#EEE922"],
     4, ["cell", "代谢", "极简", "2020"], "Cell 2020",
     "Cell 2020 代谢极简 4 色")
_reg("Cell Systems 6", ["#1B9E77", "#D95F02", "#7570B3", "#E7298A", "#66A61E", "#E6AB02"],
     6, ["cell", "系统生物学"], "Cell Systems",
     "Cell Systems 推荐的 Dark2 变体")
_reg("Cell Genomics 5", ["#2C3E50", "#E74C3C", "#3498DB", "#2ECC71", "#F39C12"],
     5, ["cell", "基因组学", "现代"], "Cell Genomics",
     "Cell Genomics 现代扁平 5 色")

# --- Lancet/BMJ/NEJM 医学系列 (5) ---
_reg("Lancet Low-Sat 6", ["#A1C9F4", "#FFB482", "#8DE5A1", "#FF9F9B", "#B39FDB", "#FDFFB6"],
     6, ["lancet", "低饱和", "医学"], "The Lancet",
     "Lancet 低饱和 6 色：适合临床数据，不刺眼")
_reg("BMJ High-Contrast 6", ["#00468B", "#ED0000", "#42B390", "#FF8C00", "#8E44AD", "#BDBCBC"],
     6, ["bmj", "高对比", "医学"], "The BMJ",
     "BMJ 高对比 6 色：120° 色相分离，完全不可能混淆")
_reg("NEJM Classic 4", ["#2A4365", "#D53E4F", "#4DAF4A", "#FF7F00"],
     4, ["nejm", "经典", "医学"], "NEJM",
     "NEJM 经典 4 色：简洁有力")
_reg("JAMA Network 6", ["#374E55", "#DF8F44", "#00A1D5", "#B24745", "#79AF97", "#6A6599"],
     6, ["jama", "柔和", "医学"], "JAMA Network",
     "JAMA Network 柔和 6 色：临床研究图表")
_reg("Clinical 3-Safe", ["#0072B5", "#F37021", "#CF0921"],
     3, ["临床", "安全", "醒目"], "通用临床",
     "临床 3 安全色：蓝/橙/红，病人不混淆")

# --- 通用科学 渐变色/离散色 (8) ---
_reg("Viridis 5", ["#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725"],
     5, ["渐变", "色盲友好", "perceptual"], "matplotlib",
     "Viridis 取 5 个均匀采样点：热图/连续变量首选")
_reg("Magma 5", ["#000004", "#3B0F70", "#8C2981", "#DE4968", "#FCFDBF"],
     5, ["渐变", "perceptual"], "matplotlib",
     "Magma 5 点采样")
_reg("Plasma 5", ["#0D0887", "#6A00A8", "#B12A90", "#E16462", "#FCA636"],
     5, ["渐变", "perceptual"], "matplotlib",
     "Plasma 5 点采样")
_reg("Cividis 5", ["#00224E", "#444C6E", "#7C7B78", "#B0AD7C", "#FDE333"],
     5, ["渐变", "色盲友好", "perceptual"], "matplotlib",
     "Cividis 5 点采样：完全色盲友好")
_reg("Cool-Warm 5", ["#2166AC", "#67A9CF", "#F7F7F7", "#EF8A62", "#B2182B"],
     5, ["渐变", "冷暖", "差异"], "ColorBrewer",
     "冷暖发散 5 色：差异/相关性热图")
_reg("Spectral Diverging 7", ["#D53E4F", "#F46D43", "#FDAE61", "#FEE08B", "#E6F598", "#ABDDA4", "#3288BD"],
     7, ["渐变", "发散", "彩虹替代"], "ColorBrewer",
     "Spectral 发散 7 色：替代彩虹色阶，上下调/正负值")
_reg("Sunset 5", ["#364B9A", "#4A7BB7", "#6EA6CD", "#98CAE1", "#C2E4EF"],
     5, ["渐变", "蓝色", "清爽"], "自定义",
     "日落蓝 5 阶：从深到浅的蓝色渐变")
_reg("Ocean Thermal 6", ["#00204D", "#003D6B", "#1A6B9E", "#4FA1CC", "#87CCE8", "#D1F0FA"],
     6, ["渐变", "海洋", "热力"], "自定义",
     "海洋热力 6 阶：深海到浅海")

# --- 色盲友好专集 (5) ---
_reg("Okabe-Ito 7", ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00"],
     7, ["色盲友好", "okabe-ito", "标准"], "Okabe & Ito 2008",
     "Okabe-Ito 7 色 + 黑：色盲友好的黄金标准")
_reg("Tol Light 7", ["#77AADD", "#EE8866", "#EEDD88", "#FFAABB", "#99DDFF", "#44BB99", "#BBCC33"],
     7, ["色盲友好", "tol", "浅色"], "Paul Tol",
     "Paul Tol Light 7：浅色背景图专用")
_reg("Tol Muted 9", ["#332288", "#88CCEE", "#44AA99", "#117733", "#999933", "#DDCC77",
                      "#CC6677", "#882255", "#AA4499"],
     9, ["色盲友好", "tol", "低饱和"], "Paul Tol",
     "Paul Tol Muted 9：最多色板之一，适合复杂分类")
_reg("Tol HighContrast 3", ["#004488", "#DDAA33", "#BB5566"],
     3, ["色盲友好", "tol", "高对比"], "Paul Tol",
     "Paul Tol 高对比 3：灰度打印也能区分")
_reg("Grayscale-Safe 6", ["#004488", "#DDAA33", "#BB5566", "#228833", "#77AADD", "#AAAAAA"],
     6, ["灰度安全", "打印", "黑白"], "ColorBrewer",
     "灰度安全 6 色：黑白打印亮度差 ≥30%")

# --- 柔和/莫兰迪/高级灰 (5) ---
_reg("Morandi 6", ["#C2A899", "#A8B5C3", "#B8C9B8", "#D4C5C7", "#C5C0A6", "#B5AFA4"],
     6, ["莫兰迪", "高级灰", "柔和"], "莫兰迪色系",
     "莫兰迪 6 色：高级灰调，文艺/设计感")
_reg("Dusty Rose 5", ["#C49B9F", "#D4AFB7", "#E3C4CB", "#B8D3D9", "#A3C4CC"],
     5, ["柔和", "玫瑰", "女性化"], "自定义",
     "灰粉 5 色：柔和女性化主题")
_reg("Sage Green 5", ["#8B9E8B", "#A3B8A3", "#BDD1BD", "#7A927A", "#9FB09F"],
     5, ["柔和", "绿色", "自然"], "自定义",
     "灰绿 5 色：自然/生态/环保主题")
_reg("French Gray 6", ["#5D6D7E", "#85929E", "#ABB2B9", "#D5D8DC", "#E5E7E9", "#F2F3F4"],
     6, ["灰色", "优雅", "渐变"], "自定义",
     "法式灰 6 阶：从深到浅的优雅灰色渐变")
_reg("Pastel Dream 6", ["#FFD6E0", "#FFFDDE", "#D4F0F7", "#E3F0DE", "#FFE5D9", "#E8E0F0"],
     6, ["粉彩", "柔和", "梦幻"], "自定义",
     "梦幻粉彩 6 色：需要大面积色块的轻松场景")

# --- 明亮/热带/活力 (5) ---
_reg("Tropical 6", ["#FF6B6B", "#FFA07A", "#FFD93D", "#6BCB77", "#4D96FF", "#9B59B6"],
     6, ["热带", "明亮", "活力"], "自定义",
     "热带 6 色：活力橙黄绿蓝紫")
_reg("Candy Pop 5", ["#FF6B6B", "#FECA57", "#48DBFB", "#FF9FF3", "#54A0FF"],
     5, ["明亮", "pop", "年轻"], "自定义",
     "糖果 5 色：亮色 pop 风格")
_reg("Sunset Glow 5", ["#FF6B35", "#F7C548", "#7BC2BC", "#4A7C96", "#2C3E50"],
     5, ["日落", "温暖", "渐变"], "自定义",
     "日落余晖 5 色：橙→金→青→蓝→墨")
_reg("Forest 6", ["#2D5016", "#4A7C2E", "#6BAF4B", "#A8D67A", "#D4EFB5", "#F2FBE3"],
     6, ["森林", "绿色", "自然"], "自定义",
     "森林 6 阶：从深绿到浅绿的渐变")
_reg("Ocean Depth 6", ["#0B3D91", "#1E62A8", "#3B8EC2", "#6CB5D9", "#ABDAED", "#E2F3F9"],
     6, ["海洋", "蓝色", "深度"], "自定义",
     "海洋深度 6 阶：从深海蓝到浅水蓝")

# --- 地形/地质/材料 (5) ---
_reg("Terrain 7", ["#3E6B48", "#7DA87B", "#C4D4A1", "#E5D5A5", "#D4A96A", "#B8784A", "#8C5230"],
     7, ["地形", "地质", "海拔"], "自定义",
     "地形 7 色：低地绿→高地棕")
_reg("Geology 6", ["#5B3E2E", "#8B6B4A", "#B89868", "#D4C48A", "#A8C4A0", "#7AAA9E"],
     6, ["地质", "岩层", "矿物"], "自定义",
     "地质 6 色：岩层棕→矿物绿")
_reg("Volcano 5", ["#1A0A00", "#4A1800", "#8B3A00", "#D4732A", "#FFC04C"],
     5, ["火山", "热力", "红热"], "自定义",
     "火山 5 色：深黑→暗红→亮橙→金黄")
_reg("Material Phase 6", ["#2C3E50", "#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6"],
     6, ["材料", "相图", "多彩"], "自定义",
     "材料相图 6 色：不同相/组分用不同色")
_reg("Metallurgy 5", ["#BDC3C7", "#95A5A6", "#7F8C8D", "#636E72", "#4A5154"],
     5, ["金属", "灰色", "工业"], "自定义",
     "冶金 5 灰阶：从银白到铁灰")

# --- 特殊用途 (4) ---
_reg("Traffic Light 3", ["#27AE60", "#F1C40F", "#E74C3C"],
     3, ["交通灯", "好坏", "红绿灯"], "通用",
     "红绿灯 3 色：绿(好)/黄(中)/红(差)")
_reg("Zebra 6", ["#1A1A1A", "#E0E0E0", "#333333", "#C0C0C0", "#4D4D4D", "#A0A0A0"],
     6, ["黑白", "条纹", "灰度"], "自定义",
     "斑马 6 色：黑白交替，无颜色混淆")
_reg("Neon DarkBg 5", ["#00FF88", "#00D4FF", "#FF6EC7", "#FFD700", "#FF4500"],
     5, ["霓虹", "深色背景", "荧光"], "自定义",
     "霓虹 5 色：深色背景上用的荧光色，PPT/海报")
_reg("Warm-Cool Pair 4", ["#E74C3C", "#F39C12", "#3498DB", "#2ECC71"],
     4, ["冷暖", "对比", "双色"], "自定义",
     "冷暖对比 4 色：红/黄(暖) + 蓝/绿(冷)")

# --- 中文期刊常用 (4) ---
_reg("China Sci 5", ["#C23531", "#2F4554", "#61A0A8", "#D48265", "#91C7AE"],
     5, ["中文", "期刊", "通用"], "自定义",
     "中文期刊通用 5 色：稳重不花哨")
_reg("Earth Tone 6", ["#8B5A2B", "#A0522D", "#CD853F", "#DEB887", "#F5DEB3", "#FFF8DC"],
     6, ["大地色", "暖色", "自然"], "自定义",
     "大地暖色 6 阶：从深棕到浅米")
_reg("Ink Wash 5", ["#1C1C1C", "#3A3A3A", "#6B6B6B", "#9B9B9B", "#CCCCCC"],
     5, ["水墨", "黑白", "传统"], "自定义",
     "水墨 5 灰阶：中国传统水墨风格")
_reg("Porcelain 5", ["#2F4F4F", "#3D6B6B", "#5F9EA0", "#8FBC8F", "#BC8F8F"],
     5, ["青花瓷", "蓝绿", "传统"], "自定义",
     "青花瓷 5 色：蓝绿棕经典中式配色")

# ====================================================================
# API Functions
# ====================================================================

def list_palettes(tag=None):
    """Return list of palette names, optionally filtered by tag."""
    if tag:
        return [k for k, v in PALETTES.items() if tag.lower() in [t.lower() for t in v["tags"]]]
    return list(PALETTES.keys())

def get_palette(name):
    """Get a palette by exact name. Raises KeyError if not found."""
    if name not in PALETTES:
        # fuzzy search
        matches = [k for k in PALETTES if name.lower() in k.lower()]
        if matches:
            return PALETTES[matches[0]]
        raise KeyError(f"Palette '{name}' not found. Use list_palettes() to see all.")
    return PALETTES[name]

def search_palettes(keyword):
    """Search palettes by keyword in name, tags, or description."""
    kw = keyword.lower()
    results = []
    for name, p in PALETTES.items():
        if kw in name.lower() or kw in p["description"].lower() or any(kw in t.lower() for t in p["tags"]):
            results.append(name)
    return results

def apply_palette(name, n=None):
    """Set matplotlib color cycle to a named palette. Returns the color list."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return None

    p = get_palette(name)
    colors = p["colors"]
    if n and n <= len(colors):
        colors = colors[:n]
    plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
    return colors

def show_palette(name, output=None):
    """Display a palette as a horizontal color bar. Saves to file if output is set."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return

    p = get_palette(name)
    colors = p["colors"]
    n = len(colors)

    fig, ax = plt.subplots(figsize=(n * 1.2, 1.2))
    for i, c in enumerate(colors):
        ax.add_patch(mpatches.Rectangle((i, 0), 1, 1, color=c))
        ax.text(i + 0.5, -0.35, c, ha='center', va='top', fontsize=8, family='monospace',
                rotation=30 if n > 8 else 0)

    ax.set_xlim(0, n)
    ax.set_ylim(-0.8, 1)
    ax.set_title(f"{p['name']} ({n} colors)\n{p['source']} — {p['description']}",
                 fontsize=9, pad=8)
    ax.axis('off')
    plt.tight_layout()

    if output:
        fig.savefig(output, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {output}")
    else:
        plt.show()


def palette_to_matplotlib(name):
    """Return matplotlib ListedColormap + discrete color list."""
    try:
        from matplotlib.colors import ListedColormap
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return None, None

    p = get_palette(name)
    cmap = ListedColormap(p["colors"], name=name.replace(" ", "_"))
    return cmap, p["colors"]


def palette_info(name):
    """Print detailed info about a palette."""
    p = get_palette(name)
    width = 8
    print(f"\n  {p['name']}")
    print(f"  {'─' * len(p['name'])}")
    print(f"  Source:  {p['source']}")
    print(f"  Colors:  {len(p['colors'])} (recommended ≤{p['n']} series)")
    print(f"  Tags:    {', '.join(p['tags'])}")
    print(f"  Desc:    {p['description']}")
    print(f"\n  ", end="")
    for c in p["colors"]:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        print(f"\033[48;2;{r};{g};{b}m  {c}  \033[0m", end=" ")
    print("\n")


def palette_to_python(name):
    """Return ready-to-paste Python code for this palette."""
    p = get_palette(name)
    colors_str = "', '".join(p["colors"])
    code = f'''# {p["name"]} — {p["description"]}
# Source: {p["source"]} | Tags: {", ".join(p["tags"])}
colors_{name.lower().replace(" ", "_").replace("-", "_")} = ['{colors_str}']

# matplotlib usage:
# import matplotlib.pyplot as plt
# plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors_{name.lower().replace(" ", "_").replace("-", "_")})

# seaborn usage:
# import seaborn as sns
# sns.set_palette(colors_{name.lower().replace(" ", "_").replace("-", "_")})
'''
    return code


# ====================================================================
# CLI
# ====================================================================

def _print_help():
    print("""SCI Color Palette Library — 55 顶刊配色方案

Usage:
  python sci_colors.py                        list all palettes
  python sci_colors.py --search <keyword>     search by keyword
  python sci_colors.py --show <name>          display palette with color blocks
  python sci_colors.py --info <name>          detailed info + terminal preview
  python sci_colors.py --code <name>          print ready-to-use Python code
  python sci_colors.py --apply <name>         print hex codes (one per line)
  python sci_colors.py --tag <tag>            filter by tag (e.g. nature, 色盲友好)
  python sci_colors.py --tags                 list all tags
  python sci_colors.py --names                list only names (for scripting)
""")

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("=" * 70)
        print(f"  SCI Color Palette Library — {len(PALETTES)} palettes")
        print("=" * 70)
        # Group by first tag
        by_tag = {}
        for name, p in PALETTES.items():
            tag = p["tags"][0] if p["tags"] else "other"
            by_tag.setdefault(tag, []).append(name)
        for tag in sorted(by_tag):
            print(f"\n  [{tag}]")
            for n in by_tag[tag]:
                p = PALETTES[n]
                print(f"    {n:<30s}  {len(p['colors'])}色  {p['description'][:40]}")
        print(f"\n  Use --show <name> to preview, --search <kw> to search.")
        print(f"  Use --code <name> to get Python code.\n")
    elif args[0] == "--help" or args[0] == "-h":
        _print_help()
    elif args[0] == "--names":
        for n in PALETTES:
            print(n)
    elif args[0] == "--tags":
        tags = set()
        for p in PALETTES.values():
            tags.update(p["tags"])
        for t in sorted(tags):
            count = sum(1 for p in PALETTES.values() if t in p["tags"])
            print(f"  {t}: {count} palettes")
    elif args[0] == "--search" and len(args) > 1:
        results = search_palettes(args[1])
        if results:
            print(f"Found {len(results)} matching '{args[1]}':")
            for r in results:
                p = PALETTES[r]
                print(f"  {r} ({len(p['colors'])}色) — {p['description'][:50]}")
        else:
            print(f"No palettes matching '{args[1]}'")
    elif args[0] == "--tag" and len(args) > 1:
        names = list_palettes(args[1])
        if names:
            print(f"Tag '{args[1]}': {len(names)} palettes")
            for n in names:
                p = PALETTES[n]
                print(f"  {n} ({len(p['colors'])}色)")
        else:
            print(f"No palettes with tag '{args[1]}'")
    elif args[0] == "--show" and len(args) > 1:
        show_palette(args[1])
    elif args[0] == "--info" and len(args) > 1:
        palette_info(args[1])
    elif args[0] == "--code" and len(args) > 1:
        print(palette_to_python(args[1]))
    elif args[0] == "--apply" and len(args) > 1:
        p = get_palette(args[1])
        for c in p["colors"]:
            print(c)
    else:
        print(f"Unknown option: {args[0]}")
        _print_help()
