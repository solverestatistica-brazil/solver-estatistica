# Solver Estatística Experimental

Projeto inicial para um site de estatística experimental com:

- **Frontend estático** em HTML/CSS/JS para GitHub Pages.
- **Backend FastAPI** para Render gratuito.
- ANOVA para **DIC, DBC e DQL**.
- Análise de **fatorial**, **parcelas subdivididas** e **regressão**.
- Testes de médias: Tukey, Duncan, Dunnett, SNK e Scheffé.
- Upload CSV/XLSX, entrada manual, dashboard visual e exportações PDF/Excel/PNG/PDF.

> Importante: este é um candidato técnico à versão 1.0. Antes de uso como laudo oficial, conclua a [matriz de validação científica](docs/VALIDATION_MATRIX.md) e a [checklist de release](docs/RELEASE_CHECKLIST.md) com o responsável técnico.

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

### Testes

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v
```

O workflow `.github/workflows/backend-tests.yml` roda a suíte com cobertura, valida a sintaxe do frontend e também dispara quando o exemplo oficial ou seu carregamento são alterados.

## Limites operacionais

- até 5 MB por requisição/arquivo;
- até 10.000 linhas por análise;
- até 2 análises pesadas simultâneas por instância, configurável por ambiente;
- endpoint de produção fixo no frontend, evitando envio acidental a um destino arbitrário.

## Segurança, privacidade e release

- [Política de segurança](SECURITY.md)
- [Matriz de validação científica](docs/VALIDATION_MATRIX.md)
- [Checklist para a versão 1.0](docs/RELEASE_CHECKLIST.md)
- [Evidência e roteiro de validação independente](docs/VALIDACAO_INDEPENDENTE.md)
- [Operação premium, SLO, carga e rollback](docs/OPERACAO_PREMIUM.md)
- Os textos de Privacidade e Termos publicados no frontend são minutas e exigem revisão legal antes da versão 1.0.
- O codigo esta licenciado sob MIT; consulte [LICENSE](LICENSE).

## Deploy rápido

Leia o passo a passo completo em [`TUTORIAL_GITHUB_RENDER.md`](TUTORIAL_GITHUB_RENDER.md).
