"""
CivicCare — Analytics Performance Report  ·  Premium Edition
═══════════════════════════════════════════════════════════════
Design:
  · Magazine-report aesthetic — wide charts, generous whitespace, bold hierarchy
  · _ph() for rich HTML paragraphs (bold/italic preserved); _p() for plain text
  · Insight callout boxes: teal-left-border card with a bold pull-quote
  · Chapter openers: full-bleed two-tone band — chapter number ghost + title
  · KPI tiles: white cards with coloured top-rule and large numerals
  · Charts rendered at full content-width, tall aspect ratios
  · Smart KeepTogether / CondPageBreak guards throughout
  · Running chapter name in header; branded footer with page number
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle, PageBreak,
    HRFlowable, KeepTogether, CondPageBreak, Flowable,
)

# ───────────────────────────────────────────────────────
#  PALETTE
# ───────────────────────────────────────────────────────
HEX = dict(
    teal      = "#008080",
    teal_dk   = "#005F5F",
    teal_md   = "#00A0A0",
    teal_lt   = "#E0F5F5",
    teal_pale = "#F0FAFA",
    ink       = "#1A1A2E",          # near-navy for headings
    body      = "#2C2C3E",          # soft dark for body text
    muted     = "#6B7280",
    rule      = "#CBD5E1",
    card      = "#FFFFFF",
    page      = "#FAFBFC",
    success   = "#059669",
    warning   = "#D97706",
    danger    = "#DC2626",
    info      = "#2563EB",
    amber     = "#F59E0B",
    row_alt   = "#F0F9F9",
    grid      = "#E2F2F2",
    insight_bg= "#F0F9FF",
    insight_bd= "#0EA5E9",
)

def rl(k): return colors.HexColor(HEX[k])

RL_TEAL     = rl("teal")
RL_TEAL_DK  = rl("teal_dk")
RL_TEAL_LT  = rl("teal_lt")
RL_INK      = rl("ink")
RL_BODY     = rl("body")
RL_MUTED    = rl("muted")
RL_RULE     = rl("rule")
RL_CARD     = rl("card")
RL_ROW_ALT  = rl("row_alt")
RL_GRID     = rl("grid")
RL_SUCCESS  = rl("success")
RL_WARNING  = rl("warning")
RL_DANGER   = rl("danger")
RL_INFO     = rl("info")

BRAND     = "CivicCare"
TAGLINE   = "Civic intelligence for responsive governance"
NEUTRAL   = HEX["muted"]

# ───────────────────────────────────────────────────────
#  PAGE GEOMETRY
# ───────────────────────────────────────────────────────
PAGE   = A4
PW, PH = PAGE
ML, MR = 1.8*cm, 1.4*cm
MT, MB = 1.0*cm, 1.55*cm
CW     = PW - ML - MR          # ≈ 460 pt  content width

_CURRENT_CHAPTER: list[str] = [""]

# ───────────────────────────────────────────────────────
#  TYPE SCALE
# ───────────────────────────────────────────────────────
FS = dict(hero=34, h1=22, h2=15, h3=11.5, h4=9, body=9.5,
          small=8.5, tiny=7.5, caption=8, kpi_val=20, kpi_lbl=7.5)

# ───────────────────────────────────────────────────────
#  TEXT HELPERS
# ───────────────────────────────────────────────────────
def _esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _p(text, style):
    """Plain text paragraph — all tags escaped."""
    return Paragraph(_esc(text), style)

def _ph(html, style):
    """Rich HTML paragraph — <b>, <i>, <br/> pass through unchanged."""
    return Paragraph(str(html) if html is not None else "–", style)

def _pc(val, style):
    """Cell value — escapes special chars, allows <br/>."""
    s = str(val) if val is not None else "–"
    s = s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>")
    return Paragraph(s, style)

def _fmt_phone(v):
    if v is None: return "–"
    if isinstance(v, list): return ", ".join(str(x) for x in v) if v else "–"
    return str(v)

def _hex_rl(h):
    if not h: return colors.HexColor(NEUTRAL)
    h = str(h).strip()
    if not h.startswith("#"): h = "#" + h
    try: return colors.HexColor(h)
    except: return colors.HexColor(NEUTRAL)

def _fit(widths, max_pt=CW):
    s = sum(widths)
    if s <= max_pt * 0.998: return widths
    f = max_pt * 0.998 / s
    return [w*f for w in widths]

def _img(png, max_w, max_h=0):
    bio = io.BytesIO(png)
    pil = PILImage.open(bio)
    wp, hp = pil.size
    asp = hp/wp if wp else 1.0
    w, h = max_w, max_w*asp
    if max_h > 0 and h > max_h: w, h = max_h/asp, max_h
    bio.seek(0)
    return RLImage(bio, width=w, height=h)

def _sp(h=0.28): return Spacer(1, h*cm)
def _hr(t=0.7, c=None): return HRFlowable(width="100%", thickness=t,
    color=c or RL_RULE, spaceBefore=2, spaceAfter=4)


# ───────────────────────────────────────────────────────
#  CHART ENGINE
# ───────────────────────────────────────────────────────
DPI   = 165
FIG_W = 11.0        # wider figures

C = HEX             # shorthand

def _ax_clean(ax):
    ax.set_facecolor(C["card"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for sp in ["left","bottom"]:
        ax.spines[sp].set_color(C["rule"]); ax.spines[sp].set_linewidth(0.6)
    ax.tick_params(colors=C["muted"], labelsize=8.5, length=3, width=0.5)

def _fig(h=4.8):
    fig, ax = plt.subplots(figsize=(FIG_W, h), dpi=DPI, layout="constrained")
    fig.patch.set_facecolor(C["card"]); _ax_clean(ax); return fig, ax

def _fig2(h=4.8):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIG_W, h), dpi=DPI, layout="constrained")
    fig.patch.set_facecolor(C["card"]); _ax_clean(a1); _ax_clean(a2); return fig, a1, a2

def _title(ax, t):
    ax.set_title(t, fontsize=11, fontweight="bold", color=C["ink"], pad=11, loc="left")

def _gh(ax):
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=C["grid"], linewidth=0.85); ax.xaxis.grid(False)

def _gv(ax):
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=C["grid"], linewidth=0.85); ax.yaxis.grid(False)

def _legend(ax, **kw):
    leg = ax.legend(fontsize=8.5, frameon=True, framealpha=0.96,
                    edgecolor=C["rule"], facecolor=C["card"],
                    handlelength=1.0, handletextpad=0.5, **kw)
    for t in leg.get_texts(): t.set_color(C["muted"])

def _lbl_h(ax, bars, vals, fmt="{:.0f}"):
    xlim = ax.get_xlim()[1]; off = max(xlim*0.012, 0.5)
    for b, v in zip(bars, vals):
        if v > 0:
            ax.text(v+off, b.get_y()+b.get_height()/2, fmt.format(v),
                    va="center", ha="left", fontsize=8, color=C["body"], fontweight="600")

def _lbl_v(ax, bars, vals, suffix=""):
    ylim = ax.get_ylim()[1]
    for b, v in zip(bars, vals):
        if v > 0:
            ax.text(b.get_x()+b.get_width()/2, v+ylim*0.008,
                    f"{v:.0f}{suffix}", ha="center", va="bottom",
                    fontsize=7.5, color=C["muted"])

def _topng(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight",
                pad_inches=0.20, facecolor=fig.get_facecolor())
    plt.close(fig); buf.seek(0); return buf.read()

def _render_eq(latex_lines: list[str], fontsize: int = 13) -> bytes:
    """Render a list of LaTeX math strings as a single PNG using matplotlib mathtext."""
    fig, ax = plt.subplots(figsize=(FIG_W * 0.82, 0.62 * len(latex_lines)),
                           dpi=DPI, layout="constrained")
    fig.patch.set_facecolor(C["card"]); ax.set_facecolor(C["card"])
    ax.axis("off")
    for sp in ax.spines.values(): sp.set_visible(False)
    y_step = 1.0 / (len(latex_lines) + 1)
    for i, line in enumerate(latex_lines):
        ax.text(0.06, 1.0 - (i + 1) * y_step, line,
                transform=ax.transAxes, fontsize=fontsize,
                color=C["ink"], va="center", ha="left",
                fontfamily="DejaVu Serif")
    return _topng(fig)


def _eq_block(latex_lines: list[str], styles) -> KeepTogether:
    """Return a KeepTogether block with the rendered equation image."""
    png = _render_eq(latex_lines)
    rl_img = _img(png, CW * 0.82)
    return KeepTogether([_sp(0.06), rl_img, _sp(0.10)])


def _tgrad(n, hi=1.0, lo=0.35):
    return [(0, 0x80/255, 0x80/255, a) for a in np.linspace(hi, lo, max(n,1))]

# ── Charts ──────────────────────────────────────────────

def chart_dept_dpi(rows):
    if not rows: return None
    names = [d.get("name","?")[:26] for d in rows]
    vals  = [float(d.get("scores",{}).get("dpi") or 0) for d in rows]
    idx   = np.argsort(vals)[::-1]
    names = [names[i] for i in idx]; vals = [vals[i] for i in idx]
    h     = max(4.5, len(names)*0.52+1.6)
    fig, ax = _fig(h)
    bars = ax.barh(names, vals, color=_tgrad(len(names)),
                   height=0.62, edgecolor=C["card"], linewidth=0.4)
    ax.axvspan(70, 110, alpha=0.06, color=C["teal"], zorder=0)
    ax.axvline(70, color=C["teal_dk"], lw=1.4, ls=(0,(5,3)),
               alpha=0.8, label="Baseline 70", zorder=3)
    ax.set_xlim(0, 110); _gv(ax); _lbl_h(ax, bars, vals, fmt="{:.1f}")
    ax.invert_yaxis()
    ax.set_xlabel("DPI Score", fontsize=9.5, color=C["muted"], labelpad=6)
    _title(ax, "Department Performance Index (DPI)"); _legend(ax, loc="lower right")
    return _topng(fig)

def chart_dept_resolution(rows):
    if not rows: return None
    names = [d.get("name","?")[:20] for d in rows]
    res   = [float((d.get("scores",{}).get("resolution_rate") or 0)*100) for d in rows]
    sla   = [float((d.get("scores",{}).get("sla_rate")        or 0)*100) for d in rows]
    x, w  = np.arange(len(names)), 0.36
    fig, ax = _fig(5.2)
    b1 = ax.bar(x-w/2, res, w, label="Resolution %", color=C["teal_dk"], edgecolor=C["card"], lw=0.4)
    b2 = ax.bar(x+w/2, sla, w, label="SLA %",        color=C["teal_md"], edgecolor=C["card"], lw=0.4)
    ax.axhline(100, color=C["rule"], lw=0.8, ls="--", alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=32, ha="right", fontsize=8.5)
    ax.set_ylim(0, 120); ax.set_ylabel("Rate (%)", fontsize=9.5, color=C["muted"], labelpad=6)
    _gh(ax); _lbl_v(ax, b1, res, suffix="%"); _lbl_v(ax, b2, sla, suffix="%")
    _title(ax, "Resolution % vs SLA % by Department"); _legend(ax, loc="upper right")
    return _topng(fig)

def chart_dept_volume(rows):
    if not rows: return None
    names = [d.get("name","?")[:26] for d in rows]
    res   = [int(d.get("metrics",{}).get("resolved",  0)) for d in rows]
    pend  = [int(d.get("metrics",{}).get("pending",   0)) for d in rows]
    esc   = [int(d.get("metrics",{}).get("escalated", 0)) for d in rows]
    tot   = [r+p+e for r,p,e in zip(res,pend,esc)]
    idx   = np.argsort(tot)[::-1]
    names = [names[i] for i in idx]; res=[res[i] for i in idx]
    pend  = [pend[i]  for i in idx]; esc=[esc[i]  for i in idx]
    h     = max(4.5, len(names)*0.52+1.6)
    fig, ax = _fig(h); y, bh = np.arange(len(names)), 0.58
    ax.barh(y, res,  bh, label="Resolved",  color=C["teal"],   edgecolor=C["card"], lw=0.4)
    ax.barh(y, pend, bh, label="Pending",   color=C["warning"],edgecolor=C["card"], lw=0.4, left=res)
    ax.barh(y, esc,  bh, label="Escalated", color=C["danger"], edgecolor=C["card"], lw=0.4,
            left=[r+p for r,p in zip(res,pend)])
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=8.5); ax.invert_yaxis()
    ax.set_xlabel("Grievance Count", fontsize=9.5, color=C["muted"], labelpad=6)
    _gv(ax); _title(ax, "Grievance Volume by Department"); _legend(ax, loc="lower right")
    return _topng(fig)

def chart_worker_sla(rows):
    if not rows: return None
    # Limit to top 30 to prevent PDF layout overflow
    rows  = sorted(rows, key=lambda w: float((w.get("metrics",{}).get("sla_rate") or 0)), reverse=True)[:30]
    names = [w.get("name","?")[:24] for w in rows]
    slas  = [float((w.get("metrics",{}).get("sla_rate") or 0)*100) for w in rows]
    atts  = [float((w.get("metrics",{}).get("attendance_rate") or 0)*100) for w in rows]
    h     = max(4.5, len(names)*0.56+1.6)
    fig, ax = _fig(h); x, bw = np.arange(len(names)), 0.36
    b1 = ax.barh(x+bw/2, slas, bw, label="SLA %",        color=C["teal_dk"], edgecolor=C["card"], lw=0.4)
    b2 = ax.barh(x-bw/2, atts, bw, label="Attendance %", color=C["teal_md"], edgecolor=C["card"], lw=0.4)
    ax.set_yticks(x); ax.set_yticklabels(names, fontsize=8.5); ax.set_xlim(0, 120)
    ax.axvline(80, color=C["warning"], lw=1.3, ls=(0,(4,3)), alpha=0.8, label="80% target", zorder=3)
    ax.invert_yaxis(); _gv(ax); _lbl_h(ax,b1,slas); _lbl_h(ax,b2,atts)
    ax.set_xlabel("Rate (%)", fontsize=9.5, color=C["muted"], labelpad=6)
    _title(ax, "Worker SLA % and Attendance %"); _legend(ax, loc="lower right")
    return _topng(fig)

def chart_worker_resolved(rows):
    if not rows: return None
    # Limit to top 30 to prevent PDF layout overflow
    rows  = sorted(rows, key=lambda w: int(w.get("metrics",{}).get("period_resolved",0)), reverse=True)[:30]
    names = [w.get("name","?")[:24] for w in rows]
    vals  = [int(w.get("metrics",{}).get("period_resolved",0)) for w in rows]
    h     = max(4.5, len(names)*0.52+1.6)
    fig, ax = _fig(h)
    bars = ax.barh(names, vals, color=_tgrad(len(names)),
                   height=0.62, edgecolor=C["card"], lw=0.4)
    _gv(ax); _lbl_h(ax,bars,vals); ax.invert_yaxis()
    ax.set_xlabel("Cases Resolved", fontsize=9.5, color=C["muted"], labelpad=6)
    _title(ax, "Cases Resolved by Field Officer")
    return _topng(fig)

def chart_ward_wpi(rows):
    wpis = [float(r.get("scores",{}).get("wpi") or 0) for r in rows if r.get("scores")]
    if not wpis: return None
    sv = sorted(wpis, reverse=True); n = len(sv)
    alphas = np.linspace(0.95, 0.22, n)
    clrs   = [(0, 0x80/255, 0x80/255, a) for a in alphas]
    fig, ax = _fig(4.8)
    ax.bar(range(n), sv, color=clrs, edgecolor="white", linewidth=0.1, width=1.0)
    top = max(sv)+10 if sv else 105
    ax.axhspan(70, max(top,105), alpha=0.05, color=C["teal"], zorder=0)
    ax.axhline(70, color=C["teal_dk"], lw=1.4, ls=(0,(5,3)), alpha=0.8, label="Baseline 70", zorder=3)
    ax.set_xlim(-0.5, n-0.5); ax.set_ylim(0, max(top,105))
    ax.set_xlabel("Wards sorted by WPI (highest → lowest)", fontsize=9.5, color=C["muted"], labelpad=6)
    ax.set_ylabel("WPI Score", fontsize=9.5, color=C["muted"], labelpad=6); _gh(ax)
    _title(ax, "Ward Performance Index (WPI) Distribution")
    n_hi  = sum(1 for v in sv if v>=70)
    n_mid = sum(1 for v in sv if 50<=v<70)
    n_lo  = sum(1 for v in sv if v<50)
    patches = [
        mpatches.Patch(facecolor=C["teal_dk"],  alpha=0.95, label=f"≥ 70   ({n_hi} wards)"),
        mpatches.Patch(facecolor=C["teal"],      alpha=0.55, label=f"50–69  ({n_mid} wards)"),
        mpatches.Patch(facecolor=C["teal_md"],   alpha=0.32, label=f"< 50   ({n_lo} wards)"),
    ]
    ax.legend(handles=patches, fontsize=8.5, frameon=True, framealpha=0.96,
              edgecolor=C["rule"], facecolor=C["card"], loc="upper right")
    return _topng(fig)

def chart_ward_backlog(rows):
    if not rows: return None
    top   = sorted(rows, key=lambda r: int(r.get("metrics",{}).get("pending",0)), reverse=True)[:20]
    names = [r.get("name","?")[:24] for r in top]
    res   = [int(r.get("metrics",{}).get("resolved",0)) for r in top]
    pend  = [int(r.get("metrics",{}).get("pending", 0)) for r in top]
    h     = max(5.0, len(names)*0.50+1.8)
    fig, ax = _fig(h); y, bh = np.arange(len(names)), 0.56
    ax.barh(y,  res,              bh, label="Resolved", color=C["teal"],   edgecolor=C["card"], lw=0.4)
    ax.barh(y, [-p for p in pend],bh, label="Pending",  color=C["warning"],edgecolor=C["card"], lw=0.4)
    ax.axvline(0, color=C["rule"], lw=0.9)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=8.5); ax.invert_yaxis()
    mx = max(max(res,default=0),max(pend,default=0),1)
    ax.set_xlim(-mx*1.25, mx*1.25)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: str(abs(int(v)))))
    ax.set_xlabel("← Pending  |  Resolved →", fontsize=9.5, color=C["muted"], labelpad=6)
    _gv(ax); _title(ax, "Top 20 Wards — Resolved vs Pending (Backlog View)")
    _legend(ax, loc="lower right")
    return _topng(fig)

def chart_zone_zpi(rows):
    if not rows: return None
    rows  = sorted(rows, key=lambda r: float(r.get("scores",{}).get("zpi") or 0), reverse=True)
    names = [r.get("name","?")[:22] for r in rows]
    zpis  = [float(r.get("scores",{}).get("zpi") or 0) for r in rows]
    n     = len(names)
    sc    = _tgrad(n, hi=0.52, lo=0.18)
    dc    = _tgrad(n, hi=1.00, lo=0.52)
    fig, ax = _fig(5.0); x = np.arange(n)
    for xi,v,s,d in zip(x,zpis,sc,dc):
        ax.vlines(xi,0,v, color=s, linewidth=5.5, zorder=2)
        ax.scatter([xi],[v], color=[d], s=110, zorder=4, edgecolors=C["card"], linewidths=1.4)
    top = max(zpis) if zpis else 85
    ax.axhspan(70, top+18, alpha=0.05, color=C["teal"], zorder=0)
    ax.axhline(70, color=C["teal_dk"], lw=1.4, ls=(0,(5,3)), alpha=0.78, label="Baseline 70", zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=28, ha="right", fontsize=9)
    ax.set_ylim(0, top+18)
    for xi,v in zip(x,zpis):
        ax.text(xi, v+1.6, f"{v:.1f}", ha="center", va="bottom",
                fontsize=8.5, color=C["ink"], fontweight="700")
    ax.set_ylabel("ZPI Score", fontsize=9.5, color=C["muted"], labelpad=6)
    _gh(ax); _title(ax, "Zone Performance Index (ZPI)"); _legend(ax, loc="upper right")
    return _topng(fig)

def chart_escalation(escalation):
    bz = escalation.get("by_zone")       or []
    bd = escalation.get("by_department") or []
    if not bz and not bd: return None
    fig, a1, a2 = _fig2(h=5.0)
    def _panel(ax, rows, subtitle):
        if not rows: ax.set_visible(False); return
        names  = [r.get("name","?")[:26] for r in rows]
        counts = [int(r.get("count",0))  for r in rows]
        mx     = max(counts) if counts else 1
        alphas = [0.34+0.66*(c/mx) for c in counts]
        clrs   = [(0, 0x80/255, 0x80/255, a) for a in alphas]
        y      = np.arange(len(names))
        bars   = ax.barh(y, counts, color=clrs, edgecolor=C["card"], linewidth=0.4, height=0.62)
        mi     = counts.index(mx)
        ax.scatter([mx],[mi], color=C["danger"], s=70, zorder=5, edgecolors=C["card"], linewidths=1.2)
        for b,v in zip(bars,counts):
            ax.text(v+mx*0.032, b.get_y()+b.get_height()/2, str(v),
                    va="center", ha="left", fontsize=8.5, color=C["body"], fontweight="600")
        ax.set_yticks(y); ax.set_yticklabels(names, fontsize=8.5); ax.invert_yaxis()
        ax.set_xlim(0, mx*1.32)
        ax.set_xlabel("Escalated Cases", fontsize=9, color=C["muted"], labelpad=5)
        ax.set_title(subtitle, fontsize=10.5, fontweight="bold", color=C["ink"], pad=9, loc="left")
        _gv(ax)
    _panel(a1, bz, "By Zone"); _panel(a2, bd, "By Department")
    fig.suptitle("Escalation Concentration", fontsize=12, fontweight="bold",
                 color=C["ink"], x=0.02, ha="left", y=1.02)
    return _topng(fig)

def chart_party_donut(pc):
    parties  = pc.get("parties") or []
    names    = [p.get("short_code") or p.get("name") or "?" for p in parties]
    counts   = [int(p.get("ward_count") or 0) for p in parties]
    rclrs    = [str(p.get("color") or NEUTRAL) for p in parties]
    if not any(counts): return None
    def _s(h): h=h.strip(); return h if h.startswith("#") else "#"+h
    pie_clrs = [_s(c) for c in rclrs]
    fig, ax = plt.subplots(figsize=(8.0, 5.5), dpi=DPI)
    fig.patch.set_facecolor(C["card"]); ax.set_facecolor(C["card"])
    wedges,_,at = ax.pie(counts, labels=None, autopct="%1.1f%%", colors=pie_clrs,
        startangle=130, pctdistance=0.72,
        wedgeprops=dict(edgecolor="white", linewidth=2.2, width=0.68))
    for a in at: a.set_fontsize(8.5); a.set_color("white"); a.set_fontweight("bold")
    ax.legend(wedges, [f"{n}  ({c} wards)" for n,c in zip(names,counts)],
              loc="center left", bbox_to_anchor=(1.0,0.5), fontsize=9,
              frameon=True, framealpha=0.96, edgecolor=C["rule"], facecolor=C["card"])
    ax.set_title("Ward Share by Political Party", fontsize=11, fontweight="bold",
                 color=C["ink"], pad=12, loc="left")
    return _topng(fig)

def chart_party_wpi(pc):
    parties  = pc.get("parties") or []
    names    = [p.get("short_code") or "?" for p in parties]
    wpis     = [float(p.get("avg_wpi") or 0) for p in parties]
    rclrs    = [str(p.get("color") or NEUTRAL) for p in parties]
    if not any(wpis): return None
    def _s(h): h=h.strip(); return h if h.startswith("#") else "#"+h
    idx = np.argsort(wpis)[::-1]
    names=[names[i] for i in idx]; wpis=[wpis[i] for i in idx]; clrs=[_s(rclrs[i]) for i in idx]
    fig, ax = _fig(5.0); x = np.arange(len(names))
    bars = ax.bar(x, wpis, color=clrs, edgecolor=C["card"], linewidth=0.8, width=0.58)
    top = max(wpis) if wpis else 85
    ax.axhspan(70, top+20, alpha=0.04, color=C["teal"], zorder=0)
    ax.axhline(70, color=C["teal_dk"], lw=1.4, ls=(0,(5,3)), alpha=0.78, label="Baseline 70", zorder=3)
    ax.set_ylim(0, top+20); ax.set_xticks(x); ax.set_xticklabels(names, fontsize=10)
    for b,v in zip(bars,wpis):
        ax.text(b.get_x()+b.get_width()/2, v+top*0.014, f"{v:.1f}",
                ha="center", va="bottom", fontsize=9, color=C["ink"], fontweight="700")
    ax.set_ylabel("Avg WPI", fontsize=9.5, color=C["muted"], labelpad=6)
    _gh(ax); _title(ax, "Average Ward WPI by Political Party"); _legend(ax, loc="upper right")
    return _topng(fig)

def chart_summary_donut(rr, sr):
    fig, (a1,a2) = plt.subplots(1,2, figsize=(8.0,4.2), dpi=DPI,
                                 gridspec_kw={"wspace":0.12})
    fig.patch.set_facecolor(C["card"])
    def _d(ax, pct, label, fill, track):
        ax.set_facecolor(C["card"])
        for sp in ax.spines.values(): sp.set_visible(False)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        rem = max(0.0, 100-pct)
        ax.pie([pct, rem], colors=[fill, track], startangle=90, counterclock=False,
               wedgeprops=dict(width=0.46, edgecolor=C["card"], linewidth=3.0))
        ax.text(0,  0.12, f"{pct:.1f}%", ha="center", va="center",
                fontsize=22, fontweight="bold", color=C["ink"])
        ax.text(0, -0.26, label, ha="center", va="center",
                fontsize=10, color=C["muted"], fontweight="500")
    _d(a1, min(rr,100), "Resolution Rate", C["teal"],  C["teal_lt"])
    _d(a2, min(sr,100), "SLA Compliance",  C["info"],  "#DDEEFF")
    fig.suptitle("System-wide Performance Overview", fontsize=12, fontweight="bold",
                 color=C["ink"], x=0.04, ha="left", y=1.02)
    return _topng(fig)


# ───────────────────────────────────────────────────────
#  CUSTOM FLOWABLES
# ───────────────────────────────────────────────────────

class ChapterBand(Flowable):
    """Full-width two-tone chapter opener band."""
    H = 2.2*cm
    def __init__(self, num, title, subtitle=""):
        super().__init__(); self.num=num; self.title=title; self.subtitle=subtitle
        self.width=CW; self.height=self.H+(0.55*cm if subtitle else 0)
    def draw(self):
        c=self.canv; w=self.width; h=self.H
        # Dark teal base
        c.setFillColor(RL_TEAL_DK)
        c.roundRect(0,0,w,h,4,fill=1,stroke=0)
        # Lighter right-side accent slab
        c.setFillColor(RL_TEAL)
        c.roundRect(w*0.66,0,w*0.34,h,4,fill=1,stroke=0)
        # Ghost number
        c.setFillColor(colors.Color(0,0,0,0.15))
        c.setFont("Helvetica-Bold",60)
        c.drawRightString(w-0.5*cm, 0.05*cm, str(self.num))
        # Chapter label
        c.setFillColor(colors.HexColor("#80CCCC"))
        c.setFont("Helvetica",8.5)
        c.drawString(0.55*cm, h-0.55*cm, f"CHAPTER {self.num:02d}")
        # Title
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold",17)
        c.drawString(0.55*cm, 0.52*cm, self.title.upper())
        if self.subtitle:
            c.setFillColor(colors.HexColor("#B0E0E0"))
            c.setFont("Helvetica-Oblique",8.5)
            c.drawString(0.0, -0.40*cm, self.subtitle)


class InsightBox(Flowable):
    """Left-accented callout card for headline insights."""
    PAD = 10
    def __init__(self, label, text, label_style, text_style, accent=None):
        super().__init__()
        self._label = label; self._text  = text
        self._ls = label_style; self._ts = text_style
        self._accent = colors.HexColor(accent or HEX["teal"])
        self.width = CW
        # Estimate height from text length
        chars_per_line = int((CW - 1.2*cm) / 5.5)
        lines = max(2, len(text) // chars_per_line + 1)
        self.height = lines * 14 + self.PAD * 3 + 18

    def draw(self):
        c=self.canv; w=self.width; h=self.height; p=self.PAD
        # Card background
        c.setFillColor(colors.HexColor(HEX["teal_pale"]))
        c.setStrokeColor(rl("rule"))
        c.setLineWidth(0.5)
        c.roundRect(0,0,w,h,4,fill=1,stroke=1)
        # Left accent bar
        c.setFillColor(self._accent)
        c.roundRect(0,0,0.30*cm,h,3,fill=1,stroke=0)
        # Label
        c.setFillColor(self._accent)
        c.setFont("Helvetica-Bold",8.5)
        c.drawString(0.50*cm, h-p-10, self._label.upper())
        # Text (draw as para)
        from reportlab.platypus import Paragraph
        para = Paragraph(self._text, self._ts)
        avail_w = w - 0.60*cm - p
        pw, ph = para.wrap(avail_w, h)
        para.drawOn(c, 0.50*cm, h - p - 14 - ph)


# ───────────────────────────────────────────────────────
#  TABLE FACTORY
# ───────────────────────────────────────────────────────

def _tbl(data, cw, *, hfs=8.5, bfs=8.0, mixed=False, extra=None):
    cw = _fit(cw)
    t  = Table(data, repeatRows=1, colWidths=cw)
    base = [
        ("BACKGROUND",    (0,0),(-1,0),  RL_TEAL_DK),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),  hfs),
        ("TOPPADDING",    (0,0),(-1,0),  6),
        ("BOTTOMPADDING", (0,0),(-1,0),  6),
        ("ALIGN",         (0,0),(-1,0),  "LEFT"),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [RL_CARD, RL_ROW_ALT]),
        ("GRID",          (0,0),(-1,-1), 0.28, RL_GRID),
        ("BOX",           (0,0),(-1,-1), 0.70, RL_TEAL),
        ("LINEBELOW",     (0,0),(-1,0),  1.8,  RL_TEAL),
        ("VALIGN",        (0,0),(-1,0),  "MIDDLE"),
        ("VALIGN",        (0,1),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("RIGHTPADDING",  (0,0),(-1,-1), 5),
        ("TOPPADDING",    (0,1),(-1,-1), 4),
        ("BOTTOMPADDING", (0,1),(-1,-1), 4),
    ]
    if not mixed: base.append(("FONTSIZE",(0,1),(-1,-1),bfs))
    if extra: base.extend(extra)
    t.setStyle(TableStyle(base)); return t

def _meth_tbl(items, small):
    c1, c2 = CW*0.26, CW*0.74
    rows = [[_pc(f"• {lab}", small), _pc(desc, small)] for lab, desc in items]
    t = Table(rows, colWidths=_fit([c1,c2]))
    t.setStyle(TableStyle([
        ("FONTNAME",       (0,0),(0,-1),"Helvetica-Bold"),
        ("TEXTCOLOR",      (0,0),(0,-1),RL_TEAL_DK),
        ("FONTNAME",       (1,0),(1,-1),"Helvetica"),
        ("FONTSIZE",       (0,0),(-1,-1),8.5),
        ("ROWBACKGROUNDS", (0,0),(-1,-1),[RL_CARD, RL_ROW_ALT]),
        ("GRID",           (0,0),(-1,-1),0.22,RL_GRID),
        ("BOX",            (0,0),(-1,-1),0.50,RL_TEAL),
        ("VALIGN",         (0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",    (0,0),(-1,-1),5),
        ("RIGHTPADDING",   (0,0),(-1,-1),5),
        ("TOPPADDING",     (0,0),(-1,-1),3),
        ("BOTTOMPADDING",  (0,0),(-1,-1),3),
    ]))
    return t

def _kpi_grid(kpis, styles):
    sm = styles
    tile_w = (CW - 5*0.28*cm) / 3
    accent_colors = [
        HEX["teal_dk"], HEX["info"], HEX["success"],
        HEX["teal"],    HEX["warning"], HEX["danger"],
        HEX["teal_md"], HEX["amber"],  HEX["teal_dk"],
    ]
    def _tile(lbl, val, sub, i):
        ac = colors.HexColor(accent_colors[i % len(accent_colors)])
        inner = [
            [_ph(lbl, sm["kpi_lbl"])],
            [_ph(val, sm["kpi_val"])],
            [_ph(sub, sm["kpi_sub"])],
        ]
        t = Table(inner, colWidths=[tile_w-0.4*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), RL_CARD),
            ("BOX",           (0,0),(-1,-1), 0.7, RL_RULE),
            ("LINEABOVE",     (0,0),(-1,0),  4.0, ac),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("RIGHTPADDING",  (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ]))
        return t
    gap = 0.28*cm
    rows = []
    for i in range(0, len(kpis), 3):
        chunk = list(kpis[i:i+3])
        while len(chunk)<3: chunk.append(("","",""))
        rows.append([_tile(l,v,s,i+j) for j,(l,v,s) in enumerate(chunk)])
    outer = Table(rows, colWidths=[tile_w,tile_w,tile_w])
    outer.setStyle(TableStyle([
        ("LEFTPADDING",   (0,0),(-1,-1),gap/2),
        ("RIGHTPADDING",  (0,0),(-1,-1),gap/2),
        ("TOPPADDING",    (0,0),(-1,-1),gap/2),
        ("BOTTOMPADDING", (0,0),(-1,-1),gap/2),
        ("VALIGN",        (0,0),(-1,-1),"TOP"),
    ]))
    return outer


# ───────────────────────────────────────────────────────
#  CANVAS CALLBACKS
# ───────────────────────────────────────────────────────

def _cover_page(canvas, doc):
    w, h = doc.pagesize; canvas.saveState()
    # Deep two-tone header
    bh = 6.0*cm
    canvas.setFillColor(RL_TEAL_DK)
    canvas.rect(0, h-bh, w, bh, fill=1, stroke=0)
    # Diagonal accent
    canvas.setFillColor(RL_TEAL)
    p = canvas.beginPath()
    p.moveTo(w,h); p.lineTo(w,h-bh); p.lineTo(w-6.5*cm,h); p.close()
    canvas.drawPath(p, fill=1, stroke=0)
    # Fine rule below band
    canvas.setStrokeColor(colors.HexColor("#009999"))
    canvas.setLineWidth(1.5); canvas.line(0,h-bh,w,h-bh)
    # Brand
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold",28); canvas.drawString(ML, h-1.62*cm, BRAND)
    canvas.setFont("Helvetica-Oblique",10); canvas.setFillColor(colors.HexColor("#B0E0E0"))
    canvas.drawString(ML, h-2.30*cm, TAGLINE)
    canvas.setFont("Helvetica-Bold",9.5); canvas.setFillColor(colors.HexColor("#E0F4F4"))
    canvas.drawRightString(w-MR, h-1.62*cm, "ANALYTICS PERFORMANCE REPORT")
    canvas.setFont("Helvetica",8.5); canvas.setFillColor(colors.HexColor("#90C8C8"))
    canvas.drawRightString(w-MR, h-2.30*cm, datetime.now().strftime("%Y"))
    # Bottom stripe
    canvas.setFillColor(RL_TEAL); canvas.rect(0,0,w,0.60*cm,fill=1,stroke=0)
    canvas.setFillColor(colors.white); canvas.setFont("Helvetica-Bold",7.5)
    canvas.drawString(ML, 0.20*cm, BRAND)
    canvas.setFont("Helvetica",7)
    canvas.drawRightString(w-MR, 0.20*cm, "Confidential · Authorised use only")
    canvas.restoreState()

def _inner_page(canvas, doc):
    w, h = doc.pagesize; canvas.saveState()
    # Header
    hh = 0.62*cm
    canvas.setFillColor(RL_TEAL_DK); canvas.rect(0,h-hh,w,hh,fill=1,stroke=0)
    canvas.setFillColor(colors.white); canvas.setFont("Helvetica-Bold",8)
    canvas.drawString(ML, h-0.42*cm, BRAND)
    canvas.setFont("Helvetica",7.5); canvas.setFillColor(colors.HexColor("#A8D8D8"))
    canvas.drawRightString(w-MR, h-0.42*cm, _CURRENT_CHAPTER[0])
    # Footer
    canvas.setStrokeColor(RL_RULE); canvas.setLineWidth(0.5)
    canvas.line(ML, 0.75*cm, w-MR, 0.75*cm)
    canvas.setFont("Helvetica-Bold",7.5); canvas.setFillColor(RL_TEAL_DK)
    canvas.drawString(ML, 1.28*cm, BRAND)
    canvas.setFont("Helvetica-Oblique",7); canvas.setFillColor(rl("muted"))
    canvas.drawString(ML+50, 1.28*cm, TAGLINE)
    canvas.setFont("Helvetica-Bold",7.5); canvas.setFillColor(RL_TEAL_DK)
    canvas.drawRightString(w-MR, 1.28*cm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# ───────────────────────────────────────────────────────
#  STORY HELPERS
# ───────────────────────────────────────────────────────

def _chapter(num, title, subtitle, styles):
    _CURRENT_CHAPTER[0] = f"{num} · {title}"
    return [CondPageBreak(5*cm), ChapterBand(num, title, subtitle), _sp(0.32)]

def _meth_block(heading, items, styles):
    return KeepTogether([
        _p(heading, styles["meth"]),
        _sp(0.05),
        _meth_tbl(items, styles["small"]),
        _sp(0.16),
    ])

def _chart_block(png, caption, fig_n, styles):
    """Full-width chart with caption — kept together."""
    if not png: return None
    cap_s = styles["caption"]
    rl_img = _img(png, CW * 0.99, 21*cm) # Safety scaling to prevent LayoutError
    return KeepTogether([
        _sp(0.14),
        rl_img,
        _ph(f"<i>Figure {fig_n} — {caption}</i>", cap_s),
        _sp(0.22),
    ])

def _tbl_block(label, tbl_obj, styles):
    return KeepTogether([
        CondPageBreak(6*cm),
        _p(label, styles["h3t"]),
        _sp(0.08),
        tbl_obj,
        _sp(0.22),
    ])

def _insight(label, html_text, styles):
    return KeepTogether([
        InsightBox(label, html_text, styles["insight_lbl"], styles["insight_txt"]),
        _sp(0.20),
    ])


# ───────────────────────────────────────────────────────
#  MAIN BUILDER
# ───────────────────────────────────────────────────────

DEPT_METRIC_DIMS = [
    ("T — Inflow",       "Total grievances received in the reporting period."),
    ("R — Resolutions",  "Grievances successfully processed and closed."),
    ("P — Caseload",     "Active workload: pending + currently assigned tasks."),
    ("S — Compliance",   "Resolutions completed within the 48-hour SLA window."),
    ("SRi — Recurrence", "Intensity of grievances requiring repeated intervention."),
    ("E — Escalations",  "Cases requiring administrative intervention at a higher level."),
]
DEPT_PERF_COEFF = [
    ("Resolution Efficiency", "R / T — gross output against total organisational demand."),
    ("Service Velocity",      "S / R — timeliness of completed work (adherence rate)."),
    ("Caseload Health",       "1 − P/T — stability of current department backlog."),
    ("Resolution Integrity",  "1 − SRi/R — resolution accuracy and quality control."),
    ("Escalation Mitigation", "1 − E/T — ability to resolve issues without escalation."),
]
WORKER_METRICS = [
    ("Resolved",   "Assignments completed within the selected period."),
    ("SLA %",      "S/R × 100 — share of resolutions delivered within 48 h of assignment."),
    ("Rating",     "Average citizen satisfaction score from resolution feedback."),
    ("Attendance", "Days with clock-in / period days × 100."),
]
WARD_METRICS = [
    ("Total",        "All grievances (pending + resolved + escalated)."),
    ("Resolved",     "Grievances closed with status Resolved."),
    ("Pending",      "Grievances not yet resolved."),
    ("SLA",          "Resolutions completed within 48 h of creation."),
    ("Escalated",    "Grievances forwarded to a higher administrative level."),
    ("Resolution %", "R/T × 100 — proportion of total grievances resolved."),
]
ZONE_METRICS = [
    ("Total",        "All grievances across wards in the zone."),
    ("Resolved",     "Closed grievances."),
    ("Pending",      "Unresolved grievances."),
    ("SLA",          "Resolutions within 48 h of creation."),
    ("Resolution %", "R/T × 100."),
]


def build_performance_report_pdf(
    *,
    title: str,
    generated_at: datetime,
    filters_note: str,
    department_rows: list[dict[str, Any]],
    worker_rows: list[dict[str, Any]],
    ward_rows: list[dict[str, Any]],
    zone_rows: list[dict[str, Any]],
    escalation: dict[str, Any],
    sustainability: dict[str, Any],
    party_control: dict[str, Any] | None = None,
    ward_geojson: dict[str, Any] | None = None,
    citizen_cis: dict[str, Any] | None = None,
) -> bytes:

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=PAGE,
        rightMargin=MR, leftMargin=ML,
        topMargin=MT, bottomMargin=MB, title=title)

    # ── Styles ──────────────────────────────────────────
    SS = getSampleStyleSheet()
    def _s(n, **kw): return ParagraphStyle(n, parent=SS["Normal"], **kw)

    styles = {
        "cover_title": _s("ct", fontName="Helvetica-Bold", fontSize=22,
                           textColor=RL_INK, leading=28, spaceAfter=5),
        "cover_sub":   _s("cs", fontSize=10, leading=14, textColor=RL_MUTED, spaceAfter=4),
        "cover_cap":   _s("cc", fontName="Helvetica-Bold", fontSize=9,
                           textColor=RL_TEAL_DK, spaceAfter=3),
        "h2":          _s("h2", fontName="Helvetica-Bold", fontSize=FS["h2"],
                           textColor=RL_INK, spaceBefore=6, spaceAfter=4, leading=20),
        "h3":          _s("h3", fontName="Helvetica-Bold", fontSize=FS["h3"],
                           textColor=RL_BODY, spaceBefore=5, spaceAfter=3),
        "h3t":         _s("h3t", fontName="Helvetica-Bold", fontSize=FS["h3"],
                           textColor=RL_TEAL_DK, spaceBefore=5, spaceAfter=3),
        "h4":          _s("h4", fontName="Helvetica-Bold", fontSize=8.5,
                           leading=11, textColor=colors.white),
        "body":        _s("body", fontSize=FS["body"], leading=15.5,
                           textColor=RL_BODY, spaceAfter=4, alignment=TA_JUSTIFY),
        "small":       _s("small", fontSize=FS["small"], leading=12.5, textColor=RL_BODY),
        "meta":        _s("meta",  fontSize=8, textColor=RL_MUTED, leading=11),
        "tiny":        _s("tiny",  fontSize=FS["tiny"], leading=10, textColor=RL_MUTED),
        "meth":        _s("meth",  fontName="Helvetica-Bold", fontSize=10,
                           textColor=RL_TEAL_DK, spaceBefore=5, spaceAfter=2),
        "caption":     _s("cap",   fontName="Helvetica-Oblique", fontSize=FS["caption"],
                           textColor=RL_MUTED, alignment=TA_CENTER, spaceAfter=3),
        "end_note":    _s("en",    fontSize=FS["small"], alignment=TA_CENTER, textColor=RL_MUTED),
        "toc_ch":      _s("tch",   fontName="Helvetica-Bold", fontSize=10,
                           textColor=RL_INK, spaceBefore=3, spaceAfter=1, leading=14),
        "toc_desc":    _s("tdesc", fontSize=8.5, textColor=RL_MUTED, leading=11),
        "kpi_lbl":     _s("kl",    fontName="Helvetica-Bold", fontSize=FS["kpi_lbl"],
                           textColor=RL_MUTED, leading=11),
        "kpi_val":     _s("kv",    fontName="Helvetica-Bold", fontSize=FS["kpi_val"],
                           textColor=RL_INK, leading=26),
        "kpi_sub":     _s("ks",    fontSize=7.5, textColor=RL_MUTED, leading=10),
        "insight_lbl": _s("il",    fontName="Helvetica-Bold", fontSize=8.5,
                           textColor=RL_TEAL_DK),
        "insight_txt": _s("it",    fontSize=9.5, leading=15, textColor=RL_BODY),
    }

    _CURRENT_CHAPTER[0] = ""
    story: list = []
    fn = [0]    # figure counter

    def _nf(caption, png):
        blk = _chart_block(png, caption, fn[0]+1, styles)
        if blk: fn[0] += 1; story.append(blk)

    # ── Map images ──────────────────────────────────────
    pc = party_control if isinstance(party_control, dict) else {}
    cover_map_png = political_map_png = None
    if ward_geojson:
        try:
            from app.services.party_map_pdf import render_delhi_party_map_png
            cover_map_png = render_delhi_party_map_png(ward_geojson, [])
            pw = pc.get("wards") or []
            if pw: political_map_png = render_delhi_party_map_png(ward_geojson, pw)
        except Exception: pass

    # ════════════════════════════════════════════════════
    # COVER
    # ════════════════════════════════════════════════════
    story.append(_sp(5.8))
    story.append(_p(title, styles["cover_title"]))
    story.append(_sp(0.10))
    story.append(_p(f"Generated: {generated_at.strftime('%d %B %Y  ·  %H:%M IST')}", styles["cover_sub"]))
    story.append(_p(f"Scope: {filters_note}", styles["cover_sub"]))
    story.append(_sp(0.35))
    story.append(HRFlowable(width="38%", thickness=3.0, color=RL_TEAL,
                             hAlign="LEFT", spaceBefore=2, spaceAfter=10))
    story.append(_sp(0.20))
    story.append(_p(
        "This report presents a comprehensive, data-driven assessment of civic service delivery "
        "across departments, field officers, wards, and administrative zones. All composite "
        "indices — DPI, WPI, ZPI — are derived from verified operational data and are intended "
        "to support evidence-based governance decisions.",
        styles["body"],
    ))
    story.append(_sp(0.50))
    if cover_map_png:
        story.append(_p("Delhi ward boundaries — geographic overview", styles["cover_cap"]))
        story.append(_sp(0.08))
        story.append(_img(cover_map_png, CW*0.99, 420))
    else:
        story.append(_p("Geographic layer unavailable — all data tables unaffected.", styles["cover_sub"]))


    # ════════════════════════════════════════════════════
    # TABLE OF CONTENTS
    # ════════════════════════════════════════════════════
    story.append(_sp(0.70))
    story.append(_p("Table of Contents", _s("toc0", fontName="Helvetica-Bold", fontSize=20,
                                             textColor=RL_INK, spaceAfter=8)))
    story.append(_hr(1.8, RL_TEAL)); story.append(_sp(0.15))

    toc_entries = [
        (1, "Executive Summary",              "System-level KPIs and overall performance snapshot"),
        (2, "Department-level Performance",   "DPI scoring, resolution rates, volume breakdown"),
        (3, "Field Workforce Activity",        "SLA compliance, attendance, cases resolved"),
        (4, "Ward-level Performance",          "WPI distribution, backlog, representative data"),
        (5, "Zone-level Aggregation",          "ZPI scores and zone-wide outcome tables"),
        (6, "Escalation Structure",            "Escalation concentration by zone and department"),
        (7, "Political Geography",             "Ward performance by political affiliation"),
        (8, "Citizens — Civic Impact Score",  "Top and bottom civic participation rankings"),
        (9, "Sustainability & SDG Mapping",   "SDG alignment and Sustainability Index (SI)"),
    ]
    for num, ch, desc in toc_entries:
        row = Table(
            [[
                _ph(f"<font color='#005F5F'><b>{num:02d}</b></font>",
                    _s("tn", fontName="Helvetica-Bold", fontSize=15, textColor=RL_TEAL_DK, leading=18)),
                Table([[_ph(ch, styles["toc_ch"])],[_ph(desc, styles["toc_desc"])]],
                      colWidths=[CW-1.2*cm]),
            ]],
            colWidths=[1.0*cm, CW-1.2*cm],
        )
        row.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),5),
            ("RIGHTPADDING",(0,0),(-1,-1),5),
            ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),2),
        ]))
        story.append(KeepTogether([
            row,
            HRFlowable(width="100%",thickness=0.4,color=RL_RULE,spaceBefore=3,spaceAfter=3),
        ]))

    # ════════════════════════════════════════════════════
    # CH 1 · EXECUTIVE SUMMARY
    # ════════════════════════════════════════════════════
    story.extend(_chapter(1, "Executive Summary",
                           "System-level KPIs and overall performance snapshot", styles))

    story.append(_p(
        "The nine tiles below summarise performance across all analytical dimensions. "
        "Figures are drawn directly from the operational database for the selected scope and period.",
        styles["body"],
    ))
    story.append(_sp(0.20))

    # KPI computation
    _grv  = sum(d.get("metrics",{}).get("total",        0) for d in department_rows)
    _res  = sum(d.get("metrics",{}).get("resolved",     0) for d in department_rows)
    _pend = sum(d.get("metrics",{}).get("pending",      0) for d in department_rows)
    _sla  = sum(d.get("metrics",{}).get("sla_resolved", 0) for d in department_rows)
    _esc  = sum(d.get("metrics",{}).get("escalated",    0) for d in department_rows)
    rrate = (_res/_grv*100)  if _grv else 0.0
    srate = (_sla/_res*100)  if _res else 0.0
    dpis  = [d["scores"]["dpi"] for d in department_rows if d.get("scores")]
    avg_dpi = sum(dpis)/len(dpis) if dpis else 0.0
    wpis  = [w["scores"]["wpi"] for w in ward_rows  if w.get("scores")]
    avg_wpi = sum(wpis)/len(wpis) if wpis else 0.0
    zpis  = [z["scores"]["zpi"] for z in zone_rows  if z.get("scores")]
    avg_zpi = sum(zpis)/len(zpis) if zpis else 0.0

    kpi_list = [
        ("TOTAL GRIEVANCES",  f"{_grv:,}",           "Demand inflow volume"),
        ("RESOLUTION RATE",   f"{rrate:.1f}%",        "Proportion closed"),
        ("SLA COMPLIANCE",    f"{srate:.1f}%",        "Resolved within 48 h"),
        ("AVG DEPT DPI",      f"{avg_dpi:.1f}",       "Dept health (0–100)"),
        ("AVG WARD WPI",      f"{avg_wpi:.1f}",       "Ward health (0–100)"),
        ("AVG ZONE ZPI",      f"{avg_zpi:.1f}",       "Zone health (0–100)"),
        ("PENDING BACKLOG",   f"{_pend:,}",            "Awaiting resolution"),
        ("ESCALATED CASES",   f"{_esc:,}",             "Higher-tier handling"),
        ("ACTIVE DEPTS",      f"{len(department_rows)}","Departments in scope"),
    ]
    story.append(KeepTogether([_kpi_grid(kpi_list, styles), _sp(0.22)]))

    # Summary donut
    _nf("System-wide Resolution Rate and SLA Compliance overview",
        chart_summary_donut(rrate, srate))

    # Insight box — uses _ph so <b> tags render
    if department_rows:
        td = max(department_rows, key=lambda x: x.get("scores",{}).get("dpi",0))
        top_dept = td.get("name","N/A")
        top_dpi  = td.get("scores",{}).get("dpi",0)
        worst    = [d for d in department_rows if d.get("scores",{}).get("dpi",0) < 65]
        insight_html = (
            f"Overall resolution rate: <b>{rrate:.1f}%</b> — "
            f"SLA compliance: <b>{srate:.1f}%</b>.  "
            f"Top-performing department: <b>{top_dept}</b> (DPI {top_dpi:.1f}).  "
            f"Active backlog: <b>{_pend:,}</b> grievances remain open.  "
            f"Escalated cases requiring higher-tier attention: <b>{_esc:,}</b>."
            + (f"  <b>{len(worst)} department(s)</b> are below the DPI baseline of 65 "
               "and should be prioritised for operational review." if worst else "")
        )
        story.append(_insight("Headline Insight", insight_html, styles))


    # ════════════════════════════════════════════════════
    # CH 2 · DEPARTMENT PERFORMANCE
    # ════════════════════════════════════════════════════
    story.extend(_chapter(2, "Department-level Performance",
                           "DPI scoring, resolution rates, and volume breakdown", styles))

    story.append(_p(
        "Each department is evaluated across six operational dimensions that are weighted "
        "and combined into the Department Performance Index (DPI). A score of 70 represents "
        "the operational baseline; scores above 80 indicate strong performance.",
        styles["body"],
    ))
    story.append(_sp(0.16))
    story.append(_meth_block("Metric Dimensions",        DEPT_METRIC_DIMS, styles))
    story.append(_meth_block("Performance Coefficients", DEPT_PERF_COEFF,  styles))
    story.append(KeepTogether([
        _p("DPI Formula", styles["meth"]),
        _eq_block([
            r"$\mathrm{DPI} = 0.30\,R_{\mathrm{eff}} + 0.25\,S_{\mathrm{vel}} + 0.20\,C_{\mathrm{health}} + 0.15\,R_{\mathrm{int}} + 0.10\,E_{\mathrm{mit}}$",
            r"$R_{\mathrm{eff}} = \dfrac{R}{T}, \quad S_{\mathrm{vel}} = \dfrac{S}{R}, \quad C_{\mathrm{health}} = 1 - \dfrac{P}{T}, \quad R_{\mathrm{int}} = 1 - \dfrac{\Sigma R_i}{R}, \quad E_{\mathrm{mit}} = 1 - \dfrac{E}{T}$",
        ], styles),
        _p("Departments with zero inflow (T = 0) are assigned a baseline DPI of 70.0.", styles["tiny"]),
        _sp(0.12),
    ]))

    _nf("Department Performance Index — sorted highest to lowest", chart_dept_dpi(department_rows))
    _nf("Resolution % vs SLA % by Department",                     chart_dept_resolution(department_rows))
    _nf("Grievance Volume — Resolved / Pending / Escalated stack",  chart_dept_volume(department_rows))

    # Dept table
    h4s = styles["h4"]; sm = styles["small"]
    dh  = ["Department","T","R","P","S","Rec.","Esc.","Res%","SLA%","DPI","Status"]
    dd  = [[_pc(h, h4s) for h in dh]]
    for d in department_rows:
        m,s = d.get("metrics") or {}, d.get("scores") or {}
        dd.append([
            _pc(d.get("name","–"),                             sm),
            _pc(m.get("total","–"),                            sm),
            _pc(m.get("resolved","–"),                         sm),
            _pc(m.get("pending","–"),                          sm),
            _pc(m.get("sla_resolved","–"),                     sm),
            _pc(m.get("total_repeat_count","–"),               sm),
            _pc(m.get("escalated","–"),                        sm),
            _pc(f"{(s.get('resolution_rate') or 0)*100:.1f}%", sm),
            _pc(f"{(s.get('sla_rate') or 0)*100:.0f}%",        sm),
            _pc(s.get("dpi","–"),                              sm),
            _pc(d.get("performance","–"),                      sm),
        ])
    if len(dd) > 1:
        cw = [c*cm for c in [3.8,1.0,1.0,1.0,1.0,1.0,1.0,1.5,1.4,1.3,1.5]]
        story.append(_tbl_block("Table 1 — Department Results",
                                _tbl(dd, cw, hfs=7, bfs=6.5, mixed=True), styles))


    # ════════════════════════════════════════════════════
    # CH 3 · FIELD WORKFORCE
    # ════════════════════════════════════════════════════
    story.extend(_chapter(3, "Field Workforce Activity & Compliance",
                           "SLA adherence, attendance, and case resolution per officer", styles))

    story.append(_p(
        "Field officers are the primary service delivery mechanism. This chapter tracks each "
        "officer's SLA compliance, attendance rate, and case throughput over the reporting period.",
        styles["body"],
    ))
    story.append(_sp(0.16))
    story.append(_meth_block("Worker Metrics", WORKER_METRICS, styles))
    story.append(KeepTogether([
        _p("Key Formulae", styles["meth"]),
        _eq_block([
            r"$\mathrm{SLA\%} = \dfrac{S}{R} \times 100$",
            r"$\mathrm{Attendance\%} = \dfrac{\text{Days with clock-in}}{\text{Period days}} \times 100$",
        ], styles),
        _sp(0.04),
    ]))

    _nf("Worker SLA % and Attendance % — Top 30 officers sorted by SLA compliance",
        chart_worker_sla(worker_rows))
    _nf("Cases resolved by each field officer — Top 30 by volume",
        chart_worker_resolved(worker_rows))

    wh = [[_pc(h, h4s) for h in [
        "Officer","Department","Active","Resolved","SLA %","Rating","Attendance","Status"]]]
    for w in worker_rows:
        m  = w.get("metrics") or {}
        st = str(w.get("status") or "offDuty")
        rv = m.get("rating")
        wh.append([
            _pc(w.get("name","–"),                                         sm),
            _pc(w.get("department_name","–"),                              sm),
            _pc(m.get("tasks_active",0),                                   sm),
            _pc(m.get("period_resolved",0),                                sm),
            _pc(f"{(m.get('sla_rate') or 0)*100:.0f}%",                    sm),
            _pc(f"{float(rv):.1f}" if rv is not None else "–",             sm),
            _pc(f"{(m.get('attendance_rate') or 0)*100:.0f}%",             sm),
            _pc("On Duty" if st=="onDuty" else "Off Duty",                 sm),
        ])
    if len(wh) > 1:
        ww = [3.6*cm,3.2*cm,1.3*cm,1.5*cm,1.4*cm,1.2*cm,1.9*cm,1.6*cm]
        story.append(_tbl_block("Table 2 — Field Officer Summary",
                                _tbl(wh, ww, hfs=7.5, bfs=7, mixed=True), styles))


    # ════════════════════════════════════════════════════
    # CH 4 · WARD PERFORMANCE
    # ════════════════════════════════════════════════════
    story.extend(_chapter(4, "Ward-level Performance & Representation",
                           "WPI distribution, backlog analysis, and representative data", styles))

    story.append(_p(
        "The Ward Performance Index (WPI) is the unweighted average of Department DPI values "
        "computed at (ward, department) granularity. It surfaces hyperlocal service delivery "
        "quality and enables targeted interventions at ward level.",
        styles["body"],
    ))
    story.append(_sp(0.16))
    story.append(_meth_block("Ward Metrics", WARD_METRICS, styles))
    story.append(KeepTogether([
        _eq_block([
            r"$\mathrm{WPI}_{w} = \dfrac{\sum_{d \in w} \mathrm{DPI}_{d}}{N_{\mathrm{active\;depts}}}$",
        ], styles),
        _p("Wards with no recorded activity are assigned a default WPI of 70.0.", styles["tiny"]),
        _sp(0.12),
    ]))

    _nf("WPI distribution across all wards (sorted highest to lowest)",
        chart_ward_wpi(ward_rows))
    _nf("Top 20 wards by pending backlog — diverging resolved vs pending view",
        chart_ward_backlog(ward_rows))

    # Ward table
    wrd_hdr = ["","Ward","Zone","Representative","Phone","Party",
               "Total","Res.","Pend.","SLA","Esc.","Res%","WPI","Status"]
    wd      = [[_pc(h, h4s) for h in wrd_hdr]]
    rc      = [None]

    for d in ward_rows:
        m,s   = d.get("metrics") or {}, d.get("scores") or {}
        wname = str(d.get("name","–"))
        if d.get("number") is not None: wname += f" #{d['number']}"
        pcode = str(d.get("party_short_code") or "").strip()
        phex  = None
        for pw in pc.get("wards") or []:
            if str(pw.get("id"))==str(d.get("id")): phex=pw.get("party_color"); break
        if not phex and pcode:
            for pp in pc.get("parties") or []:
                if str(pp.get("short_code",""))==pcode: phex=pp.get("color"); break
        wd.append([
            " ",
            _pc(wname,                                         sm),
            _pc(d.get("zone_name")           or "–",          sm),
            _pc(d.get("representative_name") or "–",          sm),
            _pc(_fmt_phone(d.get("representative_phone")),    sm),
            _pc(pcode                         or "–",          sm),
            _pc(m.get("total","–"),                            sm),
            _pc(m.get("resolved","–"),                         sm),
            _pc(m.get("pending","–"),                          sm),
            _pc(m.get("sla_resolved","–"),                     sm),
            _pc(m.get("escalated","–"),                        sm),
            _pc(f"{(s.get('resolution_rate') or 0)*100:.1f}%", sm),
            _pc(s.get("wpi","–"),                              sm),
            _pc(d.get("performance","–"),                      sm),
        ])
        rc.append(phex or NEUTRAL)

    ex = [("BACKGROUND",(0,i),(0,i),_hex_rl(rc[i]))
          for i in range(1,len(wd)) if rc[i]]
    ex.extend([("LEFTPADDING",(0,0),(0,-1),0),("RIGHTPADDING",(0,0),(0,-1),0)])
    if len(wd) > 1:
        wf = [0.014,0.10,0.076,0.115,0.094,0.047,
              0.055,0.055,0.055,0.055,0.055,0.062,0.058,0.110]
        wcols = [CW*f for f in wf]
        story.append(_tbl_block("Table 3 — Ward Outcomes",
                                _tbl(wd, wcols, extra=ex, hfs=6.5, bfs=6, mixed=True), styles))


    # ════════════════════════════════════════════════════
    # CH 5 · ZONE AGGREGATION
    # ════════════════════════════════════════════════════
    story.extend(_chapter(5, "Zone-level Aggregation",
                           "ZPI scores and zone-wide performance outcomes", styles))

    story.append(_p(
        "The Zone Performance Index (ZPI) aggregates WPI values across all wards in each "
        "administrative zone, providing a macroscopic view for senior administration and "
        "cross-zone benchmarking.",
        styles["body"],
    ))
    story.append(_sp(0.16))
    story.append(_meth_block("Zone Metrics", ZONE_METRICS, styles))
    story.append(KeepTogether([
        _eq_block([
            r"$\mathrm{ZPI}_{z} = \dfrac{\sum_{w \in z} \mathrm{WPI}_{w}}{N_{\mathrm{wards}}}$",
        ], styles),
        _p("Zones with no activity are assigned a default ZPI of 70.0.", styles["tiny"]),
        _sp(0.12),
    ]))

    _nf("Zone Performance Index — lollipop chart with baseline reference",
        chart_zone_zpi(zone_rows))

    zh = [[_pc(h, h4s) for h in ["Zone","Total","Resolved","Pending","SLA","Res%","ZPI","Status"]]]
    for d in zone_rows:
        m,s = d.get("metrics") or {}, d.get("scores") or {}
        zl  = str(d.get("name","–"))
        if d.get("code"): zl += f" ({d['code']})"
        zh.append([
            _pc(zl,                                              sm),
            _pc(m.get("total","–"),                              sm),
            _pc(m.get("resolved","–"),                           sm),
            _pc(m.get("pending","–"),                            sm),
            _pc(m.get("sla_resolved","–"),                       sm),
            _pc(f"{(s.get('resolution_rate') or 0)*100:.1f}%",   sm),
            _pc(s.get("zpi","–"),                                sm),
            _pc(d.get("performance","–"),                        sm),
        ])
    if len(zh) > 1:
        zw = [5.0*cm,1.4*cm,1.5*cm,1.5*cm,1.4*cm,1.8*cm,1.5*cm,2.4*cm]
        story.append(_tbl_block("Table 4 — Zone Aggregation",
                                _tbl(zh, zw, hfs=8, bfs=7.5, mixed=True), styles))


    # ════════════════════════════════════════════════════
    # CH 6 · ESCALATION
    # ════════════════════════════════════════════════════
    story.extend(_chapter(6, "Escalation Structure & Concentration",
                           "Where administrative pressure is building", styles))

    story.append(_p(
        "Escalated cases require higher-tier administrative intervention and consume "
        "disproportionate management capacity. Concentration in any single zone or department "
        "signals systemic pressure points demanding structural — not just operational — remediation.",
        styles["body"],
    ))
    story.append(_sp(0.18))

    if escalation:
        total_esc = escalation.get("total","–")
        reopened  = escalation.get("reopened_count","–")
        story.append(_insight(
            "Escalation Summary",
            f"<b>{total_esc}</b> total escalated cases recorded in this period.  "
            f"<b>{reopened}</b> cases were reopened after an initial resolution attempt — "
            "indicating quality issues or incomplete resolutions that merit targeted review.",
            styles,
        ))

        _nf("Escalation concentration by Zone and by Department",
            chart_escalation(escalation))

        def _etbl(header, rows_in, nk, ck):
            data = [[_pc(header,h4s), _pc("Count",h4s)]]
            for r in rows_in or []:
                n = str(r.get(nk,"–"))
                if ck and r.get(ck): n += f" ({r[ck]})"
                data.append([_pc(n,sm), _pc(str(r.get("count",0)),sm)])
            return _tbl(data, _fit([9.0*cm,3.0*cm]), hfs=8, bfs=8, mixed=True)

        half = CW/2 - 0.3*cm
        zt   = _etbl("Zone",       escalation.get("by_zone") or [],       "name","code")
        dt   = _etbl("Department", escalation.get("by_department") or [], "name",None)
        pair = Table([[zt,dt]], colWidths=[half,half])
        pair.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),0),
            ("RIGHTPADDING",(0,0),(-1,-1),0),
            ("TOPPADDING",(0,0),(-1,-1),0),
            ("BOTTOMPADDING",(0,0),(-1,-1),0),
        ]))
        story.append(_tbl_block("Table 5 — Escalation Detail", pair, styles))


    # ════════════════════════════════════════════════════
    # CH 7 · POLITICAL GEOGRAPHY
    # ════════════════════════════════════════════════════
    story.extend(_chapter(7, "Political Geography & Performance",
                           "Ward performance cross-tabulated with political affiliation", styles))

    story.append(_p(
        "Ward-level performance is cross-tabulated with political party representation to identify "
        "operational health patterns across representative zones. This is a descriptive analysis — "
        "it surfaces outcomes, not causation.",
        styles["body"],
    ))
    story.append(_sp(0.16))

    if political_map_png:
        fn[0] += 1
        story.append(KeepTogether([
            _ph(f"<i>Figure {fn[0]} — Delhi ward political choropleth (party alignment)</i>",
                styles["caption"]),
            _img(political_map_png, CW*0.99, 420),
            _sp(0.16),
        ]))

    if party_control:
        _nf("Ward share by political party — donut chart",    chart_party_donut(party_control))
        _nf("Average ward WPI by political party",            chart_party_wpi(party_control))

        pd2 = [[_pc(h,h4s) for h in ["Party","Wards","Avg WPI","Total","Res%","SLA%"]]]
        for p in party_control.get("parties") or []:
            m = p.get("metrics") or {}
            pd2.append([
                _pc(f"{p.get('name','–')} ({p.get('short_code','')})", sm),
                _pc(str(p.get("ward_count",0)),           sm),
                _pc(str(p.get("avg_wpi","–")),             sm),
                _pc(str(m.get("total","–")),               sm),
                _pc(f"{m.get('resolution_pct',0):.1f}%",  sm),
                _pc(f"{m.get('sla_pct',0):.1f}%",         sm),
            ])
        cw = [5.0*cm,2.0*cm,2.2*cm,3.0*cm,2.6*cm,2.6*cm]
        story.append(_tbl_block("Table 6 — Party Performance Summary",
                                _tbl(pd2, cw, hfs=8, bfs=8, mixed=True), styles))


    # ════════════════════════════════════════════════════
    # CH 8 · CITIZENS — CIS
    # ════════════════════════════════════════════════════
    story.extend(_chapter(8, "Citizens — Civic Impact Score",
                           "Citizen participation rankings and engagement metrics", styles))

    story.append(_p(
        "The Civic Impact Score (CIS, range 0–100) reflects verified citizen participation: "
        "grievance reporting frequency, votes, comments, ward engagement, and quality signals. "
        "Scores use the latest stored snapshot per citizen (rolling 7-day window, IST).",
        styles["body"],
    ))
    story.append(_sp(0.14))

    cc  = citizen_cis if isinstance(citizen_cis, dict) else {}
    if cc.get("week_note"):
        story.append(_p(cc["week_note"], styles["meta"])); story.append(_sp(0.10))

    top_rows = cc.get("top") or []
    bot_rows = cc.get("bottom") or []
    cis_hdr  = ["Rank","Citizen","Phone","Ward","Zone","CIS"]
    cis_cw   = [0.85*cm,3.5*cm,2.4*cm,2.4*cm,2.4*cm,1.4*cm]

    if top_rows:
        td2 = [[_pc(h,h4s) for h in cis_hdr]]
        for i, row in enumerate(top_rows,1):
            td2.append([_pc(str(i),sm),_pc(row.get("name","–"),sm),_pc(row.get("phone","–"),sm),
                        _pc(row.get("ward","–"),sm),_pc(row.get("zone","–"),sm),
                        _pc(f"{row.get('cis_score',0):.1f}",sm)])
        story.append(_tbl_block("Table 7 — Top 10 Civic Impact Scores",
                                _tbl(td2,cis_cw,hfs=8,bfs=7.5,mixed=True), styles))
    else:
        story.append(_p("No CIS snapshots on file — run the weekly snapshot job to populate.", styles["small"]))
        story.append(_sp(0.10))

    if bot_rows:
        bd2 = [[_pc(h,h4s) for h in cis_hdr]]
        for i, row in enumerate(bot_rows,1):
            bd2.append([_pc(str(i),sm),_pc(row.get("name","–"),sm),_pc(row.get("phone","–"),sm),
                        _pc(row.get("ward","–"),sm),_pc(row.get("zone","–"),sm),
                        _pc(f"{row.get('cis_score',0):.1f}",sm)])
        story.append(_tbl_block(
            "Table 8 — Bottom 5 Civic Impact Scores (lowest among citizens with snapshots)",
            _tbl(bd2,cis_cw,hfs=8,bfs=7.5,mixed=True), styles))
    elif top_rows:
        story.append(_p("Insufficient distinct scores for a separate bottom list.", styles["small"]))


    # ════════════════════════════════════════════════════
    # CH 9 · SUSTAINABILITY
    # ════════════════════════════════════════════════════
    story.extend(_chapter(9, "Sustainability Analytics & SDG Mapping",
                           "Departmental SDG alignment and Sustainability Index (SI)", styles))

    story.append(_p(
        "This chapter maps departments to United Nations Sustainable Development Goals (SDGs) "
        "and reports the Sustainability Index (SI) — a DPI-derived composite interpreted through "
        "SDG alignment metadata. It supports governance reporting against national and global "
        "sustainability commitments.",
        styles["body"],
    ))
    story.append(_sp(0.16))
    story.append(KeepTogether([
        _p("Sustainability Index Formula", styles["meth"]),
        _eq_block([
            r"$\mathrm{SI}_{\mathrm{SDG}} = \dfrac{\sum_{d \in \mathrm{SDG}} \mathrm{DPI}_{d}}{N_{\mathrm{mapped}}}$",
        ], styles),
        _sp(0.04),
    ]))

    if isinstance(sustainability, dict):
        totals      = sustainability.get("totals") or {}
        sus_rows    = sustainability.get("rows") or []
        sdg_summary = sustainability.get("sdg_summary") or []
        sus_dept    = sustainability.get("department_rows") or []

        if totals:
            mapped  = totals.get("mapped_departments",0)
            total   = totals.get("departments",0)
            unmapped= totals.get("unmapped_departments",0)
            sdg_g   = totals.get("sdg_groups",0)
            avg_si  = totals.get("average_sustainability_index",0)
            story.append(_insight(
                "SDG Coverage",
                f"<b>{mapped}</b> out of <b>{total}</b> departments have been mapped to SDGs.  "
                f"<b>{unmapped}</b> department(s) remain unmapped.  "
                f"Departments span <b>{sdg_g}</b> distinct SDG groups.  "
                f"Average Sustainability Index across all groups: <b>{avg_si}</b>.",
                styles,
            ))

        if sdg_summary:
            sh  = ["SDG","Mapped Departments","Avg SI"]
            sd2 = [[_pc(h,h4s) for h in sh]]
            for s in sdg_summary:
                sd2.append([_pc(str(s.get("sdg","Unmapped")),sm),
                            _pc(str(s.get("department_count",0)),sm),
                            _pc(f"{float(s.get('sustainability_index',0)):.2f}",sm)])
            story.append(_tbl_block("Table 9 — SDG-wise Sustainability Summary",
                                    _tbl(sd2,[7.2*cm,3.2*cm,2.4*cm],hfs=8,bfs=7.5,mixed=True),
                                    styles))

        if sus_rows:
            dh2 = ["SDG","Description","Mapped Departments","Count","SI","Max SI"]
            dd2 = [[_pc(h,h4s) for h in dh2]]
            for r in sus_rows:
                dd2.append([_pc(str(r.get("sdg","Unmapped")),sm),
                            _pc(str(r.get("description","–")),sm),
                            _pc(str(r.get("mapped_departments_text","–")),sm),
                            _pc(str(r.get("department_count",0)),sm),
                            _pc(f"{float(r.get('sustainability_index',0)):.2f}",sm),
                            _pc(f"{float(r.get('max_sustainability_index',0)):.2f}",sm)])
            story.append(_tbl_block("Table 10 — SDG-wise Mapping",
                                    _tbl(dd2,[2.0*cm,3.0*cm,4.2*cm,1.2*cm,1.4*cm,1.8*cm],
                                         hfs=8,bfs=7,mixed=True), styles))
        elif sus_dept:
            dh2 = ["Department","SDG","Description","SI","Status"]
            dd2 = [[_pc(h,h4s) for h in dh2]]
            for r in sus_dept:
                dd2.append([_pc(str(r.get("department_name","–")),sm),
                            _pc(str(r.get("sdg","Unmapped")),sm),
                            _pc(str(r.get("description","–")),sm),
                            _pc(f"{float(r.get('sustainability_index',0)):.2f}",sm),
                            _pc(str(r.get("performance","–")),sm)])
            story.append(_tbl_block("Table 10 — Departmental Sustainability Mapping",
                                    _tbl(dd2,[3.2*cm,3.0*cm,4.2*cm,1.2*cm,1.8*cm],
                                         hfs=8,bfs=7.2,mixed=True), styles))
        elif not totals and not sdg_summary:
            msg = sustainability.get("message")
            story.append(_p(str(msg or "Data pending for this reporting cycle."), styles["small"]))
    else:
        story.append(_p(str(sustainability or "Data pending for this reporting cycle."), styles["small"]))

    # ── End matter ──────────────────────────────────────
    story.append(_sp(1.6))
    story.append(HRFlowable(width="45%",thickness=1.2,color=RL_TEAL,hAlign="CENTER",
                             spaceBefore=4,spaceAfter=8))
    story.append(_sp(0.18))
    story.append(_p(
        f"{BRAND}  ·  Analytics Performance Report  ·  "
        f"Generated {generated_at.strftime('%d %B %Y')}",
        styles["end_note"],
    ))
    story.append(_sp(0.06))
    story.append(_p(
        "Intended for authorised review of municipal performance analytics. "
        "Unauthorised reproduction or distribution is prohibited.",
        styles["end_note"],
    ))

    doc.build(story, onFirstPage=_cover_page, onLaterPages=_inner_page)
    return buf.getvalue()