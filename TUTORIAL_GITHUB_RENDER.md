# Tutorial completo: GitHub Pages + Render gratuito

Este tutorial publica o **frontend** no GitHub Pages e o **backend FastAPI** no Render.

## 1. Pré-requisitos

Instale:

- Git
- Python 3.12+
- Conta no GitHub
- Conta no Render
- VS Code ou editor de preferência

## 2. Criar o repositório no GitHub

1. Acesse GitHub.
2. Clique em **New repository**.
3. Nome sugerido: `solver-estatistica`.
4. Deixe público, principalmente se usar GitHub Free e quiser GitHub Pages sem restrição.
5. Não precisa criar README no GitHub se você vai subir esta pasta pronta.
6. Clique em **Create repository**.

## 3. Subir o projeto para o GitHub

No terminal, entre na pasta do projeto:

```bash
cd solver-estatistica
```

Inicialize e envie os arquivos:

```bash
git init
git add .
git commit -m "Primeira versão do Solver Estatística"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/solver-estatistica.git
git push -u origin main
```

Troque `SEU_USUARIO` pelo seu usuário real do GitHub.

## 4. Ativar GitHub Pages

Este projeto já inclui o workflow:

```txt
.github/workflows/pages.yml
```

Ele publica automaticamente a pasta `frontend` no GitHub Pages.

No GitHub:

1. Abra o repositório.
2. Vá em **Settings**.
3. Clique em **Pages**.
4. Em **Build and deployment**, selecione **GitHub Actions**.
5. Vá em **Actions** e acompanhe o workflow **Deploy GitHub Pages**.
6. Quando terminar, o site estará em:

```txt
https://SEU_USUARIO.github.io/solver-estatistica/
```

## 5. Testar o backend localmente antes do Render

```bash
cd backend
python -m venv .venv
```

Ative o ambiente:

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Instale dependências:

```bash
pip install -r requirements.txt
```

Rode a API:

```bash
uvicorn main:app --reload
```

Teste no navegador:

```txt
http://127.0.0.1:8000/health
```

Resposta esperada:

```json
{"status":"ok"}
```

## 6. Criar o backend no Render gratuito

Opção recomendada pela interface:

1. Acesse Render.
2. Clique em **New**.
3. Escolha **Web Service**.
4. Conecte sua conta GitHub.
5. Selecione o repositório `solver-estatistica`.
6. Configure:

| Campo | Valor |
|---|---|
| Name | `solver-estatistica-api` |
| Runtime/Language | Python 3 |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |

7. Em **Environment Variables**, adicione:

| Variável | Valor |
|---|---|
| `PYTHON_VERSION` | `3.12.8` |
| `CORS_ORIGINS` | `https://SEU_USUARIO.github.io` |

Mantenha `CORS_ORIGINS` restrito aos dominios do frontend. Para um dominio adicional de teste, acrescente a URL exata separada por virgula; nunca use `*` em producao.

A API deste projeto usa o dominio publico configurado:

```txt
https://api.solver-estatistica.com.br
```

Teste:

```txt
https://api.solver-estatistica.com.br/health
```

## 7. Conectar o frontend ao backend

A URL publica da API de producao esta definida em:

```txt
frontend/assets/js/config.js
```

O valor atual e:

```js
window.SOLVER_API_BASE_URL = "https://api.solver-estatistica.com.br";
```

Para outro ambiente, altere essa URL no codigo e mantenha `CORS_ORIGINS` limitado ao dominio desse frontend. O usuario final nao deve informar livremente uma URL de API em producao.
## 8. Usar o sistema

1. Abra o site no GitHub Pages.
2. Configure o delineamento: DIC, DBC ou DQL.
3. Escolha o tipo de análise.
4. Gere a tabela manual ou envie CSV/XLSX.
5. Clique em **Rodar análise**.
6. Confira:
   - CV experimental
   - Quadro de ANOVA
   - Comparação de médias
   - Regressão e dose ótima, quando aplicável
   - Recomendações
7. Baixe PDF, Excel, PNG ou PDF vetorial.

## 9. Formatos de dados

### DIC

```csv
tratamento,valor
T1,48.2
T1,49.1
T2,52.3
T2,51.8
```

### DBC

```csv
bloco,tratamento,valor
B1,T1,58.2
B1,T2,61.4
B2,T1,57.3
B2,T2,60.5
```

### DQL

```csv
linha,coluna,tratamento,valor
L1,C1,T1,50.1
L1,C2,T2,52.3
L2,C1,T2,51.8
L2,C2,T1,49.9
```

### Regressão

```csv
dose,valor
0,42.1
50,51.5
100,60.8
150,66.2
200,65.1
```

No frontend, informe `dose` em **Fator numérico / dose**.

## 10. Problemas comuns

### O site abre, mas a análise não roda

Verifique:

- URL do backend Render no campo do frontend.
- Endpoint `/health` respondendo.
- Variável `CORS_ORIGINS` no Render.

### Primeira análise demora

No plano gratuito, o Render pode desligar o serviço após inatividade. A primeira requisição depois disso pode demorar mais.

### Erro em DBC

O DBC exige uma observação por combinação `bloco × tratamento`. Se houver repetição dentro da mesma combinação, o backend pede correção ou agregação.

### Erro em DQL

O DQL exige que número de tratamentos, linhas e colunas seja igual, e que o total de observações seja `t²`.

## 11. Próximas melhorias recomendadas

- Login de usuários.
- Banco de dados para salvar análises.
- Relatório com logo vetorial definitivo.
- Mais diagnósticos estatísticos: normalidade, homogeneidade e resíduos.
- Testes automatizados com bases de referência.
- Módulo avançado para parcelas subdivididas com estratos de erro completos.
