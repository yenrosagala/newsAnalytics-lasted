"""
Evidence Graph Renderer
========================
Mengubah struktur node/edge dari `app.services.recursive_engine.build_evidence_graph_data`
menjadi visual Plotly interaktif: rantai investigasi (Level 1 -> 2 -> ... -> N)
di sumbu vertikal, dengan penyebab (evidence) bercabang di setiap level,
diwarnai berdasarkan tier keyakinan (Tinggi/Sedang/Rendah).

Dipakai oleh pages/3_Fenomena.py (AI Investigator).
"""
from typing import Dict

TIER_COLORS = {
    "Tinggi": "#10b981",   # hijau
    "Sedang": "#f59e0b",   # amber
    "Rendah": "#ef4444",   # merah/coral
}

_DARK_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#1a2233",
    title_font_color="#1a2233",
    margin=dict(t=48, b=10, l=10, r=10),
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def _truncate(text: str, max_len: int = 55) -> str:
    text = text or ""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def build_evidence_graph_fig(graph_data: Dict):
    """Mengembalikan objek Plotly Figure, atau None kalau tidak ada data."""
    import plotly.graph_objects as go

    nodes = graph_data.get("nodes") or []
    edges = graph_data.get("edges") or []
    if not nodes:
        return None

    # --- Tata letak manual (tanpa dependency networkx) ---
    # Sumbu Y = depth (investigasi berjajar vertikal, 0 di atas).
    # Sumbu X = 0 untuk node investigasi/fenomena (rantai utama tengah),
    #           node cause disebar ke kiri-kanan node investigasi induknya.
    positions = {}
    by_depth_causes = {}
    for n in nodes:
        if n["type"] == "cause":
            by_depth_causes.setdefault(n["depth"], []).append(n["id"])

    id_to_node = {n["id"]: n for n in nodes}

    for n in nodes:
        depth = n["depth"]
        y = -depth * 2.2
        if n["type"] in ("phenomenon", "investigation"):
            positions[n["id"]] = (0.0, y)
        else:  # cause node: spread horizontally around x=0
            siblings = by_depth_causes.get(depth, [])
            idx = siblings.index(n["id"])
            spread = len(siblings)
            offset = (idx - (spread - 1) / 2) * 1.6
            positions[n["id"]] = (offset if offset != 0 else 1.6, y - 0.9)

    # --- Edge traces (garis) ---
    edge_x, edge_y = [], []
    for e in edges:
        if e["source"] not in positions or e["target"] not in positions:
            continue
        x0, y0 = positions[e["source"]]
        x1, y1 = positions[e["target"]]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(color="rgba(148,163,184,0.45)", width=1.4),
        hoverinfo="none", showlegend=False,
    ))

    # --- Node traces, dikelompokkan per tipe/tier supaya legend rapi ---
    groups = {
        "phenomenon": {"x": [], "y": [], "text": [], "hover": []},
        "investigation": {"x": [], "y": [], "text": [], "hover": []},
        "Tinggi": {"x": [], "y": [], "text": [], "hover": []},
        "Sedang": {"x": [], "y": [], "text": [], "hover": []},
        "Rendah": {"x": [], "y": [], "text": [], "hover": []},
    }
    root_marker = {"x": [], "y": [], "text": [], "hover": []}

    for n in nodes:
        x, y = positions[n["id"]]
        if n["type"] == "phenomenon":
            g = groups["phenomenon"]
            g["x"].append(x); g["y"].append(y)
            g["text"].append("🎯")
            g["hover"].append(f"<b>Fenomena Awal</b><br>{n['label']}")
        elif n["type"] == "investigation":
            g = groups["investigation"]
            g["x"].append(x); g["y"].append(y)
            g["text"].append(f"L{n['depth']}")
            g["hover"].append(f"<b>{n['label']}</b><br>{n.get('articles_found', 0)} artikel dianalisis")
        else:
            tier = n.get("tier", "Rendah")
            g = groups[tier]
            g["x"].append(x); g["y"].append(y)
            g["text"].append(_truncate(n["label"], 28))
            rationale = n.get("rationale") or "-"
            g["hover"].append(
                f"<b>{n['label']}</b><br>Keyakinan: {n.get('confidence', 0)}% ({tier})<br>Dasar: {rationale}"
            )
            if n.get("is_root_cause"):
                root_marker["x"].append(x)
                root_marker["y"].append(y)
                root_marker["text"].append("")
                root_marker["hover"].append("🎯 Akar Masalah Teridentifikasi")

    fig.add_trace(go.Scatter(
        x=groups["phenomenon"]["x"], y=groups["phenomenon"]["y"], mode="markers+text",
        marker=dict(size=42, color="#2563eb", symbol="diamond", line=dict(width=2, color="white")),
        text=groups["phenomenon"]["text"], textposition="middle center",
        hovertext=groups["phenomenon"]["hover"], hoverinfo="text",
        name="Fenomena Awal",
    ))
    fig.add_trace(go.Scatter(
        x=groups["investigation"]["x"], y=groups["investigation"]["y"], mode="markers+text",
        marker=dict(size=38, color="#2563eb", symbol="square", line=dict(width=2, color="white")),
        text=groups["investigation"]["text"], textposition="middle center", textfont=dict(size=10, color="black"),
        hovertext=groups["investigation"]["hover"], hoverinfo="text",
        name="Level Investigasi",
    ))
    for tier in ("Tinggi", "Sedang", "Rendah"):
        g = groups[tier]
        if not g["x"]:
            continue
        fig.add_trace(go.Scatter(
            x=g["x"], y=g["y"], mode="markers+text",
            marker=dict(size=22, color=TIER_COLORS[tier], line=dict(width=1.5, color="white")),
            text=g["text"], textposition="bottom center", textfont=dict(size=9),
            hovertext=g["hover"], hoverinfo="text",
            name=f"Penyebab — Keyakinan {tier}",
        ))

    if root_marker["x"]:
        fig.add_trace(go.Scatter(
            x=root_marker["x"], y=root_marker["y"], mode="markers",
            marker=dict(size=34, color="rgba(0,0,0,0)", line=dict(width=3, color="#2563eb"), symbol="circle-open"),
            hovertext=root_marker["hover"], hoverinfo="text",
            name="🎯 Akar Masalah", showlegend=True,
        ))

    fig.update_layout(
        title="Evidence Graph — Peta Bukti & Alur Investigasi",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=max(420, 260 * (max((n["depth"] for n in nodes), default=1) + 1)),
        hovermode="closest",
        **_DARK_LAYOUT,
    )
    return fig
