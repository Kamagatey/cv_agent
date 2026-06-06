"""
cv_parser.py — Extraction et parsing de CVs PDF.

Deux modes :
  1. extract_text(pdf_path)      → texte brut depuis un PDF
  2. build_profil(pdf_paths)     → profil_base.json fusionné depuis 1-N CVs
"""

import json
import re
from pathlib import Path
from typing import Union

import pdfplumber

import ollama as ol
from config import (
    OLLAMA_MODEL,
    PROFIL_JSON,
    SYSTEM_PROMPT_EXTRACTION,
    LLM_OPTIONS,
)


# ── 1. Extraction texte brut ─────────────────────────────────────────────────

def extract_text(pdf_path: Union[str, Path]) -> str:
    """Extrait tout le texte d'un PDF en conservant la structure par pages."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if text and text.strip():
                pages_text.append(f"--- Page {i} ---\n{text.strip()}")

    return "\n\n".join(pages_text)


# ── 2. Extraction structurée via LLM ────────────────────────────────────────

EXTRACTION_PROMPT = """\
Voici le texte brut d'un CV. Extrais toutes les informations et retourne
un objet JSON avec exactement cette structure (laisse vide si absent) :

{{
  "identite": {{
    "nom": "",
    "prenom": "",
    "titre": "",
    "email": "",
    "telephone": "",
    "localisation": "",
    "linkedin": "",
    "github": "",
    "portfolio": ""
  }},
  "resume": "",
  "formations": [
    {{
      "diplome": "",
      "etablissement": "",
      "lieu": "",
      "date_debut": "",
      "date_fin": "",
      "mention": "",
      "details": []
    }}
  ],
  "experiences": [
    {{
      "poste": "",
      "entreprise": "",
      "lieu": "",
      "date_debut": "",
      "date_fin": "",
      "type": "stage|alternance|CDI|CDD|freelance|projet",
      "missions": [],
      "technologies": []
    }}
  ],
  "projets": [
    {{
      "nom": "",
      "description": "",
      "technologies": [],
      "lien": "",
      "date": ""
    }}
  ],
  "competences": {{
    "langages": [],
    "frameworks": [],
    "outils": [],
    "bases_de_donnees": [],
    "cloud": [],
    "methodologies": [],
    "autres": []
  }},
  "certifications": [
    {{
      "nom": "",
      "organisme": "",
      "date": "",
      "lien": ""
    }}
  ],
  "langues": [
    {{
      "langue": "",
      "niveau": ""
    }}
  ],
  "centres_interet": []
}}

Texte du CV :
{cv_text}
"""


def extract_structured(cv_text: str) -> dict:
    """Appelle le LLM pour extraire un dict structuré depuis le texte brut."""
    prompt = EXTRACTION_PROMPT.format(cv_text=cv_text)

    response = ol.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_EXTRACTION},
            {"role": "user",   "content": prompt},
        ],
        options=LLM_OPTIONS,
    )

    raw = response["message"]["content"].strip()

    # Nettoyage robuste : supprimer éventuels backticks markdown
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Le LLM n'a pas retourné un JSON valide : {e}\n\nRéponse brute :\n{raw[:500]}")


# ── 3. Fusion de plusieurs CVs ───────────────────────────────────────────────

def _merge_lists_unique(base: list, new: list) -> list:
    """Fusionne deux listes en évitant les doublons (comparaison insensible à la casse)."""
    if not isinstance(base, list):
        return new or []
    if not isinstance(new, list):
        return base

    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False).lower() for item in base}
    for item in new:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False).lower()
        if key not in seen:
            base.append(item)
            seen.add(key)
    return base


def _merge_competences(base: dict, new: dict) -> dict:
    """Fusionne les compétences en dédupliquant chaque sous-liste."""
    if not isinstance(base, dict):
        return new or {}
    for key, values in (new or {}).items():
        if key in base:
            # Dédupliquer strings insensible à la casse
            existing_lower = {v.lower() for v in base[key] if isinstance(v, str)}
            for v in values:
                if isinstance(v, str) and v.lower() not in existing_lower:
                    base[key].append(v)
                    existing_lower.add(v.lower())
        else:
            base[key] = values
    return base


def merge_profils(profil_a: dict, profil_b: dict) -> dict:
    """Fusionne deux profils extraits en un seul profil complet."""
    merged = json.loads(json.dumps(profil_a))  # deep copy

    # Identité : compléter les champs vides
    for field, value in profil_b.get("identite", {}).items():
        if value and not merged.get("identite", {}).get(field):
            merged.setdefault("identite", {})[field] = value

    # Résumé : garder le plus long
    if len(profil_b.get("resume", "")) > len(merged.get("resume", "")):
        merged["resume"] = profil_b["resume"]

    # Listes à fusionner
    for section in ["formations", "experiences", "projets", "certifications", "langues"]:
        merged[section] = _merge_lists_unique(
            merged.get(section, []),
            profil_b.get(section, []),
        )

    # Compétences (dict de listes)
    merged["competences"] = _merge_competences(
        merged.get("competences", {}),
        profil_b.get("competences", {}),
    )

    # Centres d'intérêt
    existing_ci = {c.lower() for c in merged.get("centres_interet", [])}
    for ci in profil_b.get("centres_interet", []):
        if ci.lower() not in existing_ci:
            merged.setdefault("centres_interet", []).append(ci)
            existing_ci.add(ci.lower())

    return merged


# ── 4. Pipeline principal ────────────────────────────────────────────────────

def build_profil(pdf_paths: list, save: bool = True, progress_cb=None) -> dict:
    """
    Construit profil_base.json depuis une liste de CVs PDF.

    Args:
        pdf_paths   : liste de Path ou str vers les PDFs
        save        : si True, sauvegarde dans PROFIL_JSON
        progress_cb : callable(step: int, total: int, message: str) pour Streamlit

    Returns:
        dict du profil fusionné
    """
    if not pdf_paths:
        raise ValueError("Aucun PDF fourni.")

    total = len(pdf_paths)
    profil_final = None

    for i, pdf_path in enumerate(pdf_paths):
        pdf_path = Path(pdf_path)
        msg = f"Extraction de {pdf_path.name}…"
        if progress_cb:
            progress_cb(i, total, msg)

        # Étape A : texte brut
        text = extract_text(pdf_path)

        # Étape B : structuration LLM
        msg = f"Analyse LLM de {pdf_path.name}…"
        if progress_cb:
            progress_cb(i, total, msg)
        profil = extract_structured(text)

        # Étape C : fusion
        if profil_final is None:
            profil_final = profil
        else:
            profil_final = merge_profils(profil_final, profil)

    if progress_cb:
        progress_cb(total, total, "Profil construit ✓")

    if save and profil_final:
        PROFIL_JSON.write_text(
            json.dumps(profil_final, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return profil_final


def load_profil() -> dict:
    """Charge profil_base.json. Lève FileNotFoundError si absent."""
    if not PROFIL_JSON.exists():
        raise FileNotFoundError(
            f"profil_base.json introuvable dans {PROFIL_JSON.parent}.\n"
            "Lance d'abord l'onglet 'Profil' pour générer ton profil."
        )
    return json.loads(PROFIL_JSON.read_text(encoding="utf-8"))
