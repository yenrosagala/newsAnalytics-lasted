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

from app.core.theme import CHART_LAYOUT, TIER_COLORS, MUTED


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
            by_depth_causes.setdefault(n["depth"], []).append(n)

    for n in nodes:
        depth = n["depth"]
        y = -depth * 2.2
        if n["type"] in ("phenomenon", "investigation"):
            positions[n["id"]] = (0.0, y)
        else:
            # Penyebab disebar kiri-kanan di bawah levelnya. Urutan disebar
            # berdasarkan skor keyakinan: yang paling tinggi diletakkan paling
            # dekat ke spine tengah, jadi jarak dari garis tengah = peringkat
            # keyakinan -- posisi node kini punya makna, bukan urutan acak.
            siblings = sorted(
                by_depth_causes.get(depth, []),
                key=lambda m: -(m.get("confidence") or 0),
            )
            rank = next(i for i, m in enumerate(siblings) if m["id"] == n["id"])
            dist = 0.9 + 1.6 * (rank // 2)
            side = 1 if rank % 2 == 0 else -1
            positions[n["id"]] = (side * dist, y - 0.9)

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
        "Tinggi": {"x": [], "y": [], "text": [], "hover": [], "size": []},
        "Sedang": {"x": [], "y": [], "text": [], "hover": [], "size": []},
        "Rendah": {"x": [], "y": [], "text": [], "hover": [], "size": []},
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
            conf = n.get("confidence") or 0
            g = groups[tier]
            g["x"].append(x); g["y"].append(y)
            # Label + skor keyakinan langsung di node (bukan cuma di hover),
            # dan ukuran node ikut skor -> kekuatan bukti terbaca sekilas.
            badge = "🎯 " if n.get("is_root_cause") else ""
            g["text"].append(f"{badge}{_truncate(n['label'], 22)}<br><b>{conf}%</b>")
            g["size"].append(min(16 + 0.14 * conf, 32))
            rationale = n.get("rationale") or "-"
            g["hover"].append(
                f"<b>{n['label']}</b><br>Keyakinan: {conf}% ({tier})<br>Dasar: {rationale}"
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
            marker=dict(size=g["size"], color=TIER_COLORS[tier], line=dict(width=1.5, color="white")),
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

    # Topik tiap level ditulis di samping node level (bukan cuma di hover),
    # supaya alur investigasi bisa dibaca tanpa menyentuh grafik.
    topic_x, topic_y, topic_text = [], [], []
    for n in nodes:
        if n["type"] != "investigation":
            continue
        x, y = positions[n["id"]]
        topic_x.append(x + 0.6)
        topic_y.append(y)
        topic_text.append(_truncate(n.get("label", ""), 40))
    if topic_x:
        fig.add_trace(go.Scatter(
            x=topic_x, y=topic_y, mode="text", text=topic_text,
            textposition="middle left", textfont=dict(size=10, color=MUTED),
            hoverinfo="skip", showlegend=False,
        ))

    max_abs_x = max((abs(px) for px, _ in positions.values()), default=1.6)
    fig.update_layout(
        title="Evidence Graph — Peta Bukti & Alur Investigasi",
        # Beri ruang ekstra di kanan untuk label topik level (text tidak ikut
        # autorange Plotly, jadi tanpa ini labelnya terpotong).
        xaxis=dict(visible=False, range=[-(max_abs_x + 2.5), max_abs_x + 11]),
        yaxis=dict(visible=False),
        height=max(420, 260 * (max((n["depth"] for n in nodes), default=1) + 1)),
        hovermode="closest",
        **CHART_LAYOUT,
    )
    return fig


def build_root_cause_ranking_fig(graph_data: Dict, top_n: int = 12):
    """Bar chart peringkat penyebab menurut skor keyakinan (tertinggi di atas),
    diwarnai per tier. Melengkapi diagram node-link -- angka peringkat yang tidak
    kasat mata di graf kini terbaca langsung. None kalau tidak ada penyebab."""
    import plotly.graph_objects as go

    causes = [n for n in (graph_data.get("nodes") or []) if n.get("type") == "cause"]
    if not causes:
        return None
    causes = sorted(causes, key=lambda n: -(n.get("confidence") or 0))[:top_n]

    # Bar horizontal: urutan dibalik agar skor tertinggi muncul di paling atas.
    causes.reverse()
    labels = [
        ("🎯 " if n.get("is_root_cause") else "") + _truncate(n.get("label", ""), 48)
        for n in causes
    ]
    values = [n.get("confidence") or 0 for n in causes]
    colors = [TIER_COLORS.get(n.get("tier", "Rendah"), MUTED) for n in causes]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=colors),
        text=[f"{v}%" for v in values], textposition="outside",
        hovertext=[
            f"{n.get('tier', '-')} · L{n.get('depth', '-')}<br>{n.get('rationale') or '-'}"
            for n in causes
        ],
        hoverinfo="text+x",
    ))
    fig.update_layout(
        title="Peringkat Penyebab menurut Skor Keyakinan",
        xaxis=dict(title="Skor keyakinan (%)", range=[0, 108]),
        yaxis=dict(title=""),
        height=max(280, 34 * len(values) + 96),
        **CHART_LAYOUT,
    )
    return fig
