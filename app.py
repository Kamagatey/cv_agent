"""
app.py — Interface Streamlit de l'agent CV.

Onglets :
  1. 🏠 Accueil        — statut Ollama, instructions
  2. 👤 Mon profil     — importer CVs PDF, construire/éditer profil_base.json
  3. 📝 Adapter mon CV — coller offre, générer CV adapté, télécharger PDF
  4. 📂 Historique     — CVs générés précédemment
"""

import json
import tempfile
import time
from pathlib import Path

import streamlit as st

from config import PROFIL_JSON, OUTPUTS_DIR, OLLAMA_MODEL
from agent import check_ollama, adapter
from cv_parser import build_profil, load_profil, extract_text
from cv_generator import generate_pdf_bytes


# ── Configuration page ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="CV Agent",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS global ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Réduction padding top */
.block-container { padding-top: 1.5rem; }

/* Badge score */
.score-badge {
    display: inline-block;
    font-size: 2rem;
    font-weight: 700;
    padding: 8px 20px;
    border-radius: 12px;
    color: white;
}
.score-high   { background: #1e7e34; }
.score-medium { background: #e6a817; }
.score-low    { background: #c0392b; }

/* Card info */
.info-card {
    background: #f8fafc;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_ollama_status():
    return check_ollama()


def score_color(score: int) -> str:
    if score >= 70:
        return "score-high"
    if score >= 45:
        return "score-medium"
    return "score-low"


def format_competences(comp: dict) -> str:
    """Résumé lisible des compétences pour affichage."""
    parts = []
    labels = {
        "langages": "Langages", "frameworks": "Frameworks",
        "outils": "Outils", "bases_de_donnees": "BDD",
        "cloud": "Cloud", "methodologies": "Méthodo.", "autres": "Autres",
    }
    for key, label in labels.items():
        items = comp.get(key, [])
        if items:
            parts.append(f"**{label}** : {', '.join(items)}")
    return "\n\n".join(parts)


# ════════════════════════════════════════════════════════════════════════════
# Header
# ════════════════════════════════════════════════════════════════════════════

st.title("📄 CV Agent")
st.caption(f"Propulsé par Ollama · modèle : `{OLLAMA_MODEL}`")

# Statut Ollama dans le header
ollama_ok, ollama_msg = get_ollama_status()
if ollama_ok:
    st.success(ollama_msg, icon="✅")
else:
    st.error(ollama_msg, icon="❌")

st.divider()

# ════════════════════════════════════════════════════════════════════════════
# Onglets
# ════════════════════════════════════════════════════════════════════════════

tab_accueil, tab_profil, tab_adapter, tab_historique = st.tabs([
    "🏠 Accueil",
    "👤 Mon profil",
    "📝 Adapter mon CV",
    "📂 Historique",
])


# ────────────────────────────────────────────────────────────────────────────
# Onglet 1 : Accueil
# ────────────────────────────────────────────────────────────────────────────

with tab_accueil:
    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.subheader("Comment ça marche ?")
        st.markdown("""
**Étape 1 — Construis ton profil** (onglet *Mon profil*)
- Upload 1 à 3 CVs PDF existants
- L'agent extrait automatiquement toutes tes informations
- Le profil complet est sauvegardé dans `profil_base.json`

**Étape 2 — Adapte ton CV** (onglet *Adapter mon CV*)
- Colle le texte d'une offre d'emploi
- L'agent analyse l'offre et adapte ton CV en conséquence
- Télécharge le PDF généré

**Étape 3 — Répète**
- Chaque offre génère un CV unique et ciblé
- Ton profil de base n'est jamais modifié
        """)

    with col2:
        st.subheader("Statut du système")

        profil_existe = PROFIL_JSON.exists()
        cvs_generes = list(OUTPUTS_DIR.glob("*.pdf"))

        st.metric("Profil", "✅ Prêt" if profil_existe else "⚠️ À créer")
        st.metric("CVs générés", len(cvs_generes))
        st.metric("Modèle LLM", OLLAMA_MODEL)

        if profil_existe:
            try:
                profil = load_profil()
                id_ = profil.get("identite", {})
                nom_complet = f"{id_.get('prenom', '')} {id_.get('nom', '')}".strip()
                if nom_complet:
                    st.info(f"Profil chargé : **{nom_complet}**")
                nb_exp = len(profil.get("experiences", []))
                nb_proj = len(profil.get("projets", []))
                nb_certif = len(profil.get("certifications", []))
                st.caption(f"{nb_exp} expérience(s) · {nb_proj} projet(s) · {nb_certif} certification(s)")
            except Exception:
                pass
        else:
            st.warning("Aucun profil trouvé. Va dans **Mon profil** pour commencer.")


# ────────────────────────────────────────────────────────────────────────────
# Onglet 2 : Mon profil
# ────────────────────────────────────────────────────────────────────────────

with tab_profil:
    st.subheader("Construire mon profil depuis mes CVs")

    # ── Upload PDFs
    uploaded_files = st.file_uploader(
        "Upload tes CVs PDF (1 à 3 fichiers)",
        type=["pdf"],
        accept_multiple_files=True,
        help="Tes CVs seront analysés et fusionnés en un profil complet.",
    )

    if uploaded_files:
        if st.button("🔍 Analyser et construire le profil", type="primary", use_container_width=True):
            if not ollama_ok:
                st.error("Ollama n'est pas accessible. Vérifie qu'il est lancé (`ollama serve`).")
            else:
                # Sauvegarder les fichiers dans un dossier temp
                tmp_paths = []
                with tempfile.TemporaryDirectory() as tmpdir:
                    for f in uploaded_files:
                        tmp_path = Path(tmpdir) / f.name
                        tmp_path.write_bytes(f.read())
                        tmp_paths.append(tmp_path)

                    progress_bar = st.progress(0, text="Initialisation…")
                    status_text  = st.empty()
                    total = len(tmp_paths)

                    def progress_cb(step, total, message):
                        pct = int((step / max(total, 1)) * 100)
                        progress_bar.progress(pct, text=message)
                        status_text.info(message)

                    try:
                        with st.spinner("Analyse en cours…"):
                            profil = build_profil(tmp_paths, save=True, progress_cb=progress_cb)

                        progress_bar.progress(100, text="Profil construit ✓")
                        st.success("✅ Profil construit et sauvegardé dans `data/profil_base.json`")
                        st.balloons()

                        # Affichage du résumé
                        id_ = profil.get("identite", {})
                        st.markdown(f"### {id_.get('prenom', '')} {id_.get('nom', '')}")
                        st.caption(id_.get("titre", ""))

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Expériences", len(profil.get("experiences", [])))
                        c2.metric("Formations",  len(profil.get("formations", [])))
                        c3.metric("Projets",     len(profil.get("projets", [])))
                        c4.metric("Certifications", len(profil.get("certifications", [])))

                    except Exception as e:
                        st.error(f"Erreur lors de l'analyse : {e}")

    st.divider()

    # ── Afficher / éditer profil_base.json
    st.subheader("Profil actuel")

    if PROFIL_JSON.exists():
        try:
            profil = load_profil()

            # Tabs internes pour explorer le profil
            sub_id, sub_exp, sub_form, sub_proj, sub_comp, sub_json = st.tabs([
                "Identité", "Expériences", "Formations", "Projets", "Compétences", "JSON brut"
            ])

            with sub_id:
                id_ = profil.get("identite", {})
                for k, v in id_.items():
                    if v:
                        st.write(f"**{k.capitalize()}** : {v}")
                if profil.get("resume"):
                    st.markdown("---")
                    st.markdown("**Résumé**")
                    st.info(profil["resume"])

            with sub_exp:
                exps = profil.get("experiences", [])
                if not exps:
                    st.info("Aucune expérience dans le profil.")
                for exp in exps:
                    with st.expander(f"**{exp.get('poste', '?')}** — {exp.get('entreprise', '?')} ({exp.get('date_debut', '')} – {exp.get('date_fin', '')})"):
                        if exp.get("missions"):
                            st.markdown("**Missions :**")
                            for m in exp["missions"]:
                                st.markdown(f"- {m}")
                        if exp.get("technologies"):
                            st.markdown(f"**Technologies :** {', '.join(exp['technologies'])}")

            with sub_form:
                forms = profil.get("formations", [])
                if not forms:
                    st.info("Aucune formation dans le profil.")
                for f in forms:
                    with st.expander(f"**{f.get('diplome', '?')}** — {f.get('etablissement', '?')}"):
                        st.write(f"Période : {f.get('date_debut', '')} – {f.get('date_fin', '')}")
                        if f.get("mention"):
                            st.write(f"Mention : {f['mention']}")

            with sub_proj:
                projs = profil.get("projets", [])
                if not projs:
                    st.info("Aucun projet dans le profil.")
                for p in projs:
                    with st.expander(f"**{p.get('nom', '?')}**"):
                        if p.get("description"):
                            st.write(p["description"])
                        if p.get("technologies"):
                            st.markdown(f"**Techno :** {', '.join(p['technologies'])}")
                        if p.get("lien"):
                            st.markdown(f"**Lien :** {p['lien']}")

            with sub_comp:
                comp = profil.get("competences", {})
                if comp:
                    st.markdown(format_competences(comp))

            with sub_json:
                st.markdown("**Édition directe du JSON** (sauvegarde manuelle)")
                json_str = st.text_area(
                    "profil_base.json",
                    value=json.dumps(profil, ensure_ascii=False, indent=2),
                    height=450,
                    label_visibility="collapsed",
                )
                if st.button("💾 Sauvegarder les modifications JSON"):
                    try:
                        new_profil = json.loads(json_str)
                        PROFIL_JSON.write_text(
                            json.dumps(new_profil, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        st.success("Profil sauvegardé ✓")
                    except json.JSONDecodeError as e:
                        st.error(f"JSON invalide : {e}")

        except Exception as e:
            st.error(f"Erreur de chargement du profil : {e}")
    else:
        st.info("Aucun profil trouvé. Upload tes CVs ci-dessus pour créer ton profil.")


# ────────────────────────────────────────────────────────────────────────────
# Onglet 3 : Adapter mon CV
# ────────────────────────────────────────────────────────────────────────────

with tab_adapter:
    st.subheader("Adapter mon CV à une offre")

    if not PROFIL_JSON.exists():
        st.warning("⚠️ Aucun profil trouvé. Va dans **Mon profil** pour créer ton profil d'abord.")
        st.stop()

    # ── Saisie de l'offre
    col_offre, col_options = st.columns([2, 1])

    with col_offre:
        offre_texte = st.text_area(
            "Colle ici le texte de l'offre d'emploi",
            height=280,
            placeholder="Titre du poste, description des missions, compétences requises, informations sur l'entreprise…\n\nPlus l'offre est complète, mieux le CV sera adapté.",
        )

    with col_options:
        st.markdown("**Options**")
        st.caption("Modèle utilisé")
        st.code(OLLAMA_MODEL)
        st.caption("Le score de match indique l'adéquation de ton profil avec l'offre (0–100).")
        st.caption("Les points forts et faibles t'aident à préparer ta lettre de motivation.")

    # ── Bouton génération
    if st.button("🚀 Générer le CV adapté", type="primary", use_container_width=True, disabled=not offre_texte.strip()):

        if not ollama_ok:
            st.error("Ollama n'est pas accessible.")
        elif not offre_texte.strip():
            st.warning("Colle une offre d'emploi avant de lancer.")
        else:
            try:
                profil = load_profil()
            except FileNotFoundError as e:
                st.error(str(e))
                st.stop()

            # ── Barre de progression
            status = st.empty()
            progress = st.progress(0, text="Démarrage…")

            steps = []
            def progress_cb(message: str):
                steps.append(message)
                progress.progress(min(len(steps) * 33, 99), text=message)
                status.info(message)

            try:
                result = adapter(offre_texte, profil, progress_cb=progress_cb)
                progress.progress(100, text="CV généré ✓")
                status.success("✅ CV adapté généré avec succès !")

                cv      = result["cv"]
                analyse = result["analyse"]

                st.divider()

                # ── Score et infos offre
                score = cv.get("score_match", 0)
                poste = analyse.get("poste", "?")
                entreprise = analyse.get("entreprise", "")
                contrat = analyse.get("type_contrat", "")

                hcol1, hcol2 = st.columns([1, 3])

                with hcol1:
                    st.markdown(
                        f'<div class="score-badge {score_color(score)}">{score}/100</div>',
                        unsafe_allow_html=True,
                    )
                    st.caption("Score de match")

                with hcol2:
                    st.markdown(f"### {poste}")
                    if entreprise:
                        st.caption(f"{entreprise}  ·  {contrat}")

                # ── Points forts / faibles / conseils
                pf_col, pp_col, cons_col = st.columns(3)

                with pf_col:
                    st.markdown("**✅ Points forts**")
                    for pt in cv.get("points_forts", []):
                        st.markdown(f"- {pt}")

                with pp_col:
                    st.markdown("**⚠️ Points faibles**")
                    for pt in cv.get("points_faibles", []):
                        st.markdown(f"- {pt}")

                with cons_col:
                    st.markdown("**💡 Conseils**")
                    for c in cv.get("conseils", []):
                        st.markdown(f"- {c}")

                st.divider()

                # ── Génération PDF
                with st.spinner("Génération du PDF…"):
                    try:
                        pdf_bytes = generate_pdf_bytes(cv)
                        nom = cv.get("identite", {}).get("nom", "cv").lower().replace(" ", "_")
                        poste_slug = poste.lower().replace(" ", "_")[:25]
                        filename = f"cv_{nom}_{poste_slug}.pdf"

                        st.download_button(
                            label="⬇️ Télécharger le CV PDF",
                            data=pdf_bytes,
                            file_name=filename,
                            mime="application/pdf",
                            use_container_width=True,
                        )
                        st.success(f"PDF prêt : `{filename}`")

                    except Exception as e:
                        st.error(f"Erreur génération PDF : {e}")
                        st.info("Le CV JSON est disponible ci-dessous pour débogage.")

                # ── Aperçu du CV adapté
                with st.expander("👁️ Aperçu du CV adapté (JSON)"):
                    # Masquer les champs meta
                    cv_display = {k: v for k, v in cv.items()
                                  if k not in ("score_match", "points_forts", "points_faibles", "conseils")}
                    st.json(cv_display)

                # ── Aperçu analyse offre
                with st.expander("🔍 Analyse de l'offre"):
                    st.json(analyse)

            except Exception as e:
                progress.empty()
                st.error(f"Erreur lors de l'adaptation : {e}")
                st.exception(e)


# ────────────────────────────────────────────────────────────────────────────
# Onglet 4 : Historique
# ────────────────────────────────────────────────────────────────────────────

with tab_historique:
    st.subheader("CVs générés")

    pdf_files = sorted(OUTPUTS_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not pdf_files:
        st.info("Aucun CV généré pour l'instant. Lance une adaptation dans l'onglet **Adapter mon CV**.")
    else:
        st.caption(f"{len(pdf_files)} CV(s) dans `outputs/`")

        for pdf_path in pdf_files:
            col_name, col_date, col_dl = st.columns([3, 2, 1])
            stat = pdf_path.stat()
            size_kb = round(stat.st_size / 1024, 1)
            mtime = time.strftime("%d/%m/%Y %H:%M", time.localtime(stat.st_mtime))

            col_name.markdown(f"📄 `{pdf_path.name}`")
            col_date.caption(f"{mtime} · {size_kb} Ko")

            with open(pdf_path, "rb") as f:
                col_dl.download_button(
                    "⬇️",
                    data=f.read(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                    key=f"dl_{pdf_path.name}",
                )

    if pdf_files:
        st.divider()
        if st.button("🗑️ Vider l'historique", type="secondary"):
            for f in pdf_files:
                f.unlink()
            st.success("Historique vidé.")
            st.rerun()
