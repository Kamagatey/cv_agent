"""
config.py — Configuration centralisée de l'agent CV.
Modifier ce fichier pour changer le modèle, les chemins, etc.
"""

import os
from pathlib import Path

# ── Chemins ────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
OUTPUTS_DIR   = BASE_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"

CV_BASE_PDF    = DATA_DIR / "mon_cv_base.pdf"
PROFIL_JSON    = DATA_DIR / "profil_base.json"
CV_TEMPLATE    = TEMPLATES_DIR / "cv_template.html"

# Créer les dossiers si absents
DATA_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# ── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

# Paramètres de génération
LLM_OPTIONS = {
    "temperature": 0.3,   # Bas = plus cohérent/factuel pour le CV
    "top_p": 0.9,
    "num_ctx": 8192,      # Fenêtre de contexte
}

# ── Prompts ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT_ANALYSE = """Tu es un expert en recrutement et en rédaction de CV.
Tu analyses des offres d'emploi et des profils de candidats pour créer des CVs
parfaitement ciblés. Tu réponds UNIQUEMENT en JSON valide, sans markdown,
sans texte avant ou après le JSON."""

SYSTEM_PROMPT_EXTRACTION = """Tu es un expert en extraction d'informations depuis des CVs.
Tu extrais les informations structurées d'un CV et les formates en JSON.
Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou après."""
