"""
agent.py — Logique d'adaptation du CV à une offre d'emploi.

Pipeline :
  1. analyse_offre(texte_offre) → mots-clés, compétences requises
  2. adapter_cv(profil, analyse_offre) → CV ciblé structuré (dict)
  3. adapter(texte_offre, profil) → fonction principale combinée
"""

import json
import re
from typing import Optional

import ollama as ol
from config import OLLAMA_MODEL, SYSTEM_PROMPT_ANALYSE, LLM_OPTIONS


# ── 1. Analyse de l'offre d'emploi ──────────────────────────────────────────

PROMPT_ANALYSE_OFFRE = """\
Analyse cette offre d'emploi et retourne un JSON structuré.

Offre d'emploi :
{offre}

Retourne UNIQUEMENT ce JSON (sans markdown) :
{{
  "poste": "",
  "entreprise": "",
  "secteur": "",
  "type_contrat": "CDI|CDD|Stage|Alternance|Freelance",
  "competences_requises": [],
  "competences_souhaitees": [],
  "technologies": [],
  "experience_requise": "",
  "formation_requise": "",
  "missions_principales": [],
  "mots_cles": [],
  "soft_skills": [],
  "langue_travail": "français|anglais|bilingue"
}}
"""


def analyse_offre(texte_offre: str) -> dict:
    """Extrait les informations clés d'une offre d'emploi."""
    response = ol.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_ANALYSE},
            {"role": "user",   "content": PROMPT_ANALYSE_OFFRE.format(offre=texte_offre)},
        ],
        options=LLM_OPTIONS,
    )
    raw = _clean_json(response["message"]["content"])
    return json.loads(raw)


# ── 2. Adaptation du CV ──────────────────────────────────────────────────────

PROMPT_ADAPTER_CV = """\
Tu dois créer un CV parfaitement adapté à cette offre d'emploi.

PROFIL DU CANDIDAT (toutes ses informations) :
{profil}

ANALYSE DE L'OFFRE :
{analyse}

RÈGLES IMPORTANTES :
- Ne jamais inventer d'expériences, compétences ou diplômes absents du profil
- Reformuler les missions pour matcher les mots-clés de l'offre (sans mentir)
- Mettre en avant les expériences et projets les plus pertinents EN PREMIER
- Adapter le titre professionnel et le résumé à l'offre
- Sélectionner uniquement les compétences pertinentes (max 20)
- Garder les 2-3 expériences les plus récentes ou pertinentes
- Le résumé doit être percutant et ciblé (3-4 phrases max)

Retourne UNIQUEMENT ce JSON (sans markdown) :
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
      "type": "",
      "missions": [],
      "technologies": []
    }}
  ],
  "projets": [
    {{
      "nom": "",
      "description": "",
      "technologies": [],
      "lien": ""
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
  "score_match": 0,
  "points_forts": [],
  "points_faibles": [],
  "conseils": []
}}

Le champ "score_match" est un entier de 0 à 100 estimant l'adéquation profil/offre.
"points_forts" : 3 raisons pour lesquelles ce profil colle à l'offre.
"points_faibles" : 2 points à améliorer ou absents du profil.
"conseils" : 2-3 conseils pour mieux postuler (lettre de motivation, entretien…).
"""


def adapter_cv(profil: dict, analyse: dict) -> dict:
    """Génère un CV adapté à partir du profil et de l'analyse de l'offre."""
    response = ol.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_ANALYSE},
            {
                "role": "user",
                "content": PROMPT_ADAPTER_CV.format(
                    profil=json.dumps(profil, ensure_ascii=False, indent=2),
                    analyse=json.dumps(analyse, ensure_ascii=False, indent=2),
                ),
            },
        ],
        options={**LLM_OPTIONS, "num_ctx": 12000},
    )
    raw = _clean_json(response["message"]["content"])
    return json.loads(raw)


# ── 3. Pipeline principal ────────────────────────────────────────────────────

def adapter(texte_offre: str, profil: dict, progress_cb=None) -> dict:
    """
    Pipeline complet : offre + profil → CV adapté.

    Args:
        texte_offre : texte brut de l'offre d'emploi
        profil      : dict du profil (depuis profil_base.json)
        progress_cb : callable(etape: str) pour feedback Streamlit

    Returns:
        dict contenant :
          - "cv"      : le CV adapté (prêt pour le template)
          - "analyse" : l'analyse de l'offre
    """
    if progress_cb:
        progress_cb("Analyse de l'offre d'emploi…")

    analyse = analyse_offre(texte_offre)

    if progress_cb:
        progress_cb(f"Offre analysée — poste : {analyse.get('poste', '?')} | {analyse.get('type_contrat', '?')}")

    if progress_cb:
        progress_cb("Adaptation du CV en cours…")

    cv_adapte = adapter_cv(profil, analyse)

    if progress_cb:
        progress_cb(f"CV adapté ✓ — Score de match : {cv_adapte.get('score_match', '?')}/100")

    return {"cv": cv_adapte, "analyse": analyse}


# ── Utilitaires ──────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Nettoie la réponse LLM pour obtenir un JSON parseable."""
    raw = raw.strip()
    # Supprimer les blocs markdown
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # Extraire le premier objet JSON valide si du texte parasite précède
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        return match.group(0)
    return raw


def check_ollama() -> tuple[bool, str]:
    try:
        models = ol.list()

        print(models)

        available = []

        for m in models.get("models", []):
            if isinstance(m, dict):
                available.append(
                    m.get("model") or m.get("name") or str(m)
                )
            else:
                available.append(str(m))

        if any(OLLAMA_MODEL.split(":")[0] in m for m in available):
            return True, f"✅ Ollama OK — modèle {OLLAMA_MODEL} disponible"

        return False, (
            f"⚠️ Modèle {OLLAMA_MODEL} non trouvé. "
            f"Disponibles : {', '.join(available)}"
        )

    except Exception as e:
        return False, f"❌ Ollama inaccessible : {e}"
