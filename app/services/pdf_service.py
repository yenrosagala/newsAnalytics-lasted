import io
from datetime import datetime
from typing import List, Optional, Tuple
from fpdf import FPDF
import matplotlib.pyplot as plt
import seaborn as sns


def fig_to_png_buffer(fig, width: int = 900, height: int = 600, scale: int = 2) -> Optional[io.BytesIO]:
    """Render a Plotly Figure to a PNG image buffer via kaleido, for embedding
    in the PDF report (fpdf2 can't render Plotly figures directly -- they
    need to be rasterized first, same trick already used for the Matplotlib
    charts elsewhere in this module).

    Returns None if `fig` is None or rendering fails (e.g. kaleido missing),
    so callers can just skip that section instead of breaking the whole PDF.
    """
    if fig is None:
        return None
    try:
        png_bytes = fig.to_image(format="png", width=width, height=height, scale=scale)
        buf = io.BytesIO(png_bytes)
        buf.seek(0)
        return buf
    except Exception:
        return None


def clean_text(text):
    """Fungsi helper untuk membersihkan karakter non-ASCII/Unicode yang tidak didukung Helvetica"""
    if not isinstance(text, str):
        return str(text)
    # Ganti tanda kutip miring/unik dengan tanda kutip biasa, lalu hapus karakter non-ASCII lainnya
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return text.encode('ascii', 'ignore').decode('ascii')


def generate_pdf_report(
    filtered_df, insights, target_keyword, date_range_str, t_media_str, brief,
    extra_graphs: Optional[List[Tuple[str, io.BytesIO]]] = None,
):
    """
    Fungsi utilitas murni untuk membuat file PDF berdasarkan data yang dikirim dari UI.
    Grafik dibuat menggunakan Matplotlib/Seaborn agar tidak ketergantungan pada Chrome/Kaleido.

    `brief`: dict terstruktur Decision Intelligence Executive Brief, hasil dari
    `app.services.decision_brief.parse_decision_brief_json` / `deserialize_brief`,
    dengan keys: title, situation, risks (list of {risk,severity,rationale}),
    impact, recommendations (list of str), bibliography (str).

    `extra_graphs`: daftar opsional (heading, image_buffer) untuk grafik yang
    dirender di luar fungsi ini (mis. Evidence Graph / Peta Aktor / Spatial
    Intelligence dari Plotly, dirasterisasi lewat `fig_to_png_buffer()`).
    Masing-masing ditampilkan full-width satu per halaman/section, setelah
    seksi grafik sentimen/media bawaan.
    """
    # Set style global untuk grafik biar rapi
    plt.style.use('ggplot')
    
    # 1. BIKIN GRAFIK SENTIMEN (Pie Chart)
    img_sentimen_bytes = io.BytesIO()
    if not filtered_df.empty and "Sentimen" in filtered_df.columns:
        sentimen_counts = filtered_df["Sentimen"].value_counts()
        
        fig, ax = plt.subplots(figsize=(5, 4))
        colors = {"Positif": "#4CAF50", "Negatif": "#F44336", "Netral": "#9E9E9E"}
        current_colors = [colors.get(x, "#9E9E9E") for x in sentimen_counts.index]
        
        ax.pie(
            sentimen_counts.values, 
            labels=sentimen_counts.index, 
            autopct='%1.1f%%', 
            startangle=90, 
            colors=current_colors,
            wedgeprops=dict(width=0.4, edgecolor='w')
        )
        ax.set_title("Distribusi Sentimen", fontsize=12, fontweight='bold', pad=10)
        plt.tight_layout()
        plt.savefig(img_sentimen_bytes, format='png', dpi=200)
        plt.close()
        img_sentimen_bytes.seek(0)

    # 2. BIKIN GRAFIK TOP 10 MEDIA (Horizontal Bar Chart)
    img_media_bytes = io.BytesIO()
    if not filtered_df.empty and "media" in filtered_df.columns:
        top_10_m = filtered_df["media"].value_counts().head(10)
        
        fig, ax = plt.subplots(figsize=(6, 4))
        sns.barplot(x=top_10_m.values, y=top_10_m.index, ax=ax, hue=top_10_m.index, palette="Blues_r", legend=False)
        ax.set_title("Top 10 Media Kontributor", fontsize=12, fontweight='bold', pad=10)
        ax.set_xlabel("Jumlah Berita")
        plt.tight_layout()
        plt.savefig(img_media_bytes, format='png', dpi=200)
        plt.close()
        img_media_bytes.seek(0)

    brief = brief or {}
    ai_title = (brief.get("title") or "").strip()
    SEVERITY_RGB = {"Tinggi": (200, 40, 40), "Sedang": (180, 120, 0), "Rendah": (30, 140, 90)}

    # 4. INISIALISASI DOKUMEN FPDF
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=20, top=20, right=20) 
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # --- HEADER LAPORAN ---
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 120, 212) 
    pdf.cell(170, 10, "LAPORAN EXECUTIVE NEWS INTELLIGENCE", align="C", new_x="LMARGIN", new_y="NEXT")
    
      
    # MENAMPILKAN JUDUL UTAMA ANALISIS HASIL AI SECARA DINAMIS
    display_title = ai_title if ai_title else target_keyword
    clean_keyword_title = display_title.replace("**", "").replace(":", "").strip()
    clean_keyword_title = clean_keyword_title.replace("•", "-").replace("·", "-")
    clean_keyword_title = clean_text(clean_keyword_title)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(170, 6, f"{clean_keyword_title}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(170, 6, f"Dibuat secara otomatis pada: {datetime.now().strftime('%d %B %Y, %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


    # Garis Pembatas Utama
    pdf.set_draw_color(0, 120, 212)
    pdf.set_line_width(0.6)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(8)
    
    # --- METADATA ANALISIS ---
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(60, 60, 60)
       
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(40, 6, "Rentang Waktu", border=0)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.cell(130, 6, f": {clean_text(date_range_str)}", border=0, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(40, 6, "Top Media", border=0)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.multi_cell(130, 6, f": {clean_text(t_media_str)}", border=0, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Garis Pembatas Utama
    pdf.set_draw_color(0, 120, 212)
    pdf.set_line_width(0.6)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(8)
    
    # --- SEKSI 1: VISUALISASI GRAFIK ---
    section_num = 0
    has_charts = bool(img_sentimen_bytes.getvalue() or img_media_bytes.getvalue())
    has_insights = bool(insights)

    if has_charts:
        section_num += 1
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 100, 180)
        pdf.cell(170, 8, f"{section_num}. Grafik & Visualisasi Analisis", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        y_pos = pdf.get_y()
        if img_sentimen_bytes.getvalue():
            pdf.image(img_sentimen_bytes, x=20, y=y_pos, w=80)
        if img_media_bytes.getvalue():
            pdf.image(img_media_bytes, x=105, y=y_pos, w=85)
        pdf.set_y(y_pos + 62)
        pdf.ln(4)

    # --- SEKSI: GRAFIK TAMBAHAN (Evidence Graph / Peta Aktor / Spatial Intelligence) ---
    extra_graphs = [(h, b) for h, b in (extra_graphs or []) if b is not None and b.getvalue()]
    if extra_graphs:
        section_num += 1
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 100, 180)
        pdf.cell(170, 8, f"{section_num}. Peta & Grafik Investigasi", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        for heading, img_buf in extra_graphs:
            if pdf.get_y() > 160:
                pdf.add_page()
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(170, 7, clean_text(heading), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            try:
                pdf.image(img_buf, x=20, w=170)
            except Exception:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(150, 60, 60)
                pdf.cell(170, 6, "(Gagal menampilkan grafik ini)", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(6)

    # --- SEKSI: INSIGHTS UTAMA (dilewati kalau tidak ada data artikel, mis. brief-only PDF) ---
    if has_insights:
        section_num += 1
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 100, 180)
        pdf.cell(170, 8, f"{section_num}. Ringkasan Temuan Utama (Insights)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(50, 50, 50)
        pdf.ln(2)
    for insight in insights:
        clean_insight = clean_text(insight)
        clean_insight = clean_insight.replace("•", "-").replace("·", "-")
        pdf.multi_cell(170, 6, f"  - {clean_insight}", new_x="LMARGIN", new_y="NEXT", align="JUSTIFY")
    pdf.ln(6)
    
    # --- SEKSI 3: EXECUTIVE BRIEF (Situation / Risks / Impact / Recommendations) ---
    def _write_paragraphs(text, font_size=11):
        pdf.set_font("Helvetica", "", font_size)
        pdf.set_text_color(40, 40, 40)
        clean_body = clean_text(text.replace("**", ""))
        clean_body = clean_body.replace("•", "-").replace("·", "-")
        for paragraf in [p.strip() for p in clean_body.split("\n") if p.strip()]:
            pdf.multi_cell(170, 6.5, "        " + paragraf, new_x="LMARGIN", new_y="NEXT", align="JUSTIFY")
            pdf.ln(3)

    def _write_subheading(text):
        pdf.set_font("Helvetica", "B", 11.5)
        pdf.set_text_color(0, 100, 180)
        pdf.cell(170, 7, clean_text(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 100, 180)
    section_num += 1
    pdf.cell(170, 8, f"{section_num}. Executive Brief", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    if brief.get("situation"):
        _write_subheading("Situation")
        _write_paragraphs(brief["situation"])

    if brief.get("risks"):
        _write_subheading("Risks")
        pdf.set_font("Helvetica", "", 10.5)
        for r in brief["risks"]:
            severity = r.get("severity", "Sedang")
            rgb = SEVERITY_RGB.get(severity, (80, 80, 80))
            pdf.set_text_color(40, 40, 40)
            line = clean_text(f"- {r.get('risk', '')} ")
            pdf.write(5.6, line)
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*rgb)
            pdf.write(5.6, f"[{severity}]")
            pdf.ln(6)
            pdf.set_font("Helvetica", "", 10.5)
            if r.get("rationale"):
                pdf.set_text_color(110, 110, 110)
                pdf.set_font("Helvetica", "I", 9)
                pdf.multi_cell(170, 5, clean_text(f"  Dasar: {r['rationale']}"), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 10.5)
        pdf.ln(3)

    if brief.get("impact"):
        _write_subheading("Impact")
        _write_paragraphs(brief["impact"])

    if brief.get("recommendations"):
        _write_subheading("Recommendations")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(40, 40, 40)
        for i, rec in enumerate(brief["recommendations"], 1):
            pdf.multi_cell(170, 6, clean_text(f"{i}. {rec}"), new_x="LMARGIN", new_y="NEXT", align="JUSTIFY")
        pdf.ln(3)

    if not any([brief.get("situation"), brief.get("risks"), brief.get("impact"), brief.get("recommendations")]):
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(170, 6, "Executive brief tidak tersedia untuk laporan ini.", new_x="LMARGIN", new_y="NEXT")

    # --- SEKSI 4: DAFTAR PUSTAKA NUMERIK DI HALAMAN AKHIR ---
    if brief.get("bibliography"):
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 100, 180)
        section_num += 1
        pdf.cell(170, 8, f"{section_num}. Daftar Pustaka", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)
        
        clean_refs = brief["bibliography"].replace("**", "")
        clean_refs = clean_text(clean_refs)
        clean_refs = clean_refs.replace("•", "-").replace("·", "-")
        ref_lines = [r.strip() for r in clean_refs.split("\n") if r.strip()]
        
        for line in ref_lines:
            pdf.multi_cell(170, 5.5, line, new_x="LMARGIN", new_y="NEXT", align="JUSTIFY")
            pdf.ln(1)

    # --- FOOTER LAPORAN ---
    if pdf.get_y() > 245:
        pdf.add_page()
        
    pdf.ln(5)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(140, 140, 140)
    teks_footer_1 = "Laporan resmi ini dihasilkan secara otomatis oleh sistem Decision Intelligent."
    teks_footer_2 = "newsinvestigator: Yenro P. Sagala - BPS Provinsi Papua"
    
    pdf.cell(170, 4, teks_footer_1, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(170, 4, teks_footer_2, align="C", new_x="LMARGIN", new_y="NEXT")
    
    # fpdf2's pdf.output() returns a bytearray, not bytes. st.download_button()
    # only accepts str/bytes and raises "RuntimeError: Invalid binary data
    # format: <class 'bytearray'>" otherwise -- which, because every caller of
    # this function wraps its whole UI block in a single try/except, used to
    # surface as a misleading "Gagal memuat riwayat" error far from the real
    # cause. Cast explicitly so downstream consumers always get real bytes.
    return bytes(pdf.output())