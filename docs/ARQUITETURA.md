# Arquitetura do Solver Estatística

## Visão geral

O projeto separa a camada visual da camada estatística:

```txt
Usuário
  ↓
GitHub Pages: frontend estático
  ↓ fetch HTTPS
Render: backend FastAPI
  ↓
Motor estatístico Python: pandas, scipy, statsmodels, matplotlib
```

## Por que essa divisão?

O GitHub Pages é ideal para HTML, CSS e JavaScript estático. Ele não executa Python no servidor. Por isso, cálculos estatísticos, upload de planilhas e exportações são processados no backend FastAPI hospedado no Render.

## Funcionalidades por camada

### Frontend

- Identidade visual Solver.
- Entrada manual de dados.
- Upload CSV/XLSX em navegador.
- Configuração do delineamento.
- Exibição de cards, ANOVA, médias, recomendações e regressão.
- Chamada aos endpoints do backend.

### Backend

- Validação de delineamento.
- ANOVA DIC, DBC e DQL.
- Fatorial e parcelas subdivididas no MVP.
- Testes de comparação de médias.
- Regressão linear, quadrática e cúbica.
- Sugestão automática por R² ajustado.
- Exportação em PDF, Excel, PNG e PDF vetorial.

## Endpoints principais

| Método | Rota | Uso |
|---|---|---|
| GET | `/health` | Testar se a API está online |
| POST | `/api/analyze` | Rodar análise estatística |
| POST | `/api/analyze-upload` | Rodar análise a partir de arquivo |
| POST | `/api/export/pdf` | Baixar relatório PDF |
| POST | `/api/export/excel` | Baixar planilha Excel |
| POST | `/api/export/regression-plot?fmt=png` | Baixar gráfico PNG |
| POST | `/api/export/regression-plot?fmt=pdf` | Baixar gráfico em PDF vetorial |

## Modelo de payload

```json
{
  "design": "DBC",
  "analysis_type": "single",
  "response_column": "valor",
  "treatment_column": "tratamento",
  "block_column": "bloco",
  "comparison_test": "tukey",
  "goal": "max",
  "data": [
    {"bloco":"B1", "tratamento":"T1", "valor":58.2},
    {"bloco":"B1", "tratamento":"T2", "valor":61.4}
  ]
}
```

## Pontos para evolução

1. Autenticação e histórico de análises.
2. Banco de dados para salvar projetos.
3. Importador com mapeamento assistido de colunas.
4. Validação estatística avançada para parcelas subdivididas.
5. Testes unitários com bases conhecidas e conferência contra softwares estatísticos.
6. Relatórios com logo vetorial oficial.

## Referencias cientificas

Os calculos de ANOVA (teste F), os delineamentos (DIC/DBC/DQL/fatorial/parcelas
subdivididas) e os testes de comparacao de medias (Tukey, Duncan, Dunnett, SNK, Scheffe)
implementados em `statistics_engine.py` seguem a formulacao classica descrita nas
referencias abaixo. Verificadas via busca em julho de 2026.

**Livros-texto (base das formulas e tabelas usadas no app):**

- GOMES, F. P. *Curso de Estatistica Experimental*. 15. ed. Piracicaba: FEALQ/ESALQ, 2022.
  ISBN 978-85-7133-055-9. Referencia brasileira classica; cobre DIC, DBC, DQL, fatorial,
  parcelas subdivididas e as tabelas do teste de Tukey usadas no app.
- BANZATTO, D. A.; KRONKA, S. N. *Experimentacao Agricola*. 4. ed. Jaboticabal: FUNEP, 2006.
  ISBN 85-87632-71-X. Cobre os mesmos delineamentos e regressao por polinomios ortogonais,
  base do modulo de regressao/dose otima.
- STEEL, R. G. D.; TORRIE, J. H.; DICKEY, D. A. *Principles and Procedures of Statistics:
  A Biometrical Approach*. 3. ed. New York: McGraw-Hill, 1997. Referencia internacional
  equivalente, usada para conferencia cruzada das formulas.

**Artigos originais dos pos-testes de comparacao de medias:**

- TUKEY, J. W. Comparing individual means in the analysis of variance. *Biometrics*, v. 5,
  n. 2, p. 99-114, 1949. DOI 10.2307/3001913.
- DUNCAN, D. B. Multiple range and multiple F tests. *Biometrics*, v. 11, n. 1, p. 1-42, 1955.
  DOI 10.2307/3001478.
- DUNNETT, C. W. A multiple comparison procedure for comparing several treatments with a
  control. *Journal of the American Statistical Association*, v. 50, n. 272, p. 1096-1121,
  1955. DOI 10.1080/01621459.1955.10501294.
- NEWMAN, D. The distribution of range in samples from a normal population, expressed in
  terms of an independent estimate of standard deviation. *Biometrika*, v. 31, n. 1-2,
  p. 20-30, 1939; KEULS, M. The use of the "studentized range" in connection with an
  analysis of variance. *Euphytica*, v. 1, p. 112-122, 1952. (base do teste SNK)
- SCHEFFE, H. A method for judging all contrasts in the analysis of variance. *Biometrika*,
  v. 40, n. 1-2, p. 87-110, 1953.

**Origem do teste F / ANOVA:**

- FISHER, R. A. *Statistical Methods for Research Workers*. Edinburgh: Oliver and Boyd, 1925.

Essas referencias documentam a origem das formulas e tabelas, mas nao substituem
verificacao numerica linha a linha: o item 5 de "Pontos para evolucao" acima (testes
unitarios contra bases conhecidas e conferencia contra outros softwares estatisticos)
continua sendo a forma mais confiavel de validar a implementacao.
