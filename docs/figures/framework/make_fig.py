"""Generate the methodology framework figure (SVG) for 能见度 / Nengjiandu."""
import math, html

W, H = 1800, 1080
SANS = "Inter, 'Helvetica Neue', Arial, sans-serif"
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

def label_pill(x, y, s, color=SUB, anchor="middle", size=12, bg="#FFFFFF"):
    w = len(s) * size * 0.56 + 14
    x0 = x - w / 2 if anchor == "middle" else x
    add(f'<rect x="{x0}" y="{y-13}" width="{w}" height="19" rx="9.5" fill="{bg}" stroke="none"/>')
    text(x0 + w / 2, y + 1.5, esc(s), size, 500, color, "middle", extra='font-style="italic"')

def chip(x, y, s, kind, w=None):
    stroke, _, tint = C[kind]
    w = w or len(s) * 6.9 + 18
    add(f'<rect x="{x}" y="{y}" width="{w}" height="22" rx="11" fill="{tint}" stroke="{stroke}" stroke-width="0.8"/>')
    text(x + w / 2, y + 15, esc(s), 11.5, 500, stroke, "middle")
    return w

# ---------------------------------------------------------------- canvas
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
    f'aria-label="Framework of Nengjiandu: multi-source inputs feed a physics-based hourly simulation, decision analytics and a decision interface, closed by a human-in-the-loop local-LLM interface.">')
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
text(AX + 4, EY + 12, f'<tspan font-weight="700">(e)</tspan>  Human-in-the-loop language interface', 14.5, 600, C["llm"][0])
text(W - AX - 4, EY + 12, "re-planning loop runs right → left", 12, 400, SUB, "end", extra='font-style="italic"')

by = EY + 30; bh = 92
# U: decision maker (right)
box(1530, by, 240, bh, "llm")
module_title(1546, by + 24, "Decision maker", "llm")
text(1546, by + 46, "Natural-language request", 12.5, 400, SUB)
text(1546, by + 66, "“3 units per room,", 12.5, 400, INK, extra='font-style="italic"')
text(1546, by + 83, " no grid export”", 12.5, 400, INK, extra='font-style="italic"')
# L: local LLM
box(1110, by, 360, bh, "llm")
module_title(1126, by + 24, "Local LLM (on-premise)", "llm")
text(1126, by + 46, "Tool-calling under a strict JSON schema", 12.5, 400, SUB)
text(1126, by + 65, "Edits task fields only — never emits results", 12.5, 400, SUB)
text(1126, by + 84, "No data leaves the machine", 12.5, 400, SUB)
badge(1458, by + 4, "C5")
# E: proposed edits
box(690, by, 360, bh, "llm")
module_title(706, by + 24, "Proposed edits ΔΘ", "llm")
rich(706, by + 47, [("field: ", ""), ("from", "i"), (" → ", ""), ("to", "i"), ("   (validated against API ranges)", "")], 12.5, fill=SUB)
text(706, by + 66, "Unsupported items listed, not dropped", 12.5, 400, SUB)
text(706, by + 85, "Ambiguity → clarification question", 12.5, 400, SUB)
# K: confirmation
box(350, by, 280, bh, "llm")
module_title(366, by + 24, "User confirmation", "llm")
text(366, by + 46, "Accept / revise proposed edits", 12.5, 400, SUB)
rich(366, by + 66, [("→ structured task ", ""), ("Θ", "mi")], 12.5, fill=SUB)
text(366, by + 85, "(room, AC, PV, wind, tariff, quotes)", 12, 400, SUB)
mid = by + bh / 2
arrow([(1530, mid), (1472, mid)], C["llm"][0], 1.6, head="ahl")
arrow([(1110, mid), (1052, mid)], C["llm"][0], 1.6, head="ahl")
arrow([(690, mid), (632, mid)], C["llm"][0], 1.6, head="ahl")
# K -> inputs (left, then down)
arrow([(350, mid), (165, mid), (165, TOP - 2)], C["llm"][0], 1.6, head="ahl")
label_pill(240, mid - 12, "task Θ", C["llm"][0])
# outputs -> user (up)
arrow([(1650, TOP - 2), (1650, by + bh + 2)], C["llm"][0], 1.6, dash=True, head="ahl")
label_pill(1712, TOP - 18, "inspect / revise", C["llm"][0], size=11.5)

# ---------------------------------------------------------------- (a) inputs
header(AX, TOP, AW, "data", "(a)", "Multi-source inputs")
iy = TOP + 50; ih = 140; ig = 14
inputs = [
    ("Hourly weather", ["Reanalysis, 8,784 h (2024)", "Air temp., RH, pressure, irradiance, wind", "Interval semantics normalised"]),
    ("Building & HVAC", ["Room geometry, envelope, schedule", "AC catalog: rated capacity, COP", "N rooms × n units per room"]),
    ("Site & equipment", ["Roof area → PV capacity bound", "Certified small-wind power curve", "User quotes: PV, wind, storage"]),
    ("Policy & market", ["Official 4-period TOU tariff", "Critical peak: Jul–Sep, Tmax ≥ 35 °C", "Grid EF 0.4419 kgCO₂/kWh (GD)"]),
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
header(BX, TOP, BW, "phys", "(b)", "Physics-based hourly simulation")
# B1 room model
b1y, b1h = TOP + 50, 238
box(BX, b1y, BW, b1h, "phys")
module_title(BX + 16, b1y + 27, "Lumped RC heat–moisture room model", "phys", "1")
rich(BX + 24, b1y + 62, [("C", "mi"), (" dT", "m"), ("/", "m"), ("dt", "m"), (" = ", "m"), ("UA", "mi"), ("(", "m"), ("T", "mi"), ("out", "sub"), (" − ", "m"), ("T", "mi"), (")", "m"),
                         (" + ", "m"), ("Q", "mi"), ("sol", "sub"), (" + ", "m"), ("Q", "mi"), ("int", "sub"), (" + ", "m"), ("Q", "mi"), ("vent", "sub"), (" − ", "m"), ("Q", "mi"), ("AC", "sub")], 14)
rich(BX + 24, b1y + 92, [("m", "mi"), ("a", "sub"), (" dw", "m"), ("/", "m"), ("dt", "m"), (" = ", "m"), ("ṁ", "mi"), ("w", "sub"), ("(", "m"), ("w", "mi"), ("out", "sub"), (" − ", "m"), ("w", "mi"), (")", "m"), (" + ", "m"), ("G", "mi"), ("lat", "sub"), (" − ", "m"), ("Q", "mi"), ("lat", "sub"), ("/", "m"), ("h", "mi"), ("fg", "sub")], 14)
rich(BX + 24, b1y + 122, [("P", "mi"), ("AC", "sub"), ("(", "m"), ("t", "mi"), (")", "m"), (" = ", "m"), ("Q", "mi"), ("AC", "sub"), ("(", "m"), ("t", "mi"), (")", "m"), (" / COP(", "m"), ("T", "mi"), ("out", "sub"), (")", "m"),
                          ("     sensible + latent,  ", ""), ("Q", "mi"), ("AC", "sub"), (" ≤ ", "m"), ("n", "mi"), ("Q", "mi"), ("rated", "subr")], 14)
# adequacy gate sub-box
gy = b1y + 142
add(f'<rect x="{BX+16}" y="{gy}" width="{BW-32}" height="80" rx="8" fill="#FFFFFF" stroke="{C["phys"][0]}" stroke-width="1" stroke-dasharray="4 3"/>')
text(BX + 30, gy + 22, '<tspan font-weight="650" fill="#1D5FA8">Comfort-gated sizing</tspan>  ·  60-min pre-cooling (energy counted)', 12.8, 400, INK)
text(BX + 30, gy + 43, "Shortfall & unmet temperature/RH scored in occupied hours only", 12.5, 400, SUB)
rich(BX + 30, gy + 65, [("Unit sweep ", ""), ("n", "mi"), (" = 1…", "m"), ("n", "mi"), ("max", "subr"), ("  →  ", ""), ("n*", "mi"), (" = min{ ", "m"), ("n", "mi"), (" : shortfall = 0 }", "m"), ("   (min. adequate units)", "")], 12.8, fill=SUB)
badge(BX + BW - 10, b1y + 6, "C2")

# B2 generation
b2y, b2h = b1y + b1h + 18, 128
gx = BX + 46; gw2 = (BW - 46 - 14) / 2
for k, (title, l1, l2, l3) in enumerate([
        ("PV generation", "pvlib (PVWatts) · POA transposition", "Cell temperature from air temp. & wind", "Capacity bounded by roof area"),
        ("Wind generation", "Certified SD6 power curve", "Hub-height speed (Hellman law):", None)]):
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
module_title(BX + 16, b3y + 27, "Hourly energy matching", "phys", "4")
text(BX + 16 + 250, b3y + 27, "t = 1 … 8,784", 12.5, 400, SUB, extra='font-style="italic"')
rich(BX + 24, b3y + 60, [("s", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), (" = min{", "m"), ("G", "mi"), ("(", "m"), ("t", "mi"), ("), ", "m"), ("L", "mi"), ("(", "m"), ("t", "mi"), (")}", "m")], 14)
rich(BX + 24, b3y + 86, [("g", "mi"), ("imp", "subr"), (" = ", "m"), ("L", "mi"), (" − ", "m"), ("s", "mi")], 14)
rich(BX + 150, b3y + 86, [("e", "mi"), ("sur", "subr"), (" = ", "m"), ("G", "mi"), (" − ", "m"), ("s", "mi")], 14)
text(BX + 24, b3y + 112, "self-use · grid import · surplus", 12.3, 400, SUB)
add(f'<line x1="{BX+24}" y1="{b3y+126}" x2="{BX+262}" y2="{b3y+126}" stroke="{C["phys"][2]}" stroke-width="1"/>')
text(BX + 24, b3y + 146, "vs. conventional annual estimate", 12, 600, RED)
rich(BX + 24, b3y + 168, [("E", "mi"), ("gen", "subr"), (" × ", "m"), ("p̄", "mi"), ("  (ignores timing & TOU)", "")], 12.5, fill=SUB)
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
for i, (col, lab) in enumerate([("#2F9E6B", "self-use s"), ("#E8A33D", "surplus"), ("#9AA5B1", "import")]):
    add(f'<rect x="{lx + i*82}" y="{ly}" width="10" height="10" fill="{col}" fill-opacity="0.7"/>')
    text(lx + i * 82 + 14, ly + 9.5, lab, 10.5, 500, SUB)
text(X(12.6), Yv(0.97), "G(t)", 11, 600, "#C47A12", "start", MATH, True)
text(X(18.4), Yv(0.62), "L(t)", 11, 600, C["phys"][0], "start", MATH, True)
text(X(5.6), Yv(0.80), "pre-cool", 9.5, 500, C["phys"][0], "middle")

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
header(CX, TOP, CW, "dec", "(c)", "Decision analytics")
c_x = CX + 22; c_w = CW - 22
cy = TOP + 50
mods = []
def dmod(y, h, title, num):
    box(c_x, y, c_w, h, "dec")
    module_title(c_x + 14, y + 26, title, "dec", num)
    mods.append((y, h))

h1 = 92; dmod(cy, h1, "Scenario & capacity sweep", "5")
xx = c_x + 16
for s in ["S0 grid only", "S1 PV", "S2 wind", "S3 PV + wind"]:
    xx += chip(xx, cy + 40, s, "dec") + 8
rich(c_x + 16, cy + 82, [("PV capacity ", ""), ("k", "mi"), (" ∈ ", "m"), ("K", "mi"), (" (roof-bounded);  S0 kept as baseline", "")], 12.3, fill=SUB)

y2 = cy + h1 + 14; h2 = 128; dmod(y2, h2, "TOU-aware lifecycle economics", "6")
rich(c_x + 16, y2 + 58, [("TC", "mi"), (" = ", "m"), ("I", "mi"), ("0", "subr"), (" + Σ", "m"), ("y", "sub"), (" [ Σ", "m"), ("t", "sub"), (" ", "m"), ("p", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), ("g", "mi"), ("imp", "subr"), ("(", "m"), ("t", "mi"), (")", "m"), (" + ", "m"), ("M", "mi"), ("y", "sub"), (" + ", "m"), ("R", "mi"), ("y", "sub"), (" ] / (1+", "m"), ("r", "mi"), (")", "m"), ("y", "sup"), (" − ", "m"), ("V", "mi"), ("res", "subr")], 14)
text(c_x + 16, y2 + 86, "p(t): valley / flat / peak / critical-peak by hour, month and daily Tmax", 12.3, 400, SUB)
rich(c_x + 16, y2 + 108, [("Outputs: 10-yr total cost, ", ""), ("Δ", "m"), ("TC", "mi"), (" vs. S0 (sign kept), simple payback", "")], 12.3, fill=SUB)

y3 = y2 + h2 + 14; h3 = 92; dmod(y3, h3, "Carbon accounting", "7")
rich(c_x + 16, y3 + 56, [("Δ", "m"), ("CO", "mi"), ("2", "subr"), (" = Σ", "m"), ("t", "sub"), (" ", "m"), ("s", "mi"), ("(", "m"), ("t", "mi"), (")", "m"), (" · ", "m"), ("EF", "mi"), ("grid", "subr")], 14)
text(c_x + 16, y3 + 80, "Official provincial factor; carbon price shown as a scenario only", 12.3, 400, SUB)

y4 = y3 + h3 + 14; h4 = 96; dmod(y4, h4, "Surplus valorisation (add-on paths)", "8")
text(c_x + 16, y4 + 52, "Storage: rule-based dispatch, η = 0.90 → investment, payback", 12.3, 400, SUB)
text(c_x + 16, y4 + 74, "Grid export: rough revenue from the same surplus", 12.3, 400, SUB)
text(c_x + c_w - 14, y4 + 88, "not added to the main ranking", 11, 400, SUB, "end", extra='font-style="italic"')

y5 = y4 + h4 + 14; h5 = BOT - y5; dmod(y5, h5, "Constraint-aware status & recommendation", "9")
xx = c_x + 16
for s in ["feasible", "over budget", "quote unknown", "service gap"]:
    xx += chip(xx, y5 + 40, s, "dec") + 8
rich(c_x + 16, y5 + 84, [("Recommend ", ""), ("argmin", "m"), (" TC", "mi"), (" over comparable candidates;", "")], 12.3, fill=SUB)
text(c_x + 16, y5 + 104, "unknown ≠ excluded; service gap never shown as adequate", 12.3, 400, SUB)
badge(c_x + c_w - 10, y5 + 6, "C4")
badge(c_x + c_w - 10, y2 + 6, "C3")

# decision bus at x = CX + 6
dbx = CX + 6
add(f'<path d="M{dbx},{cy+h1/2} L{dbx},{y5+h5/2}" stroke="{C["dec"][0]}" stroke-width="1.6" fill="none"/>')
for (yy, hh) in mods:
    arrow([(dbx, yy + hh / 2), (c_x - 2, yy + hh / 2)], C["dec"][0], 1.5, head="ahd")
# B3 -> bus
arrow([(BX + BW, b3y + 70), (dbx, b3y + 70)], C["phys"][0], 1.8, head="ahp")
label_pill((BX + BW + dbx) / 2 + 2, b3y + 56, "hourly flows", C["phys"][0], size=10.5)
# policy & market -> bus (route under panels)
py = BOT + 18
add(f'<path d="M{AX+AW/2},{ys[3]+ih} L{AX+AW/2},{py} L{dbx},{py} L{dbx},{y5+h5/2}" stroke="{C["data"][0]}" stroke-width="1.5" fill="none" stroke-dasharray="6 4" marker-end="url(#ah)"/>')
label_pill((BX + BX + BW) / 2, py, "tariff p(t), emission factor, quotes", C["data"][0], size=11)

# ---------------------------------------------------------------- (d) decision interface
header(DX, TOP, DW, "ui", "(d)", "Decision interface")
dx = DX; dy = TOP + 50
box(dx, dy, DW, 140, "ui")
module_title(dx + 14, dy + 26, "Progressive computing", "ui")
text(dx + 16, dy + 52, "Typical-week preview", 12.3, 600, INK)
text(dx + 16, dy + 70, "physics only, < 1 s", 12.3, 400, SUB)
text(dx + 16, dy + 96, "Full-year async job", 12.3, 600, INK)
text(dx + 16, dy + 114, "real backend progress", 12.3, 400, SUB)
badge(dx + DW - 10, dy + 6, "C6")
# visual outputs
oy = dy + 154; oh = 300
box(dx, oy, DW, oh, "ui")
module_title(dx + 14, oy + 26, "Visual evidence", "ui")
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
text(dx + 16, hy + 12 * (ch_ + 1.2) + 14, "Energy calendar (month × hour)", 11.5, 500, SUB)
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
text(dx + 16, ay1 + 16, "Capacity–cost curve (best marked)", 11.5, 500, SUB)
text(dx + 16, ay1 + 40, "10-yr ledger · carbon · storage", 11.5, 500, SUB)
text(dx + 16, ay1 + 56, "Hourly CSV / JSON / printable brief", 11.5, 500, SUB)
# saved plans
sy = oy + oh + 14; sh = BOT - sy
box(dx, sy, DW, sh, "ui")
module_title(dx + 14, sy + 26, "Accountable output", "ui")
text(dx + 16, sy + 52, "Every number from computation", 12.3, 400, SUB)
text(dx + 16, sy + 72, "Edits invalidate stale results", 12.3, 400, SUB)
text(dx + 16, sy + 92, "Saved plans side-by-side", 12.3, 400, SUB)
text(dx + 16, sy + 112, "Sources & hashes traceable", 12.3, 400, SUB)
# C -> D
arrow([(CX + CW, TOP + 330), (DX - 2, TOP + 330)], C["dec"][0], 1.8, head="ahd")
label_pill((CX + CW + DX) / 2, TOP + 312, "results", C["dec"][0], size=10.5)

# ---------------------------------------------------------------- innovations strip
iy0 = 912
add(f'<line x1="{AX}" y1="{iy0-8}" x2="{W-AX}" y2="{iy0-8}" stroke="{C["data"][2]}" stroke-width="1"/>')
text(AX, iy0 + 14, "Key contributions", 14.5, 700, INK)
inn = [
    ("C1", "Hourly coupling", "Load, PV and wind matched hour-by-hour under TOU prices, instead of annual energy × average price."),
    ("C2", "Comfort-gated sizing", "AC load and unit count derived from heat–moisture physics with an explicit adequacy rule."),
    ("C3", "Policy-faithful economics", "Official tariff incl. temperature-triggered critical peak, lifecycle costs and provincial carbon factor."),
    ("C4", "Honest decision semantics", "Unknown ≠ excluded; service gaps flagged; grid-only baseline always kept for comparison."),
    ("C5", "LLM as interface, not calculator", "On-premise LLM turns language into validated task edits; deterministic tools compute every number."),
    ("C6", "Progressive computing", "Sub-second typical-week preview, then a full-year job with real progress for interactive use."),
]
colw = (W - 2 * AX - 150) / 3
for i, (b, t, d) in enumerate(inn):
    col, row = i % 3, i // 3
    x = AX + 150 + col * colw; y = iy0 + row * 76
    badge(x + 13, y + 9, b)
    text(x + 34, y + 14, esc(t), 13.5, 650, INK)
    # wrap description into two lines
    words = d.split(); lines = [""]
    for w_ in words:
        if len(lines[-1]) + len(w_) + 1 > 62: lines.append(w_)
        else: lines[-1] = (lines[-1] + " " + w_).strip()
    for j, l in enumerate(lines[:2]):
        text(x + 34, y + 34 + j * 17, esc(l), 12, 400, SUB)

add("</svg>")
open("framework.svg", "w", encoding="utf-8").write("\n".join(o for o in out if o))
print("ok")
