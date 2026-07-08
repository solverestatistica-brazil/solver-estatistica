# Solver Estatística Experimental

Projeto inicial para um site de estatística experimental com:

- **Frontend estático** em HTML/CSS/JS para GitHub Pages.
- **Backend FastAPI** para Render gratuito.
- ANOVA para **DIC, DBC e DQL**.
- Análise de **fatorial**, **parcelas subdivididas** e **regressão**.
- Testes de médias: Tukey, Duncan, Dunnett, SNK e Scheffé.
- Upload CSV/XLSX, entrada manual, dashboard visual e exportações PDF/Excel/PNG/PDF.

> Importante: este é um MVP técnico. Antes de usar como laudo oficial, valide as rotinas estatísticas e os modelos com o responsável técnico.

## Estrutura

```txt
solver-estatistica/
├── frontend/                 # Site estático para GitHub Pages
│   ├── index.html
│   └── assets/
├── backend/                  # API FastAPI para Render
│   ├── main.py
│   ├── statistics_engine.py
│   ├── exporters.py
│   └── requirements.txt
├── examples/                 # CSVs de teste
├── docs/                     # Arquitetura e notas técnicas
├── .github/workflows/pages.yml
├── render.yaml
└── TUTORIAL_GITHUB_RENDER.md
```

## Rodar localmente

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

A API fica em `http://127.0.0.1:8000` e a documentação em `http://127.0.0.1:8000/docs`.

### Frontend

Em outro terminal:

```bash
cd frontend
python -m http.server 5500
```

Abra `http://127.0.0.1:5500` e informe `http://127.0.0.1:8000` no campo "URL do backend Render".

## Deploy rápido

Leia o passo a passo completo em [`TUTORIAL_GITHUB_RENDER.md`](TUTORIAL_GITHUB_RENDER.md).
