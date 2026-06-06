"""
cv_generator.py — Rendu du CV adapté en PDF via Jinja2 + xhtml2pdf.


xhtml2pdf utilise les polices DejaVu embarquées.
"""

import io
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from config import TEMPLATES_DIR, OUTPUTS_DIR, CV_TEMPLATE


# ── Rendu HTML ───────────────────────────────────────────────────────────────

def render_html(cv: dict) -> str:
    """Rend le template Jinja2 avec les données du CV adapté."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    env.filters["nl2br"] = lambda s: s.replace("\n", "<br>") if s else ""
    template = env.get_template(CV_TEMPLATE.name)
    return template.render(cv=cv, now=datetime.now())


# ── Génération PDF ───────────────────────────────────────────────────────────

def generate_pdf(cv: dict, output_path: Path = None) -> Path:
    """
    Génère un fichier PDF depuis un CV adapté.

    Args:
        cv          : dict du CV adapté
        output_path : chemin de sortie (auto-généré si None)

    Returns:
        Path vers le fichier PDF généré
    """
    if output_path is None:
        nom = cv.get("identite", {}).get("nom", "cv").lower().replace(" ", "_")
        poste = cv.get("identite", {}).get("titre", "cv").lower()
        poste = re.sub(r"[^a-z0-9_]", "_", poste)[:30]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUTS_DIR / f"cv_{nom}_{poste}_{timestamp}.pdf"

    pdf_bytes = generate_pdf_bytes(cv)
    output_path.write_bytes(pdf_bytes)
    return output_path


def generate_pdf_bytes(cv: dict) -> bytes:
    """Retourne le PDF en bytes (pour Streamlit download_button)."""
    html_content = render_html(cv)
    buf = io.BytesIO()

    result = pisa.CreatePDF(
        src=html_content,
        dest=buf,
        encoding="utf-8",
    )

    if result.err:
        raise RuntimeError(f"xhtml2pdf : erreur lors de la génération PDF (code {result.err})")

    return buf.getvalue()