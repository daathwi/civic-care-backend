"""Static Delhi ward map (matplotlib) + mathtext renders for PDF exports."""

from __future__ import annotations

import io
import os
import re
import tempfile
from typing import Any

# Writable config dir for font cache (Docker / restricted $HOME)
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon

NEUTRAL_HEX = "#9ca3af"


def _normalize_text(s: str) -> str:
    return "".join(s.lower().split())


def _ward_feature_name(props: dict) -> str:
    if not props:
        return ""
    keys = [
        "WardName",
        "ward_name",
        "WARD_NAME",
        "name",
        "NAME",
        "ward",
        "WARD",
        "NW2022",
    ]
    for k in keys:
        v = props.get(k)
        if v is not None:
            t = str(v).strip()
            if t:
                return t
    return ""


def _ward_feature_number(props: dict) -> str:
    if not props:
        return ""
    keys = [
        "Ward_No",
        "ward_no",
        "WARD_NO",
        "number",
        "NUMBER",
        "ward_number",
        "WARD_NUMBER",
    ]
    for k in keys:
        v = props.get(k)
        if v is not None:
            return str(v)
    return ""


def match_party_ward_for_feature(
    feature: dict,
    ward_list: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Mirror admin Party Map: match GeoJSON feature to control.wards entry."""
    props = feature.get("properties") or {}
    name = _normalize_text(_ward_feature_name(props))
    num = str(_ward_feature_number(props)).strip()
    for w in ward_list:
        wn = _normalize_text(str(w.get("name") or ""))
        wnum = str(w.get("number") or "").strip()
        if name and wn and (wn in name or name in wn):
            return w
        if num and wnum and num == wnum:
            return w
    return None


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    if not hex_color:
        return (0.61, 0.61, 0.61)
    h = hex_color.strip().lstrip("#")
    if len(h) == 6 and re.match(r"^[0-9a-fA-F]{6}$", h):
        return (
            int(h[0:2], 16) / 255.0,
            int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0,
        )
    return (0.61, 0.61, 0.61)


def _iter_polygons(geometry: dict) -> list[list[tuple[float, float]]]:
    """Yield rings (exterior only) as lists of (lng, lat)."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return []
    rings: list[list[tuple[float, float]]] = []
    if gtype == "Polygon":
        ring = coords[0]
        rings.append([(float(c[0]), float(c[1])) for c in ring])
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly and poly[0]:
                ring = poly[0]
                rings.append([(float(c[0]), float(c[1])) for c in ring])
    return rings


def render_delhi_party_map_png(
    geojson: dict[str, Any],
    party_wards: list[dict[str, Any]],
    *,
    figsize_inches: tuple[float, float] = (10.0, 10.5),
    dpi: int = 200,
) -> bytes | None:
    """
    Raster map: ward polygons filled by party_color (same as Party Map).
    GeoJSON from /wards/geojson; wards list from /analytics/parties/control.wards.
    """
    features = geojson.get("features") or []
    if not features:
        return None

    patches: list = []
    facecolors: list[tuple[float, float, float, float]] = []

    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        w = match_party_ward_for_feature(feat, party_wards)
        hex_c = (w or {}).get("party_color") or NEUTRAL_HEX
        rgb = _hex_to_rgb(str(hex_c))
        rgba = (*rgb, 0.88)
        for ring in _iter_polygons(geom):
            if len(ring) < 3:
                continue
            patches.append(MplPolygon(ring, closed=True))
            facecolors.append(rgba)

    if not patches:
        return None

    fig, ax = plt.subplots(figsize=figsize_inches, dpi=dpi)
    fig.patch.set_facecolor("white")
    coll = PatchCollection(
        patches,
        facecolors=facecolors,
        edgecolors=(0.25, 0.25, 0.25, 0.5),
        linewidths=0.35,
    )
    ax.add_collection(coll)
    ax.autoscale()
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.set_title("CivicCare — Delhi wards by political party", fontsize=10, pad=8)

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        bbox_inches="tight",
        pad_inches=0.08,
        facecolor="white",
    )
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_mathtext_png(
    lines: list[str],
    *,
    fontsize: int = 6,
    dpi: int = 220,
    line_height: float = 0.38,
    fig_width: float | None = None,
) -> bytes:
    """
    Render matplotlib mathtext (LaTeX subset) to high-resolution PNG for PDF embedding.
    Pass each line as a full math string including $...$ delimiters.
    High DPI keeps formulas sharp when scaled to column width in the PDF.
    """
    n = max(len(lines), 1)
    fig_h = 0.32 + line_height * n
    w = fig_width if fig_width is not None else max(6.5, 0.022 * max((len(s) for s in lines), default=50))
    fig = plt.figure(figsize=(w, fig_h), dpi=dpi)
    fig.patch.set_alpha(0.0)

    for i, line in enumerate(lines):
        y = 1.0 - (i + 0.5) / n
        fig.text(
            0.5,
            y,
            line,
            fontsize=fontsize,
            ha="center",
            va="center",
        )

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        bbox_inches="tight",
        pad_inches=0.1,
        transparent=True,
    )
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


# ── Advanced chart generators for executive report ──────────────────────────


def render_dpi_heatmap_png(
    dept_names: list[str],
    score_matrix: list[list[float]],
    component_labels: list[str],
    *,
    figsize: tuple[float, float] = (8.5, 4.0),
    dpi: int = 200,
) -> bytes | None:
    """
    Department × Score-Component heatmap.
    score_matrix: rows = departments, cols = score components (0-1 scale values).
    Colour-coded red→yellow→green.  Insight: which sub-score drags each dept down.
    """
    if not dept_names or not score_matrix:
        return None
    import numpy as np

    data = np.array(score_matrix, dtype=float)
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")

    cmap = plt.cm.RdYlGn
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=1)

    ax.set_xticks(range(len(component_labels)))
    ax.set_xticklabels(component_labels, fontsize=7, rotation=30, ha="right")
    ax.set_yticks(range(len(dept_names)))
    ax.set_yticklabels([n[:28] for n in dept_names], fontsize=7)

    # Annotate each cell
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            color = "white" if val < 0.35 or val > 0.85 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=6, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.04)
    cbar.ax.tick_params(labelsize=6)
    ax.set_title("Department Performance Score Components (Heatmap)", fontsize=9, pad=8)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.12, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_boxplot_png(
    data_groups: list[list[float]],
    group_labels: list[str],
    *,
    title: str = "Distribution Analysis",
    ylabel: str = "Value",
    figsize: tuple[float, float] = (7.0, 3.5),
    dpi: int = 200,
) -> bytes | None:
    """
    Box-and-whisker plot for numeric metric across groups.
    Each group is a list of values; labels name each box.
    Insight: show spread, median, quartiles, and outliers.
    """
    non_empty = [g for g in data_groups if g]
    if not non_empty:
        return None

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")

    bp = ax.boxplot(
        data_groups,
        labels=[l[:18] for l in group_labels],
        patch_artist=True,
        showmeans=True,
        meanprops=dict(marker="D", markerfacecolor="#0d9488", markersize=5),
        medianprops=dict(color="#0f766e", linewidth=1.5),
        flierprops=dict(marker="o", markerfacecolor="#ef4444", markersize=4, alpha=0.6),
    )

    colors = ["#a7f3d0", "#bfdbfe", "#fde68a", "#fecaca", "#e9d5ff", "#c7d2fe"]
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(colors[i % len(colors)])
        patch.set_edgecolor("#374151")
        patch.set_linewidth(0.8)

    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=9, pad=8)
    ax.tick_params(axis="x", labelsize=7, rotation=15)
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_regression_scatter_png(
    x_vals: list[float],
    y_vals: list[float],
    *,
    xlabel: str = "X",
    ylabel: str = "Y",
    title: str = "Correlation Analysis",
    figsize: tuple[float, float] = (6.5, 4.0),
    dpi: int = 200,
) -> tuple[bytes, dict] | None:
    """
    Scatter plot with OLS best-fit line.
    Returns (png_bytes, stats_dict) where stats_dict has keys:
    slope, intercept, r_squared, n, t_stat, p_value_approx.
    Insight: quantify relationship between two performance variables.
    """
    import math
    import statistics as st

    if len(x_vals) < 3 or len(y_vals) < 3 or len(x_vals) != len(y_vals):
        return None

    n = len(x_vals)
    mx = st.mean(x_vals)
    my = st.mean(y_vals)

    ss_xx = sum((xi - mx) ** 2 for xi in x_vals)
    ss_yy = sum((yi - my) ** 2 for yi in y_vals)
    ss_xy = sum((xi - mx) * (yi - my) for xi, yi in zip(x_vals, y_vals))

    if ss_xx == 0:
        return None

    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy != 0 else 0.0

    # t-stat for slope
    y_pred = [intercept + slope * xi for xi in x_vals]
    sse = sum((yi - yp) ** 2 for yi, yp in zip(y_vals, y_pred))
    if n > 2 and ss_xx > 0:
        se_slope = math.sqrt(sse / (n - 2) / ss_xx)
        t_stat = slope / se_slope if se_slope > 0 else 0.0
    else:
        se_slope = 0.0
        t_stat = 0.0

    # Approximate two-tailed p-value using t-distribution approximation
    df = n - 2
    if df > 0 and t_stat != 0:
        # Approximation for large df using normal; for small df use crude bound
        abs_t = abs(t_stat)
        if df >= 30:
            # Normal approximation
            z = abs_t
            p_val = 2 * math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        else:
            # Crude Student-t approximation
            p_val = 2 * (1 - 0.5 * (1 + math.erf(abs_t / math.sqrt(2))))
        p_val = max(p_val, 1e-10)
    else:
        p_val = 1.0

    stats = {
        "slope": round(slope, 6),
        "intercept": round(intercept, 6),
        "r_squared": round(r_squared, 4),
        "n": n,
        "t_stat": round(t_stat, 4),
        "p_value_approx": round(p_val, 6),
        "se_slope": round(se_slope, 6),
    }

    # Plot
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")

    ax.scatter(x_vals, y_vals, c="#0d9488", alpha=0.65, edgecolors="#065f46", s=30, linewidths=0.5)

    # Regression line
    x_line = [min(x_vals), max(x_vals)]
    y_line = [intercept + slope * x for x in x_line]
    ax.plot(x_line, y_line, color="#dc2626", linewidth=1.5, linestyle="--",
            label=f"OLS: Y = {slope:.3f}X + {intercept:.3f}")

    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=9, pad=8)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25, linewidth=0.4)

    # Annotation box
    textstr = f"R² = {r_squared:.4f}\nn = {n}\np ≈ {p_val:.4f}"
    props = dict(boxstyle="round,pad=0.4", facecolor="#f0fdf4", edgecolor="#0d9488", alpha=0.85)
    ax.text(0.03, 0.97, textstr, transform=ax.transAxes, fontsize=7,
            verticalalignment="top", bbox=props)

    ax.legend(fontsize=7, loc="lower right")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue(), stats


def render_sankey_flow_png(
    total: int,
    resolved: int,
    pending: int,
    sla_ok: int,
    escalated: int,
    *,
    title: str = "Grievance Resolution Pipeline",
    figsize: tuple[float, float] = (8.0, 3.0),
    dpi: int = 200,
) -> bytes | None:
    """
    Simplified Sankey-style horizontal stacked flow (pure matplotlib, no extras).
    Flow: Total → Resolved | Pending → SLA OK | SLA Breach, Escalated branch.
    Insight: visualise how grievance volume flows through the resolution pipeline.
    """
    if total <= 0:
        return None

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    # Stage positions
    stage_x = [0.5, 3.5, 7.0]
    bar_h = 2.5
    bar_y = 0.75

    # Colors
    c_total = "#6366f1"
    c_resolved = "#10b981"
    c_pending = "#f59e0b"
    c_sla = "#06b6d4"
    c_breach = "#ef4444"
    c_escalated = "#dc2626"

    def draw_bar(x, y, w, h, color, label, count):
        rect = plt.Rectangle((x, y), w, h, facecolor=color, edgecolor="white", linewidth=1, alpha=0.85)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, f"{label}\n{count}", ha="center", va="center",
                fontsize=7, fontweight="bold", color="white")

    bar_w = 1.8

    # Stage 1: Total
    draw_bar(stage_x[0], bar_y, bar_w, bar_h, c_total, "TOTAL", total)

    # Stage 2: Resolved / Pending split
    r_frac = resolved / total if total > 0 else 0.5
    p_frac = 1 - r_frac
    r_h = bar_h * r_frac
    p_h = bar_h * p_frac
    draw_bar(stage_x[1], bar_y + p_h, bar_w, r_h, c_resolved, "Resolved", resolved)
    draw_bar(stage_x[1], bar_y, bar_w, p_h, c_pending, "Pending", pending)

    # Stage 3: SLA OK / SLA Breach + Escalated
    if resolved > 0:
        sla_breach = max(0, resolved - sla_ok)
        s_frac = sla_ok / resolved if resolved > 0 else 0.5
        b_frac = 1 - s_frac
        # within the resolved height
        s_h = r_h * s_frac
        b_h = r_h * b_frac
        draw_bar(stage_x[2], bar_y + p_h + b_h, bar_w, s_h, c_sla, "SLA OK", sla_ok)
        if sla_breach > 0:
            draw_bar(stage_x[2], bar_y + p_h, bar_w, b_h, c_breach, "SLA Breach", sla_breach)

    # Escalated indicator
    if escalated > 0:
        e_h = min(0.5, bar_h * 0.15)
        draw_bar(stage_x[2], bar_y - 0.05 - e_h, bar_w, e_h, c_escalated, f"Escalated: {escalated}", "")
        ax.text(stage_x[2] + bar_w / 2, bar_y - 0.05 - e_h / 2, f"Escalated: {escalated}",
                ha="center", va="center", fontsize=6.5, fontweight="bold", color="white")

    # Flow arrows
    for i in range(len(stage_x) - 1):
        ax.annotate("", xy=(stage_x[i + 1] - 0.05, bar_y + bar_h / 2),
                     xytext=(stage_x[i] + bar_w + 0.05, bar_y + bar_h / 2),
                     arrowprops=dict(arrowstyle="->", color="#6b7280", lw=1.5))

    ax.set_title(title, fontsize=9, pad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_zone_ward_heatmap_png(
    zone_names: list[str],
    metric_values: list[list[float]],
    metric_labels: list[str],
    *,
    title: str = "Zone Performance Comparison",
    figsize: tuple[float, float] = (7.5, 3.5),
    dpi: int = 200,
) -> bytes | None:
    """
    Zone × Metric heatmap comparing zones side by side.
    metric_values: rows = zones, cols = metrics.
    Insight: quickly identify geographic performance gaps.
    """
    if not zone_names or not metric_values:
        return None
    import numpy as np

    data = np.array(metric_values, dtype=float)
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")

    cmap = plt.cm.RdYlGn
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=max(1.0, float(data.max())))

    ax.set_xticks(range(len(metric_labels)))
    ax.set_xticklabels(metric_labels, fontsize=7, rotation=25, ha="right")
    ax.set_yticks(range(len(zone_names)))
    ax.set_yticklabels([n[:24] for n in zone_names], fontsize=7)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            fmt = f"{val:.1f}" if val >= 10 else f"{val:.2f}"
            color = "white" if val < data.mean() * 0.5 else "black"
            ax.text(j, i, fmt, ha="center", va="center", fontsize=6, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.04)
    cbar.ax.tick_params(labelsize=6)
    ax.set_title(title, fontsize=9, pad=8)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.12, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
