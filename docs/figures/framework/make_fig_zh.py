"""Generate the methodology framework figure (SVG) for 能见度 / Nengjiandu."""
import math, html

W, H = 1800, 1080
SANS = "Inter, 'Noto Sans CJK SC', 'Microsoft YaHei', 'PingFang SC', sans-serif"
MATH = "'Latin Modern Roman', 'LM Roman 10', 'Times New Roman', serif"

# palette (muted, print-friendly)
INK = "#1F2933"; SUB = "#52606D"; LINE = "#7B8794"
C = {
    "data":  ("#3E4C59", "#F5F7FA", "#E4E7EB"),
    "phys":  ("#1D5FA8", "#EEF5FD", "#D3E4F8"),
    "dec":   ("#1E7A57", "#EEF8F3", "#CDEBDD"),
    "ui":    ("#B35A12", "#FFF6EC", "#FBE1C6"),
    "llm":   ("#6B3FB5", "#F5F0FD", "#E0D3F6"),
}
RED = "#B83232"

out = []
def add(s): out.append(s)
def esc(s): return html.escape(s, quote=False)

def text(x, y, s, size=13, weight=400, fill=INK, anchor="start", family=SANS, italic=False, extra=""):
    st = ' font-style="italic"' if italic else ""
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{st} {extra}>{s}</text>')

def rich(x, y, parts, size=13, anchor="start", fill=INK):
    """parts: list of (str, style) style in {'', 'b', 'i', 'm', 'mi', 'sub', 'sup', 'msub'}"""
    spans = []
    for s, st in parts:
        s = esc(s)
        if st == "b": spans.append(f'<tspan font-weight="600">{s}</tspan>')
        elif st == "i": spans.append(f'<tspan font-style="italic">{s}</tspan>')
        elif st == "m": spans.append(f'<tspan font-family="{MATH}" font-size="{size+2}">{s}</tspan>')
        elif st == "mi": spans.append(f'<tspan font-family="{MATH}" font-size="{size+2}" font-style="italic">{s}</tspan>')
        elif st == "sub": spans.append(f'<tspan font-family="{MATH}" font-size="{size-2}" baseline-shift="-25%" font-style="italic">{s}</tspan>')
        elif st == "subr": spans.append(f'<tspan font-family="{MATH}" font-size="{size-2}" baseline-shift="-25%">{s}</tspan>')
        elif st == "sup": spans.append(f'<tspan font-family="{MATH}" font-size="{size-2}" baseline-shift="40%">{s}</tspan>')
        else: spans.append(f'<tspan>{s}</tspan>')
    add(f'<text x="{x}" y="{y}" font-family="{SANS}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" xml:space="preserve">{"".join(spans)}</text>')

def box(x, y, w, h, kind, rx=10, dash=False, sw=1.4, fill=None):
    stroke, bg, _ = C[kind]
    d = ' stroke-dasharray="5 4"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill or bg}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

def header(x, y, w, kind, label, title):
    stroke, _, tint = C[kind]
    add(f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="8" fill="{stroke}"/>')
    text(x + 14, y + 22.5, f'<tspan font-weight="700">{esc(label)}</tspan>  {esc(title)}', 15, 500, "#FFFFFF")

def module_title(x, y, s, kind, num=None):
    stroke = C[kind][0]
    if num:
        add(f'<circle cx="{x+9}" cy="{y-5}" r="9" fill="{stroke}"/>')
        text(x + 9, y - 1, num, 11, 700, "#FFFFFF", "middle")
        x += 24
    text(x, y, esc(s), 14.5, 650, stroke)

def badge(cx, cy, label):
    add(f'<g><circle cx="{cx}" cy="{cy}" r="13" fill="{RED}" stroke="#FFFFFF" stroke-width="2"/>'
        f'<text x="{cx}" y="{cy+4.2}" font-family="{SANS}" font-size="11.5" font-weight="700" fill="#FFFFFF" text-anchor="middle">{label}</text></g>')

def arrow(points, color=LINE, sw=1.6, dash=False, head="ah"):
    d = " ".join(("M" if i == 0 else "L") + f"{x},{y}" for i, (x, y) in enumerate(points))
    da = ' stroke-dasharray="6 4"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{da} marker-end="url(#{head})"/>')

def vis(s, size):
    return sum(size * (1.0 if ord(ch) > 0x2E80 else 0.56) for ch in s)

def label_pill(x, y, s, color=SUB, anchor="middle", size=12, bg="#FFFFFF"):
    w = vis(s, size) + 14
    x0 = x - w / 2 if anchor == "middle" else x
    add(f'<rect x="{x0}" y="{y-13}" width="{w}" height="19" rx="9.5" fill="{bg}" stroke="none"/>')
    text(x0 + w / 2, y + 1.5, esc(s), size, 500, color, "middle", extra='font-style="italic"')

def chip(x, y, s, kind, w=None):
    stroke, _, tint = C[kind]
    w = w or vis(s, 11.5) + 18
    add(f'<rect x="{x}" y="{y}" width="{w}" height="22" rx="11" fill="{tint}" stroke="{stroke}" stroke-width="0.8"/>')
    text(x + w / 2, y + 15, esc(s), 11.5, 500, stroke, "middle")
    return w

# ---------------------------------------------------------------- canvas
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
    f'aria-label="能见度方法框架：多源输入经物理逐时仿真、决策分析进入决策界面，并由人机协同的本地大模型交互层形成闭环。">')
add('<defs>'
    f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker>'
    f'<marker id="ahl" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C["llm"][0]}"/></marker>'
    f'<marker id="ahp" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C["phys"][0]}"/></marker>'
    f'<marker id="ahd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C["dec"][0]}"/></marker>'
    '</defs>')
add(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#FFFFFF"/>')

# column geometry
AX, AW = 30, 270
BX, BW = 350, 560
CX, CW = 970, 510
DX, DW = 1530, 240
TOP = 205          # main panel top
BOT = 868          # main panel bottom

# ---------------------------------------------------------------- (e) LLM band
EY, EH = 28, 140
add(f'<rect x="{AX-10}" y="{EY-10}" width="{W-2*AX+20}" height="{EH+20}" rx="14" fill="#FBF9FE" stroke="{C["llm"][2]}" stroke-width="1"/>')
text(AX + 4, EY + 12, f'<tspan font-weight="700">(e)</tspan>  人机协同的自然语言交互', 14.5, 600, C["llm"][0])
text(W - AX - 4, EY + 12, "重规划闭环：自右向左", 12, 400, SUB, "end", extra='font-style="italic"')

by = EY + 30; bh = 92
# U: decision maker (right)
box(1530, by, 240, bh, "llm")
module_title(1546, by + 24, "决策者", "llm")
text(1546, by + 46, "用自然语言提出需求", 12.5, 400, SUB)
text(1546, by + 66, "“每间改 3 台，", 12.5, 400, INK, extra='font-style="italic"')
text(1546, by + 83, "  多余电不卖给电网”", 12.5, 400, INK, extra='font-style="italic"')
# L: local LLM
box(1110, by, 360, bh, "llm")
module_title(1126, by + 24, "本地大模型（离线部署）", "llm")
text(1126, by + 46, "在严格 JSON 模式下调用工具", 12.5, 400, SUB)
text(1126, by + 65, "只修改任务字段，从不输出计算结果", 12.5, 400, SUB)
text(1126, by + 84, "数据不出本机", 12.5, 400, SUB)
badge(1458, by + 4, "C5")
# E: proposed edits
box(690, by, 360, bh, "llm")
module_title(706, by + 24, "修改建议 ΔΘ", "llm")
rich(706, by + 47, [("字段：", ""), ("原值", "i"), (" → ", ""), ("新值", "i"), ("（按接口取值范围校验）", "")], 12.5, fill=SUB)
text(706, by + 66, "不支持的内容逐条列出，不静默丢弃", 12.5, 400, SUB)
text(706, by + 85, "表述不清 → 反问澄清", 12.5, 400, SUB)
# K: confirmation
box(350, by, 280, bh, "llm")
module_title(366, by + 24, "用户确认", "llm")
text(366, by + 46, "采用或修改建议", 12.5, 400, SUB)
rich(366, by + 66, [("→ 结构化任务 ", ""), ("Θ", "mi")], 12.5, fill=SUB)
text(366, by + 85, "（房间、空调、光伏、风机、电价、报价）", 12, 400, SUB)
mid = by + bh / 2
arrow([(1530, mid), (1472, mid)], C["llm"][0], 1.6, head="ahl")
arrow([(1110, mid), (1052, mid)], C["llm"][0], 1.6, head="ahl")
arrow([(690, mid), (632, mid)], C["llm"][0], 1.6, head="ahl")
# K -> inputs (left, then down)
arrow([(350, mid), (165, mid), (165, TOP - 2)], C["llm"][0], 1.6, head="ahl")
label_pill(240, mid - 12, "任务 Θ", C["llm"][0])
# outputs -> user (up)
arrow([(1650, TOP - 2), (1650, by + bh + 2)], C["llm"][0], 1.6, dash=True, head="ahl")
label_pill(1712, TOP - 18, "查看 / 调整", C["llm"][0], size=11.5)

# ---------------------------------------------------------------- (a) inputs
header(AX, TOP, AW, "data", "(a)", "多源输入")
iy = TOP + 50; ih = 140; ig = 14
inputs = [
    ("逐时气象", ["再分析数据，8,784 h（2024 年）", "气温、湿度、气压、辐照、风速", "时段语义统一处理"]),
    ("建筑与空调", ["房间尺寸、围护结构、使用时段", "空调目录：额定制冷量、COP", "N 间房 × 每间 n 台"]),
    ("场地与设备", ["屋顶面积 → 光伏容量上限", "认证小风机功率曲线", "用户报价：光伏、风机、储能"]),
    ("政策与市场", ["官方四段分时电价", "尖峰：7–9 月及日最高温 ≥ 35 °C", "广东电网排放因子 0.4419 kgCO₂/kWh"]),
]
ys = []
for i, (t, lines) in enumerate(inputs):
    y = iy + i * (ih + ig); ys.append(y)
    box(AX, y, AW, ih, "data")
    module_title(AX + 14, y + 26, t, "data")
    for j, l in enumerate(lines):
        add(f'<circle cx="{AX+19}" cy="{y+50+j*24}" r="2.2" fill="{LINE}"/>')
        text(AX + 28, y + 54 + j * 24, esc(l), 12.3, 400, SUB)
badge(AX + AW - 8, ys[3] + 6, "C3")
# input bus x=325
bus_x = 325
for y in ys[:3]:
    add(f'<path d="M{AX+AW},{y+ih/2} L{bus_x},{y+ih/2}" stroke="{LINE}" stroke-width="1.4" fill="none"/>')
add(f'<path d="M{bus_x},{ys[0]+ih/2} L{bus_x},{ys[2]+ih/2}" stroke="{LINE}" stroke-width="1.4" fill="none"/>')
for y in ys[:3]:
    add(f'<circle cx="{bus_x}" cy="{y+ih/2}" r="2.6" fill="{LINE}"/>')

# ---------------------------------------------------------------- (b) physics core
header(BX, TOP, BW, "phys", "(b)", "物理驱动的逐时仿真")
# B1 room model
b1y, b1h = TOP + 50, 238
box(BX, b1y, BW, b1h, "phys")
module_title(BX + 16, b1y + 27, "集总 RC 房间热湿模型", "phys", "1")
rich(BX + 24, b1y + 62, [("C", "mi"), (" dT", "m"), ("/", "m"), ("dt", "m"), (" = ", "m"), ("UA", "mi"), ("(", "m"), ("T", "mi"), ("out", "sub"), (" − ", "m"), ("T", "mi"), (")", "m"),
                         (" + ", "m"), ("Q", "mi"), ("sol", "sub"), (" + ", "m"), ("Q", "mi"), ("int", "sub"), (" + ", "m"), ("Q", "mi"), ("vent", "sub"), (" − ", "m"), ("Q", "mi"), ("AC", "sub")], 14)
rich(BX + 24, b1y + 92, [("m", "mi"), ("a", "sub"), (" dw", "m"), ("/", "m"), ("dt", "m"), (" = ", "m"), ("ṁ", "mi"), ("w", "sub"), ("(", "m"), ("w", "mi"), ("out", "sub"), (" − ", "m"), ("w", "mi"), (")", "m"), (" + ", "m"), ("G", "mi"), ("lat", "sub"), (" − ", "m"), ("Q", "mi"), ("lat", "sub"), ("/", "m"), ("h", "mi"), ("fg", "sub")], 14)
rich(BX + 24, b1y + 122, [("P", "mi"), ("AC", "sub"), ("(", "m"), ("t", "mi"), (")", "m"), (" = ", "m"), ("Q", "mi"), ("AC", "sub"), ("(", "m"), ("t", "mi"), (")", "m"), (" / COP(", "m"), ("T", "mi"), ("out", "sub"), (")", "m"),
                          ("     显热 + 潜热，  ", ""), ("Q", "mi"), ("AC", "sub"), (" ≤ ", "m"), ("n", "mi"), ("Q", "mi"), ("rated", "subr")], 14)
# adequacy gate sub-box
gy = b1y + 142
add(f'<rect x="{BX+16}" y="{gy}" width="{BW-32}" height="80" rx="8" fill="#FFFFFF" stroke="{C["phys"][0]}" stroke-width="1" stroke-dasharray="4 3"/>')
text(BX + 30, gy + 22, '<tspan font-weight="650" fill="#1D5FA8">舒适度约束选台</tspan>  ·  上班前预冷 60 分钟（预冷用电计入）', 12.8, 400, INK)
text(BX + 30, gy + 43, "冷量不足与温湿度未达标只在使用时段判定", 12.5, 400, SUB)
rich(BX + 30, gy + 65, [("台数比选 ", ""), ("n", "mi"), (" = 1…", "m"), ("n", "mi"), ("max", "subr"), ("  →  ", ""), ("n*", "mi"), (" = min{ ", "m"), ("n", "mi"), (" : 冷量不足 = 0 }", "m"), ("  （最少达标台数）", "")], 12.8, fill=SUB)
badge(BX + BW - 10, b1y + 6, "C2")

# B2 generation
b2y, b2h = b1y + b1h + 18, 128
gx = BX + 46; gw2 = (BW - 46 - 14) / 2
for k, (title, l1, l2, l3) in enumerate([
        ("光伏发电", "pvlib（PVWatts）· 斜面辐照换算", "由气温与风速计算组件温度", "容量受屋顶面积约束"),
        ("风力发电", "SD6 认证功率曲线", "轮毂高度风速（Hellman 幂律）：", None)]):
    x = gx + k * (gw2 + 14)
    box(x, b2y, gw2, b2h, "phys")
    module_title(x + 14, b2y + 26, title, "phys", "2" if k == 0 else "3")
    text(x + 16, b2y + 52, esc(l1), 12.3, 400, SUB)
    text(x + 16, b2y + 74, esc(l2), 12.3, 400, SUB)
    if l3: text(x + 16, b2y + 96, esc(l3), 12.3, 400, SUB)
    else:
        rich(x + 16, b2y + 100, [("v", "mi"), ("h", "sub"), (" = ", "m"), ("v", "mi"), ("ref", "subr"), ("(", "m"), ("h", "mi"), ("/", "m"), ("h", "mi"), ("ref", "subr"), (")", "m"), ("α", "sup")], 14)

# B3 matching
b3y = b2y + b2h + 18; b3h = BOT - b3y
box(BX, b3y, BW, b3h, "phys")
module_title(BX + 16, b3y + 27, "逐时能量匹配", "phys", "4")
text(BX + 16 + 250, b3y + 27, "t = 1 … 8,784", 12.5, 400, SUB, extra='font-style="italic"')
rich(BX + 24, b3y + 60, [("s", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), (" = min{", "m"), ("G", "mi"), ("(", "m"), ("t", "mi"), ("), ", "m"), ("L", "mi"), ("(", "m"), ("t", "mi"), (")}", "m")], 14)
rich(BX + 24, b3y + 86, [("g", "mi"), ("imp", "subr"), (" = ", "m"), ("L", "mi"), (" − ", "m"), ("s", "mi")], 14)
rich(BX + 150, b3y + 86, [("e", "mi"), ("sur", "subr"), (" = ", "m"), ("G", "mi"), (" − ", "m"), ("s", "mi")], 14)
text(BX + 24, b3y + 112, "自用 · 电网购电 · 余电", 12.3, 400, SUB)
add(f'<line x1="{BX+24}" y1="{b3y+126}" x2="{BX+262}" y2="{b3y+126}" stroke="{C["phys"][2]}" stroke-width="1"/>')
text(BX + 24, b3y + 146, "对比：传统全年粗算", 12, 600, RED)
rich(BX + 24, b3y + 168, [("E", "mi"), ("gen", "subr"), (" × ", "m"), ("p̄", "mi"), ("（忽略时间错配与分时电价）", "")], 12.5, fill=SUB)
badge(BX + BW - 10, b3y + 6, "C1")

# mini daily profile chart
cx0, cx1 = BX + 300, BX + BW - 22
cy0, cy1 = b3y + 62, b3y + b3h - 30
pxh = (cx1 - cx0) / 24.0
def X(h): return cx0 + h * pxh
def Yv(v): return cy1 - v * (cy1 - cy0)
hours = [i / 4 for i in range(0, 97)]
def G(h): return 0.92 * math.sin(math.pi * (h - 6) / 12) ** 1.15 if 6 < h < 18 else 0.0
def L(h): return 0.55 if 7 <= h < 18 else (0.0)
def Lsm(h):
    v = L(h)
    if 7 <= h < 8: v = 0.72          # pre-cooling peak
    return v
def poly(fn_top, fn_bot):
    top = [(X(h), Yv(fn_top(h))) for h in hours]
    bot = [(X(h), Yv(fn_bot(h))) for h in reversed(hours)]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in top + bot) + " Z"
add(f'<rect x="{cx0}" y="{cy0-6}" width="{cx1-cx0}" height="{cy1-cy0+6}" fill="#FFFFFF" stroke="{C["phys"][2]}" stroke-width="1"/>')
add(f'<path d="{poly(lambda h: min(G(h), Lsm(h)), lambda h: 0)}" fill="#2F9E6B" fill-opacity="0.55"/>')
add(f'<path d="{poly(lambda h: G(h) if G(h) > Lsm(h) else min(G(h), Lsm(h)), lambda h: min(G(h), Lsm(h)))}" fill="#E8A33D" fill-opacity="0.55"/>')
add(f'<path d="{poly(lambda h: Lsm(h) if Lsm(h) > G(h) else min(G(h), Lsm(h)), lambda h: min(G(h), Lsm(h)))}" fill="#9AA5B1" fill-opacity="0.55"/>')
pts = " ".join(f"{X(h):.1f},{Yv(G(h)):.1f}" for h in hours)
add(f'<polyline points="{pts}" fill="none" stroke="#C47A12" stroke-width="1.8"/>')
pts = " ".join(f"{X(h):.1f},{Yv(Lsm(h)):.1f}" for h in hours)
add(f'<polyline points="{pts}" fill="none" stroke="{C["phys"][0]}" stroke-width="1.8"/>')
for hh in (0, 6, 12, 18, 24):
    text(X(hh), cy1 + 15, f"{hh:02d}h", 10.5, 400, SUB, "middle")
add(f'<line x1="{cx0}" y1="{cy1}" x2="{cx1}" y2="{cy1}" stroke="{LINE}" stroke-width="1"/>')
# legend
ly = cy0 - 26; lx = cx0 + 2
for i, (col, lab) in enumerate([("#2F9E6B", "自用 s"), ("#E8A33D", "余电"), ("#9AA5B1", "购电")]):
    add(f'<rect x="{lx + i*82}" y="{ly}" width="10" height="10" fill="{col}" fill-opacity="0.7"/>')
    text(lx + i * 82 + 14, ly + 9.5, lab, 10.5, 500, SUB)
text(X(12.6), Yv(0.97), "G(t)", 11, 600, "#C47A12", "start", MATH, True)
text(X(18.4), Yv(0.62), "L(t)", 11, 600, C["phys"][0], "start", MATH, True)
text(X(5.6), Yv(0.80), "预冷", 9.5, 500, C["phys"][0], "middle")

# internal arrows in B
chan = BX + 22
add(f'<path d="M{chan},{b1y+b1h} L{chan},{b3y-2}" stroke="{C["phys"][0]}" stroke-width="1.6" fill="none" marker-end="url(#ahp)"/>')
text(chan - 7, (b2y + b2y + b2h) / 2, "L(t)", 12.5, 600, C["phys"][0], "middle", MATH, True,
     extra=f'transform="rotate(-90 {chan-7} {(b2y*2+b2h)/2})"')
for k in range(2):
    x = gx + k * (gw2 + 14) + gw2 / 2
    add(f'<path d="M{x},{b2y+b2h} L{x},{b3y-2}" stroke="{C["phys"][0]}" stroke-width="1.6" fill="none" marker-end="url(#ahp)"/>')
rich(gx + gw2 + 7, b3y - 5, [("G", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), (" = ", "m"), ("G", "mi"), ("PV", "subr"), (" + ", "m"), ("G", "mi"), ("wind", "subr")], 11.5, "middle", C["phys"][0])

# bus -> B1, B2
arrow([(bus_x, b1y + 120), (BX - 2, b1y + 120)], LINE, 1.5)
add(f'<path d="M{bus_x},{ys[2]+ih/2} L{bus_x},{b2y+64}" stroke="{LINE}" stroke-width="1.4" fill="none"/>')
arrow([(bus_x, b2y + 64), (gx - 2, b2y + 64)], LINE, 1.5)
label_pill((bus_x + BX) / 2 - 2, b1y + 105, "Θ, wx", SUB, size=10.5)

# ---------------------------------------------------------------- (c) decision analytics
header(CX, TOP, CW, "dec", "(c)", "决策分析")
c_x = CX + 22; c_w = CW - 22
cy = TOP + 50
mods = []
def dmod(y, h, title, num):
    box(c_x, y, c_w, h, "dec")
    module_title(c_x + 14, y + 26, title, "dec", num)
    mods.append((y, h))

h1 = 92; dmod(cy, h1, "方案与容量比选", "5")
xx = c_x + 16
for s in ["S0 只用电网", "S1 光伏", "S2 风机", "S3 风光组合"]:
    xx += chip(xx, cy + 40, s, "dec") + 8
rich(c_x + 16, cy + 82, [("光伏容量 ", ""), ("k", "mi"), (" ∈ ", "m"), ("K", "mi"), ("（受屋顶约束）；S0 始终作为基准", "")], 12.3, fill=SUB)

y2 = cy + h1 + 14; h2 = 128; dmod(y2, h2, "分时电价下的全生命周期经济性", "6")
rich(c_x + 16, y2 + 58, [("TC", "mi"), (" = ", "m"), ("I", "mi"), ("0", "subr"), (" + Σ", "m"), ("y", "sub"), (" [ Σ", "m"), ("t", "sub"), (" ", "m"), ("p", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), ("g", "mi"), ("imp", "subr"), ("(", "m"), ("t", "mi"), (")", "m"), (" + ", "m"), ("M", "mi"), ("y", "sub"), (" + ", "m"), ("R", "mi"), ("y", "sub"), (" ] / (1+", "m"), ("r", "mi"), (")", "m"), ("y", "sup"), (" − ", "m"), ("V", "mi"), ("res", "subr")], 14)
text(c_x + 16, y2 + 86, "p(t)：按小时、月份和日最高温取谷 / 平 / 峰 / 尖峰电价", 12.3, 400, SUB)
rich(c_x + 16, y2 + 108, [("输出：10 年总花费、相对 S0 的 ", ""), ("Δ", "m"), ("TC", "mi"), ("（保留正负）、简单回本年限", "")], 12.3, fill=SUB)

y3 = y2 + h2 + 14; h3 = 92; dmod(y3, h3, "碳排放核算", "7")
rich(c_x + 16, y3 + 56, [("Δ", "m"), ("CO", "mi"), ("2", "subr"), (" = Σ", "m"), ("t", "sub"), (" ", "m"), ("s", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), (" · ", "m"), ("EF", "mi"), ("grid", "subr")], 14)
text(c_x + 16, y3 + 80, "采用官方省级排放因子；碳价仅作情景展示", 12.3, 400, SUB)

y4 = y3 + h3 + 14; h4 = 96; dmod(y4, h4, "余电利用（附加路径）", "8")
text(c_x + 16, y4 + 52, "储能：规则调度，η = 0.90 → 投入与回本", 12.3, 400, SUB)
text(c_x + 16, y4 + 74, "卖给电网：同一份余电的收入粗算", 12.3, 400, SUB)
text(c_x + c_w - 14, y4 + 88, "不计入主方案排序", 11, 400, SUB, "end", extra='font-style="italic"')

y5 = y4 + h4 + 14; h5 = BOT - y5; dmod(y5, h5, "约束感知的状态判定与推荐", "9")
xx = c_x + 16
for s in ["可行", "超预算", "报价未知", "冷量缺口"]:
    xx += chip(xx, y5 + 40, s, "dec") + 8
rich(c_x + 16, y5 + 84, [("在可比较方案中取 ", ""), ("argmin", "m"), (" TC", "mi"), (" 作为推荐；", "")], 12.3, fill=SUB)
text(c_x + 16, y5 + 104, "条件不全 ≠ 淘汰；有冷量缺口绝不显示为达标", 12.3, 400, SUB)
badge(c_x + c_w - 10, y5 + 6, "C4")
badge(c_x + c_w - 10, y2 + 6, "C3")

# decision bus at x = CX + 6
dbx = CX + 6
add(f'<path d="M{dbx},{cy+h1/2} L{dbx},{y5+h5/2}" stroke="{C["dec"][0]}" stroke-width="1.6" fill="none"/>')
for (yy, hh) in mods:
    arrow([(dbx, yy + hh / 2), (c_x - 2, yy + hh / 2)], C["dec"][0], 1.5, head="ahd")
# B3 -> bus
arrow([(BX + BW, b3y + 70), (dbx, b3y + 70)], C["phys"][0], 1.8, head="ahp")
label_pill((BX + BW + dbx) / 2 + 2, b3y + 56, "逐时电量", C["phys"][0], size=10.5)
# policy & market -> bus (route under panels)
py = BOT + 18
add(f'<path d="M{AX+AW/2},{ys[3]+ih} L{AX+AW/2},{py} L{dbx},{py} L{dbx},{y5+h5/2}" stroke="{C["data"][0]}" stroke-width="1.5" fill="none" stroke-dasharray="6 4" marker-end="url(#ah)"/>')
label_pill((BX + BX + BW) / 2, py, "电价 p(t)、排放因子、报价", C["data"][0], size=11)

# ---------------------------------------------------------------- (d) decision interface
header(DX, TOP, DW, "ui", "(d)", "决策界面")
dx = DX; dy = TOP + 50
box(dx, dy, DW, 140, "ui")
module_title(dx + 14, dy + 26, "渐进式计算", "ui")
text(dx + 16, dy + 52, "典型周预览", 12.3, 600, INK)
text(dx + 16, dy + 70, "仅物理匹配，< 1 秒", 12.3, 400, SUB)
text(dx + 16, dy + 96, "全年后台计算", 12.3, 600, INK)
text(dx + 16, dy + 114, "显示真实进度", 12.3, 400, SUB)
badge(dx + DW - 10, dy + 6, "C6")
# visual outputs
oy = dy + 154; oh = 300
box(dx, oy, DW, oh, "ui")
module_title(dx + 14, oy + 26, "可视化证据", "ui")
# mini calendar heatmap
hx, hy = dx + 16, oy + 42; cw_, ch_ = (DW - 32) / 24, 5.2
import random
random.seed(7)
for m in range(12):
    cool = max(0.0, math.sin(math.pi * (m - 2.5) / 8.5)) if 3 <= m <= 10 else 0.0   # AC demand by month
    irr = 0.55 + 0.45 * math.sin(math.pi * (m - 1) / 10) if 1 <= m <= 11 else 0.5
    for h in range(24):
        sun = math.sin(math.pi * (h - 6) / 12) if 6 < h < 18 else 0.0
        gen = sun * irr
        occ = 7 <= h < 18
        load = (0.06 + 0.94 * cool) * (1.0 if occ else 0.0)
        self_ = min(gen, load); sur = gen - self_; imp = load - self_
        if gen < 0.03 and load < 0.03: col, op = "#E4E7EB", 1.0
        else:
            k = max((self_, "#2F9E6B"), (sur, "#E8A33D"), (imp, "#9AA5B1"))
            col, op = k[1], 0.35 + 0.65 * min(1.0, k[0] / 0.7)
        add(f'<rect x="{hx + h*cw_:.1f}" y="{hy + m*(ch_+1.2):.1f}" width="{cw_-0.8:.1f}" height="{ch_}" fill="{col}" fill-opacity="{op:.2f}"/>')
text(dx + 16, hy + 12 * (ch_ + 1.2) + 14, "能源日历（月 × 小时）", 11.5, 500, SUB)
# capacity cost curve
ccy = hy + 12 * (ch_ + 1.2) + 30
ax0, ax1, ay0, ay1 = dx + 22, dx + DW - 18, ccy, ccy + 64
add(f'<line x1="{ax0}" y1="{ay1}" x2="{ax1}" y2="{ay1}" stroke="{LINE}"/><line x1="{ax0}" y1="{ay0}" x2="{ax0}" y2="{ay1}" stroke="{LINE}"/>')
pts = []
for i in range(7):
    k = i / 6
    v = 0.75 - 0.9 * k + 1.15 * k * k
    pts.append((ax0 + 10 + k * (ax1 - ax0 - 20), ay1 - 6 - v * 50))
add('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f'" fill="none" stroke="{C["ui"][0]}" stroke-width="1.8"/>')
best = max(pts, key=lambda p: p[1])
for p in pts:
    add(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="2.6" fill="#FFFFFF" stroke="{C["ui"][0]}" stroke-width="1.4"/>')
add(f'<circle cx="{best[0]:.1f}" cy="{best[1]:.1f}" r="4.5" fill="{C["ui"][0]}"/>')
text(dx + 16, ay1 + 16, "容量—花费曲线（标出最优）", 11.5, 500, SUB)
text(dx + 16, ay1 + 40, "10 年总账 · 减碳 · 储能", 11.5, 500, SUB)
text(dx + 16, ay1 + 56, "逐时 CSV / JSON / 可打印简报", 11.5, 500, SUB)
# saved plans
sy = oy + oh + 14; sh = BOT - sy
box(dx, sy, DW, sh, "ui")
module_title(dx + 14, sy + 26, "可追溯的输出", "ui")
text(dx + 16, sy + 52, "每个数字都来自计算", 12.3, 400, SUB)
text(dx + 16, sy + 72, "改条件即令旧结果失效", 12.3, 400, SUB)
text(dx + 16, sy + 92, "保存的方案可并排对比", 12.3, 400, SUB)
text(dx + 16, sy + 112, "来源与哈希可追溯", 12.3, 400, SUB)
# C -> D
arrow([(CX + CW, TOP + 330), (DX - 2, TOP + 330)], C["dec"][0], 1.8, head="ahd")
label_pill((CX + CW + DX) / 2, TOP + 312, "结果", C["dec"][0], size=10.5)

# ---------------------------------------------------------------- innovations strip
iy0 = 912
add(f'<line x1="{AX}" y1="{iy0-8}" x2="{W-AX}" y2="{iy0-8}" stroke="{C["data"][2]}" stroke-width="1"/>')
text(AX, iy0 + 14, "主要创新点", 14.5, 700, INK)
inn = [
    ("C1", "逐时耦合", "负荷、光伏与风电按小时匹配并按分时电价计费，|取代“年发电量 × 平均电价”的粗算。"),
    ("C2", "舒适度约束选台", "空调负荷与台数由热湿物理模型和明确的|达标规则共同确定。"),
    ("C3", "贴合政策的经济性", "官方电价（含高温触发尖峰）、全生命周期|费用与省级排放因子。"),
    ("C4", "诚实的决策语义", "条件不全不等于淘汰；冷量缺口必须标出；|“只用电网”始终保留作对比基准。"),
    ("C5", "大模型做界面，不做计算器", "本地大模型把自然语言转成经校验的任务修改；|所有数字由确定性程序计算。"),
    ("C6", "渐进式计算", "秒级典型周预览，随后全年后台计算并显示|真实进度，支持交互式使用。"),
]
colw = (W - 2 * AX - 150) / 3
for i, (b, t, d) in enumerate(inn):
    col, row = i % 3, i // 3
    x = AX + 150 + col * colw; y = iy0 + row * 76
    badge(x + 13, y + 9, b)
    text(x + 34, y + 14, esc(t), 13.5, 650, INK)
    # wrap description into two lines
    lines = d.split("|") if "|" in d else [d]
    words = []
    for w_ in words:
        if len(lines[-1]) + len(w_) + 1 > 62: lines.append(w_)
        else: lines[-1] = (lines[-1] + " " + w_).strip()
    for j, l in enumerate(lines[:2]):
        text(x + 34, y + 34 + j * 17, esc(l), 12, 400, SUB)

add("</svg>")
open("framework_zh.svg", "w", encoding="utf-8").write("\n".join(o for o in out if o))
print("ok")
