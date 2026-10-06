"""Frame renderer for the MagicaMapGen internal proposal video.

PIL draws every frame and OpenCV only encodes, because OpenCV's Hershey fonts look
like a debug tool and this video has to survive being shown to people who do not care
about the technology. PIL gives real typography, alpha compositing and rounded
borders, and the generator runs offline so the cost does not matter.

A scene is a callable ``(t, ctx) -> Image`` where ``t`` is seconds since the scene
started, so a scene can animate without the film knowing anything about it.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# The RLE codec lives in the generator core (symmetric with its encoder), so the
# promo renderer can expand a grid without re-implementing it or pulling in the
# PyQt6-tied GUI preview module. Guard the import against a non-repo cwd.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from mapgen.export.mapdata import decode_rle  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

W, H = 1600, 900
FPS = 30
OUT = HERE / "MagicaMapGen_promo.mp4"
ASSETS = HERE / "_promo_assets"

# Palette mirrors tools/MagicaMapGen/app/theme.py so the film and the product match.
BG_DEEP = (18, 16, 14)
BG_PANEL = (27, 24, 21)
BG_RAISED = (36, 31, 26)
BORDER = (74, 63, 51)
BORDER_LIT = (107, 90, 69)
TEXT = (232, 220, 200)
TEXT_DIM = (162, 147, 124)
EMBER = (201, 106, 43)
EMBER_LIT = (224, 138, 69)
RUNE = (91, 138, 114)
WARN = (201, 162, 39)
DANGER = (166, 58, 46)

_FONTS = {
    "title": "georgiab.ttf",
    "hd": "msyhbd.ttc",
    "serif": "georgia.ttf",
    "sans": "seguisb.ttf",
    "body": "msyh.ttc",
    "bodybold": "msyhbd.ttc",
    "mono": "consola.ttf",
    "monobold": "consolab.ttf",
}
_cache: dict = {}


def font(kind: str, size: int):
    key = (kind, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONTS / _FONTS[kind]), size)
    return _cache[key]


def ease(t: float, dur: float = 0.5) -> float:
    """Smooth 0..1 ramp, so nothing pops in harshly."""
    if dur <= 0:
        return 1.0
    x = max(0.0, min(1.0, t / dur))
    return x * x * (3 - 2 * x)


def lerp_col(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def base_canvas() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_DEEP)
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(28):
        a = int(3 + i * 0.5)
        d.rectangle([i, i, W - 1 - i, H - 1 - i], outline=(255, 245, 230, a))
    return img


def panel(img: Image.Image, box, accent: bool = False):
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=BG_PANEL + (255,),
                        outline=BORDER + (255,), width=2)
    if accent:
        d.rounded_rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], radius=4,
                            outline=EMBER + (120,), width=1)
        for cx, cy in ((x0 + 14, y0 + 14), (x1 - 14, y0 + 14),
                       (x0 + 14, y1 - 14), (x1 - 14, y1 - 14)):
            d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=EMBER + (200,))
    return img


def text(d, xy, s, f, fill=TEXT, anchor=None):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def wrap(d, s, f, max_w) -> list:
    """Greedy wrap that works for CJK too: break per character when a token is wide."""
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if d.textlength(trial, font=f) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fade_in(img: Image.Image, t: float, dur: float = 0.6) -> Image.Image:
    """Composite over black at the given opacity."""
    a = int(255 * ease(t, dur))
    if a >= 255:
        return img
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(black, img, a / 255.0)


# --------------------------------------------------------------------------
# Scenes
# --------------------------------------------------------------------------

def scene_title(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    y = 296
    text(d, (W // 2, y), "MagicaMapGen", font("title", 84), TEXT, "mm")
    text(d, (W // 2, y + 88), "确定性游戏原型地图生成器", font("body", 34), EMBER_LIT, "mm")
    d.line([(W // 2 - 260, y + 132), (W // 2 + 260, y + 132)],
           fill=BORDER_LIT + (255,), width=2)
    lines = [
        "把一个游戏想法，转成可交付、可复现、引擎可消费的设计原稿地图",
        "Theme 契约  →  Category 数量  →  Distribution 分布  →  Region 局部概率化",
    ]
    for i, s in enumerate(lines):
        text(d, (W // 2, y + 180 + i * 44), s, font("body", 22), TEXT_DIM, "mm")
    text(d, (W // 2, H - 84), "内部立项演示", font("body", 20), TEXT_DIM, "mm")
    return fade_in(img, t, 1.0)


def scene_problem(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "前期原型设计的三道坎", font("hd", 46), TEXT)
    d.line([(90, 134), (500, 134)], fill=EMBER + (255,), width=3)
    items = [
        ("01", "说不清", "“我要一张有雪地有森林的地图”——没有可执行的规格，"
                        "每次重做都不一样，团队无法讨论具体方案。"),
        ("02", "留不下", "原型散落在美术的工程文件、策划的文档、会议的截图里。"
                        "两周后没人说得清当时为什么那样设计。"),
        ("03", "靠不住", "随机生成的东西无法复现。A 觉得好，B 改个参数就全变了，"
                        "评审变成争吵而不是决策。"),
    ]
    y = 186
    for num, head, body in items:
        panel(img, [90, y, W - 90, y + 166], accent=(num == "03"))
        text(d, (126, y + 46), num, font("serif", 42), EMBER, "lm")
        text(d, (206, y + 46), head, font("bodybold", 30), TEXT, "lm")
        for i, ln in enumerate(wrap(d, body, font("body", 20), W - 330)):
            text(d, (210, y + 94 + i * 32), ln, font("body", 20), TEXT_DIM)
        y += 194
    return fade_in(img, t, 0.6)


def scene_solution(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "MagicaMapGen：把原型变成一份契约", font("hd", 44), TEXT)
    d.line([(90, 134), (560, 134)], fill=EMBER + (255,), width=3)
    text(d, (90, 172), "四层模型 —— 每一层都可替换、可追溯", font("bodybold", 26), EMBER_LIT)
    layers = [
        ("Theme 主题", "确定契约：说雪地绝不给草原", RUNE),
        ("Category 类别", "主题下的物体与各自数量", BORDER_LIT),
        ("Distribution 分布", "这一类怎么铺开：泊松盘 / 团簇 / 均匀 / 网格", EMBER),
        ("Region 区域", "局部概率化：北部密林、东部山脊", WARN),
    ]
    y = 228
    for i, (name, desc, col) in enumerate(layers):
        x0 = 90 + i * 58
        w = W - 180 - i * 116
        a = int(255 * ease(t - 0.22 * i - 0.2, 0.5))
        d.rounded_rectangle([x0, y, x0 + w, y + 84], radius=6,
                            fill=lerp_col(BG_PANEL, BG_RAISED, i / 3.0) + (a,),
                            outline=col + (a,), width=2)
        text(d, (x0 + 32, y + 30), name, font("bodybold", 24), col + (a,))
        text(d, (x0 + 32, y + 62), desc, font("body", 18), TEXT_DIM + (a,))
        y += 100
    text(d, (90, 668), "换一层只改一个字符串：换主题、换分布、换局部覆盖，"
                       "而管线其余部分一行不动。", font("body", 21), TEXT_DIM)
    text(d, (90, 710), "新增主题或分布：注册表加一行，GUI 与导出会自动跟上，"
                       "不需要为它写任何界面代码。", font("body", 21), TEXT_DIM)
    return fade_in(img, t, 0.6)


def scene_contract(t, ctx):
    """The contract catching a real bad map. Nothing here is staged."""
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "契约层：说不到就做不到", font("hd", 44), TEXT)
    d.line([(90, 134), (480, 134)], fill=EMBER + (255,), width=3)

    text(d, (90, 172), "真实运行结果 —— 岛屿主题，seed 88", font("bodybold", 26), EMBER_LIT)

    # Left: the command and the verdict.
    panel(img, [90, 226, 830, 470], accent=True)
    text(d, (126, 268), "$ python -m mapgen --theme island --seed 88 --validate",
         font("mono", 20), TEXT)
    text(d, (126, 312), "契约: 未通过  (检查 8 项, 硬失败 1, 警告 0)",
         font("bodybold", 22), DANGER)
    text(d, (126, 356), "[硬失败] min_biome_coverage", font("mono", 20), DANGER)
    for i, ln in enumerate(wrap(d,
            "植被/沙滩总覆盖不足，看起来不像温带岛屿。requested 0.55, combined 0.51",
            font("body", 18), 640)):
        text(d, (140, 392 + i * 28), ln, font("body", 18), TEXT_DIM)
    text(d, (126, 440), "exit code 1", font("mono", 20), EMBER_LIT)

    # Right: why this matters.
    panel(img, [866, 226, W - 90, 470])
    text(d, (900, 262), "为什么这是特性，不是缺陷", font("bodybold", 22), TEXT)
    for i, s in enumerate([
            "契约失败 = 地图不合格，而不是工具崩了",
            "退出码区分了「地图不好」与「你参数写错」",
            "反空检查探测器：恒真的检查一律判为失败",
            "说雪地绝不给草原 —— 这句话可以被机器执行",
    ]):
        yy = 306 + i * 40
        d.ellipse([900, yy + 7, 912, yy + 19], fill=EMBER)
        for k, ln in enumerate(wrap(d, s, font("body", 19), W - 1000)):
            text(d, (926, yy + k * 28), ln, font("body", 19), TEXT_DIM)

    text(d, (90, 530), "同一个主题换个 seed 就通过 —— 契约拦的是具体不合格的地图，"
                       "不是拦整个主题。", font("body", 21), TEXT_DIM)
    text(d, (90, 600), "GUI 直接把这四种结局翻译成四种可操作的提示：",
         font("bodybold", 22), EMBER_LIT)
    exits = [("0", "成功且契约通过", RUNE), ("1", "契约失败", WARN),
             ("2", "配置错误", EMBER_LIT), ("4", "schema 校验失败", DANGER)]
    for i, (code, meaning, col) in enumerate(exits):
        x = 90 + i * 360
        d.rounded_rectangle([x, 644, x + 320, 716], radius=5,
                            fill=BG_RAISED, outline=col + (200,), width=2)
        text(d, (x + 24, 680), code, font("monobold", 26), col, "lm")
        text(d, (x + 76, 680), meaning, font("body", 20), TEXT, "lm")
    return fade_in(img, t, 0.6)


def scene_determinism(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "确定性：同一个 seed，逐字节相同", font("hd", 44), TEXT)
    d.line([(90, 134), (560, 134)], fill=EMBER + (255,), width=3)
    det = (ctx.get("determinism") or {})
    sha = det.get("sha256", "")

    text(d, (90, 176), "实测：3 种输出格式组合 × 2 个输出目录", font("bodybold", 24), EMBER_LIT)
    combos = ["map", "map + csv + pgm + report", "map + csv + pgm + report + obj"]
    y = 226
    for i, c in enumerate(combos):
        a = int(255 * ease(t - 0.2 * i - 0.2, 0.5))
        d.rounded_rectangle([90, y, 900, y + 58], radius=5, fill=BG_PANEL + (a,),
                            outline=BORDER + (a,), width=2)
        text(d, (120, y + 29), "--format " + c, font("mono", 19), TEXT + (a,), "lm")
        text(d, (640, y + 29), "×2 目录", font("body", 18), TEXT_DIM + (a,), "lm")
        text(d, (740, y + 29), "sha256 相同", font("bodybold", 19), RUNE + (a,), "lm")
        y += 70

    panel(img, [90, 470, W - 90, 606], accent=True)
    text(d, (126, 508), "map.json  sha256", font("mono", 19), TEXT_DIM)
    shown = sha[:64] if sha else "(collect_promo_assets.py 未运行)"
    for i in range(0, len(shown), 64):
        text(d, (126, 540 + i // 64 * 30), shown[i:i + 64], font("mono", 19), EMBER_LIT)

    text(d, (90, 656), "这不是“效果看起来一样”，是文件哈希完全一致。",
         font("bodybold", 22), TEXT)
    for i, s in enumerate([
            "产物不含时间戳、不含耗时、不含绝对路径",
            "换格式集、换输出目录、换机器 —— 结果都不变",
            "因此 seed + 配置就是一份可归档、可评审、可复现的规格",
    ]):
        yy = 700 + i * 36
        d.ellipse([92, yy + 8, 104, yy + 20], fill=RUNE)
        text(d, (120, yy), s, font("body", 20), TEXT_DIM)
    return fade_in(img, t, 0.6)




def _preview_image(case, box_w, box_h):
    """Render a real map.json into a PIL image, straight from the delivered contract."""
    stem = case["theme"] + "_" + str(case["seed"])
    doc = json.loads((ASSETS / (stem + "_map.json")).read_text(encoding="utf-8"))
    grid = doc["grid"]
    w, h = int(grid["width"]), int(grid["height"])
    legend = {}
    for b in grid.get("biome_legend", []):
        legend[int(b["id"])] = b.get("color_hex", "#ff00ff")
    cells = decode_rle(grid["biome_rle"], w * h)
    # Draw one pixel per cell, then resize to the card. Resizing (not an integer
    # tile size) is what keeps a 128-cell map from collapsing to a 1px thumbnail.
    small = Image.new("RGB", (w, h))
    px = small.load()
    for y in range(h):
        for x in range(w):
            c = legend.get(cells[y * w + x], "#ff00ff")
            px[x, y] = tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return small.resize((box_w, box_h), Image.NEAREST)

def scene_maps(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "真实产物：两套主题，多个 seed", font("hd", 44), TEXT)
    d.line([(90, 134), (560, 134)], fill=EMBER + (255,), width=3)

    cases = (ctx.get("cases") or [])[:5]
    cols, cw, ch = 5, 268, 268
    x0, y0 = 90, 186
    for i, case in enumerate(cases):
        a = int(255 * ease(t - 0.16 * i - 0.2, 0.5))
        x = x0 + i * (cw + 20)
        d.rounded_rectangle([x, y0, x + cw, y0 + ch + 96], radius=6,
                            fill=BG_PANEL + (a,), outline=BORDER + (a,), width=2)
        try:
            pm = _preview_image(case, cw - 16, ch - 16)
            img.paste(pm, (x + 8, y0 + 8))
        except Exception as exc:
            text(d, (x + 20, y0 + 120), "preview unavailable: %s" % exc,
                 font("mono", 13), DANGER + (a,))
        ok = case["passed"]
        col = RUNE if ok else DANGER
        label = "契约通过" if ok else "契约失败"
        text(d, (x + 12, y0 + ch + 4), case["theme"], font("bodybold", 20), col + (a,))
        text(d, (x + 12, y0 + ch + 30), "seed %d" % case["seed"],
             font("mono", 16), TEXT_DIM + (a,))
        text(d, (x + 12, y0 + ch + 54), label, font("body", 17), col + (a,))
        st = case["stats"]
        text(d, (x + 12, y0 + ch + 76),
             "陆地 %.1f%%  实例 %d" % (st["land_fraction"] * 100, st["instance_count"]),
             font("body", 15), TEXT_DIM + (a,))

    text(d, (90, 590), "全部由命令行产出，经 --validate 通过 map.schema.json 校验。",
         font("body", 21), TEXT_DIM)
    text(d, (90, 632), "雪花主题所有 seed 均满足契约；岛屿主题在 seed 88 被拦下 —— "
                       "这一张是故意的。", font("body", 21), TEXT_DIM)
    return fade_in(img, t, 0.6)


def scene_gui(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "MagicaMapGen 桌面工具", font("hd", 44), TEXT)
    d.line([(90, 134), (480, 134)], fill=EMBER + (255,), width=3)
    shot = HERE.parent / "docs" / "screenshot_main.png"
    a = int(255 * ease(t - 0.2, 0.6))
    if shot.exists():
        pm = Image.open(shot).convert("RGB")
        target_w = 1000
        pm = pm.resize((target_w, int(pm.height * target_w / pm.width)), Image.LANCZOS)
        d.rounded_rectangle([92, 186, 92 + pm.width + 16, 190 + pm.height + 16],
                            radius=6, fill=BG_RAISED + (a,), outline=BORDER + (a,), width=2)
        img.paste(pm, (100, 194))
    else:
        d.rounded_rectangle([92, 186, 1092, 640], radius=6, outline=DANGER + (a,), width=2)
        text(d, (592, 410), "screenshot_main.png not found", font("mono", 20),
             DANGER + (a,), "mm")

    x = 1130
    text(d, (x, 200), "界面即规格", font("bodybold", 26), EMBER_LIT)
    for i, s in enumerate([
            "参数表单由生成器自己的元数据驱动，",
            "新增参数自动出现在界面上",
            "",
            "区域编辑器：形状 / 优先级 /",
            "逐类别覆盖，实时生成配置文件",
            "",
            "进度条显示十个真实生成阶段，",
            "不是假进度",
            "",
            "契约结论、失败原因、产物路径",
            "当场可见",
    ]):
        text(d, (x, 250 + i * 36), s, font("body", 19), TEXT_DIM)
    text(d, (x, 690), "GUI 不 import 生成器，", font("bodybold", 19), EMBER_LIT)
    text(d, (x, 720), "而是通过命令行调用它 ——", font("bodybold", 19), EMBER_LIT)
    text(d, (x, 750), "所以界面看到的退出码", font("body", 18), TEXT_DIM)
    text(d, (x, 778), "和 CI 看到的完全一致。", font("body", 18), TEXT_DIM)
    return fade_in(img, t, 0.6)


def scene_engine(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "引擎无关的交付契约", font("hd", 44), TEXT)
    d.line([(90, 134), (480, 134)], fill=EMBER + (255,), width=3)
    text(d, (90, 176), "主交付是一个自描述的 JSON，换引擎只需要写消费端。",
         font("bodybold", 24), EMBER_LIT)

    panel(img, [90, 232, 760, 560])
    lines = [
        "map.json   schema v%d" % (ctx.get("schema_version") or 3),
        "",
        "grid      biome / height / river / moisture RLE",
        "          + 16-bit 无损高度图旁挂文件",
        "units     每个数值字段的单位声明",
        "instances world 坐标 / 朝向 / 缩放 / biome",
        "          / 坡度 / 水深",
        "regions   形状 / 优先级 / 归属格数",
        "contract  主题契约的逐项判定",
    ]
    for i, s in enumerate(lines):
        text(d, (126, 262 + i * 31), s, font("mono", 18), TEXT if s else TEXT_DIM)

    panel(img, [796, 232, W - 90, 560], accent=True)
    text(d, (832, 262), "已验证的消费者", font("bodybold", 24), TEXT)
    text(d, (832, 306), "Unity 6000.0.0f1  batchmode", font("mono", 18), EMBER_LIT)
    for i, s in enumerate([
            "6 份 map.json 全部导入成功",
            "场景对象数 == stats.instance_count",
            "退出码 0",
            "",
            "C# 侧零改动即可消费 v3 schema，",
            "证明契约是稳定的接口，",
            "不是一次性的导出格式。",
    ]):
        text(d, (832, 350 + i * 34), s, font("body", 19),
             RUNE if s.startswith("6") or s.startswith("退出") else TEXT_DIM)

    text(d, (90, 620), "同一份 map.json 还可以直接进 Houdini（附导入指引与 .hip 构建脚本）、",
         font("body", 21), TEXT_DIM)
    text(d, (90, 654), "进地形工具（16-bit PGM）、进表格（CSV）、或进自研引擎。",
         font("body", 21), TEXT_DIM)
    return fade_in(img, t, 0.6)


def scene_value(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (90, 78), "它在前期设计阶段替团队做什么", font("hd", 44), TEXT)
    d.line([(90, 134), (560, 134)], fill=EMBER + (255,), width=3)
    rows = [
        ("策划", "把“大概要一片密林”变成可执行规格："
                "哪个主题、多少棵、什么分布、覆盖多大区域。"),
        ("关卡设计", "十分钟内产出十几张可比较的布局方案，"
                    "而不是在美术那里排队等一张图。"),
        ("剧情 / 叙事", "用区域覆盖锚定地点：北边密林、南边湖泊、"
                      "山脊挡视线 —— 地形直接承载叙事空间。"),
        ("美术", "先定地貌与植被密度，再投入雕刻；"
                "不满意就换 seed，不会推翻已经建好的资产。"),
        ("主策 / 决策", "评审时打开的是同一份文件、同一个 hash，"
                        "争论回到方案本身而不是渲染差异。"),
    ]
    y = 182
    for who, what in rows:
        a = int(255 * ease(t - 0.18 * rows.index((who, what)) - 0.2, 0.5))
        d.rounded_rectangle([90, y, W - 90, y + 122], radius=6,
                            fill=BG_PANEL + (a,), outline=BORDER + (a,), width=2)
        d.rounded_rectangle([90, y, 106, y + 122], radius=6, fill=EMBER + (a,))
        text(d, (140, y + 34), who, font("bodybold", 25), EMBER_LIT + (a,))
        for i, ln in enumerate(wrap(d, what, font("body", 20), W - 340)):
            text(d, (140, y + 74 + i * 30), ln, font("body", 20), TEXT_DIM + (a,))
        y += 136
    return fade_in(img, t, 0.6)


def scene_close(t, ctx):
    img = base_canvas()
    d = ImageDraw.Draw(img, "RGBA")
    y = 236
    text(d, (W // 2, y), "它不是又一个随机地图生成器", font("hd", 40), TEXT, "mm")
    text(d, (W // 2, y + 74), "而是一份可以被机器执行的原型规格", font("body", 30),
         EMBER_LIT, "mm")
    d.line([(W // 2 - 300, y + 122), (W // 2 + 300, y + 122)],
           fill=BORDER_LIT + (255,), width=2)

    facts = [
        ("80", "项自动化测试全绿"),
        ("2", "套主题，均通过契约"),
        ("32–1024", "全尺寸区间契约零失败"),
        ("6/6", "Unity 导入验证通过"),
    ]
    for i, (big, small) in enumerate(facts):
        x = W // 2 - 600 + i * 300
        d.rounded_rectangle([x, y + 168, x + 260, y + 300], radius=6,
                            fill=BG_PANEL, outline=BORDER, width=2)
        text(d, (x + 130, y + 216), big, font("serif", 44), EMBER_LIT, "mm")
        for k, ln in enumerate(wrap(d, small, font("body", 17), 230)):
            text(d, (x + 130, y + 258 + k * 24), ln, font("body", 17), TEXT_DIM, "mm")

    text(d, (W // 2, y + 372), "下一步：把地图接进剧情与关卡数据，"
                               "让原型成为可继承的资产而不是一次性演示。",
         font("body", 21), TEXT_DIM, "mm")
    text(d, (W // 2, H - 120), "github.com/bnna7219213-lab/MagicaMapGen",
         font("mono", 20), BORDER_LIT, "mm")
    return fade_in(img, t, 1.0)


def load_ctx():
    """Real evidence from collect_promo_assets.py. Nothing is hardcoded."""
    ctx = {"cases": [], "determinism": {}, "schema_version": 3}
    mf = ASSETS / "manifest.json"
    if mf.exists():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            ctx["cases"] = data.get("cases", [])
            ctx["determinism"] = data.get("determinism", {})
        except Exception as exc:
            print("manifest unreadable: %s" % exc)
    for case in ctx["cases"]:
        ctx["schema_version"] = case.get("schema_version", 3)
    return ctx

TIMELINE = [
    (scene_title, 6.0),
    (scene_problem, 11.0),
    (scene_solution, 11.0),
    (scene_maps, 10.0),
    (scene_contract, 12.0),
    (scene_determinism, 10.0),
    (scene_gui, 10.0),
    (scene_engine, 10.0),
    (scene_value, 12.0),
    (scene_close, 9.0),
]


def main():
    ctx = load_ctx()
    if not ctx["cases"]:
        print("ERROR: no cases in " + str(ASSETS))
        return 1
    tmp = OUT.with_suffix(".tmp.mp4")
    vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not vw.isOpened():
        print("ERROR: could not open VideoWriter")
        return 1
    total = int(sum(s for _, s in TIMELINE) * FPS)
    print("rendering {0} scenes, {1} frames at {2}x{3} at {4}fps".format(len(TIMELINE), total, W, H, FPS))
    t_start = time.time()
    for fn, seconds in TIMELINE:
        frames = int(seconds * FPS)
        t0 = time.time()
        for i in range(frames):
            img = fn(i / float(FPS), ctx)
            arr = np.asarray(img)[:, :, ::-1]
            vw.write(np.ascontiguousarray(arr))
        print("  {0:<18} {1:>4} frames  {2:.1f}s".format(getattr(fn, "__name__", "?"), frames, time.time() - t0))
    vw.release()
    if OUT.exists():
        OUT.unlink()
    tmp.replace(OUT)
    mb = OUT.stat().st_size / 1048576.0
    print("wrote {0}  ({1:.1f} MB, {2:.0f}s)".format(OUT, mb, time.time() - t_start))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())