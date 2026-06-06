"""
agent.py — Adaptation du CV en UN SEUL appel LLM (version optimisée).

Au lieu de deux appels séquentiels :
  1. analyse_offre()   → ~60-90s
  2. adapter_cv()      → ~90-120s

On fait tout en un seul prompt structuré :
  adapter()            → ~80-110s  (gain ~40-60%)

Le LLM fait le même raisonnement en interne, mais on évite :
  - le rechargement du contexte entre deux appels
  - la sérialisation/désérialisation intermédiaire
  - la latence supplémentaire vers Ollama
"""

import json
import re

import ollama as ol
from config import OLLAMA_MODEL, LLM_OPTIONS


# ── Prompt système ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un expert en recrutement et en rédaction de CV.
Tu analyses des offres d'emploi et adaptes des profils de candidats pour créer
des CVs parfaitement ciblés et percutants.
Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou après."""


# ── Prompt unique fusionné ────────────────────────────────────────────────────

PROMPT_FUSIONNE = """\
Tu reçois une offre d'emploi et le profil complet d'un candidat.
Tu dois en UNE SEULE réponse JSON :
  1. Analyser l'offre (extraire les informations clés)
  2. Produire un CV ciblé et adapté à cette offre

RÈGLES IMPORTANTES pour l'adaptation du CV :
- Ne JAMAIS inventer d'expériences, compétences ou diplômes absents du profil
- Reformuler les missions pour matcher les mots-clés de l'offre (sans mentir)
- Mettre en avant les expériences et projets les plus pertinents EN PREMIER
- Adapter le titre professionnel et le résumé à l'offre
- Sélectionner uniquement les compétences pertinentes (max 20 items au total)
- Garder les 2-3 expériences les plus récentes ou pertinentes
- Résumé percutant et ciblé (3-4 phrases max)

═══════════════════════════════
OFFRE D'EMPLOI :
{offre}

═══════════════════════════════
PROFIL DU CANDIDAT :
{profil}

═══════════════════════════════
Retourne UNIQUEMENT ce JSON (sans markdown) :
{{
  "analyse": {{
    "poste": "",
    "entreprise": "",
    "secteur": "",
    "type_contrat": "CDI|CDD|Stage|Alternance|Freelance",
    "competences_requises": [],
    "competences_souhaitees": [],
    "technologies": [],
    "experience_requise": "",
    "missions_principales": [],
    "mots_cles": [],
    "soft_skills": [],
    "langue_travail": "français|anglais|bilingue"
  }},
  "cv": {{
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
    "centres_interet": [],
    "score_match": 0,
    "points_forts": [],
    "points_faibles": [],
    "conseils": []
  }}
}}

score_match : entier 0-100 estimant l'adéquation profil/offre.
points_forts : 3 raisons pour lesquelles ce profil colle à l'offre.
points_faibles : 2 points absents ou insuffisants dans le profil.
conseils : 2-3 conseils pratiques (lettre de motivation, entretien…).
"""


# ── Fonction principale ───────────────────────────────────────────────────────

def adapter(texte_offre: str, profil: dict, progress_cb=None) -> dict:
    """
    Pipeline complet en UN SEUL appel LLM : offre + profil → CV adapté.

    Args:
        texte_offre : texte brut de l'offre d'emploi
        profil      : dict du profil (depuis profil_base.json)
        progress_cb : callable(etape: str) pour feedback Streamlit

    Returns:
        dict avec clés "cv" et "analyse"
    """
    if progress_cb:
        progress_cb("Analyse de l'offre et adaptation du CV en cours…")

    prompt = PROMPT_FUSIONNE.format(
        offre=texte_offre.strip(),
        profil=json.dumps(profil, ensure_ascii=False, indent=2),
    )

    response = ol.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        options={
            **LLM_OPTIONS,
            "num_ctx": 6000,   # réduit de 8192 → gain mémoire et vitesse
        },
    )

    raw = _clean_json(response["message"]["content"])

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Le LLM n'a pas retourné un JSON valide : {e}\n\n"
            f"Début de la réponse brute :\n{raw[:600]}"
        )

    # Vérification structure minimale
    if "cv" not in result or "analyse" not in result:
        raise ValueError(
            f"Structure JSON inattendue — clés présentes : {list(result.keys())}"
        )

    poste    = result["analyse"].get("poste", "?")
    contrat  = result["analyse"].get("type_contrat", "?")
    score    = result["cv"].get("score_match", "?")

    if progress_cb:
        progress_cb(f"✓ Poste : {poste} ({contrat}) — Score match : {score}/100")

    return result


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Nettoie la réponse LLM pour obtenir un JSON parseable."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # Extraire le premier objet JSON valide si du texte parasite précède
    match = re.search(r"\{[\s\S]*\}", raw)
    return match.group(0) if match else raw


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