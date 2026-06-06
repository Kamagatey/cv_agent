# CV Agent — Adaptateur de CV intelligent avec Ollama

Agent local qui adapte automatiquement ton CV à chaque offre d'emploi.

## Stack
- **Ollama** (qwen2.5:14b) — LLM local
- **Streamlit** — interface web
- **pdfplumber** — extraction texte PDF
- **Jinja2 + WeasyPrint** — génération PDF

## Installation

```bash
# 1. Cloner / copier le projet
cd cv_agent

# 2. Installer les dépendances
pip install -r requirements.txt

# 4. Placer ton CV de base dans data/
cp /chemin/vers/ton_cv.pdf data/mon_cv_base.pdf

# 5. Lancer l'app
streamlit run app.py
```

## Structure

```
cv_agent/
├── app.py                  # Interface Streamlit principale
├── cv_parser.py            # Extraction et parsing du CV PDF
├── agent.py                # Logique LLM (Ollama)
├── cv_generator.py         # Rendu HTML → PDF
├── config.py               # Configuration centralisée
├── templates/
│   └── cv_template.html    # Template Jinja2 du CV
├── data/
│   ├── mon_cv_base.pdf     # CV source (à fournir)
│   └── profil_base.json    # Profil complet (généré depuis CV)
├── outputs/                # CVs adaptés générés
└── requirements.txt
```

## Workflow

1. Lance `streamlit run app.py`
2. Colle ou uploade une offre d'emploi
3. L'agent analyse l'offre et adapte ton CV
4. Télécharge le PDF généré

## Premiers pas

Après installation, lance l'onglet **"Profil"** dans l'interface pour
importer tes CVs PDF et générer automatiquement `profil_base.json`.
