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
