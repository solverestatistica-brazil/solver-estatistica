# Matriz de validação científica

Esta matriz é o critério de aceite numérico para uma release destinada a laudos. Cada caso deve guardar o dataset sem dados pessoais, a saída de referência e a versão exata do software usado na conferência.

| ID | Método | Cenário mínimo | Referência | Estado |
|---|---|---|---|---|
| DIC-01 | ANOVA DIC | balanceado, efeito significativo | fórmula fechada + R `aov`/SAS | Fórmula independente automatizada; R/SAS pendente |
| DIC-02 | ANOVA DIC | não significativo e resíduo singular | R `aov`/SAS | Pendente |
| DBC-01 | ANOVA DBC | exemplo oficial, F≈14,412 e CV≈6,21% | fórmula fechada + R/SAS | Fórmula independente e contrato do produto automatizados; R/SAS pendente |
| DQL-01 | ANOVA DQL | quadrado latino válido | fórmula fechada + R/SAS | Fórmula independente automatizada; R/SAS pendente |
| FAT-01 | Fatorial | efeitos principais sem interação | fórmula fechada + R/SAS | Balanceado e SQ I/II/III automatizados; R/SAS pendente |
| FAT-02 | Fatorial | interação significativa e desdobramento | R/SAS | Estrutura automatizada; oracle externo pendente |
| SPLIT-01 | Parcelas subdivididas | Erro (a) e Erro (b) não singulares | fórmula fechada + R `aov`/SAS | Dois estratos conferidos por fórmula independente; R/SAS pendente |
| REG-01 | Regressão | linear, quadrática e cúbica | NumPy/Statsmodels + R `lm` | Coeficientes, parcimônia e falta de ajuste automatizados; R pendente |
| TUK-01 | Tukey-Kramer | grupos balanceados e desbalanceados | R `TukeyHSD`/SAS | Pendente |
| DUN-01 | Dunnett | testemunha explícita | SciPy `dunnett` + R | Parcial: conferência SciPy automatizada |
| DUN-02 | Dunnett | testemunha ausente | regra de produto | Automatizado |
| DUN-03 | Duncan | médias conhecidas | R/SAS | Pendente |
| SNK-01 | SNK | médias conhecidas | R/SAS | Pendente |
| SCH-01 | Scheffé | contrastes conhecidos | R/SAS | Pendente |
| SK-01 | Scott–Knott | partição canônica | artigo + R `ScottKnott` | Parcial: fórmula/teste interno; falta R |
| EXP-01 | Exportações | PDF, XLSX, PNG e PDF vetorial | conteúdo + inspeção | PDF/XLSX automatizados; PNG/PDF vetorial validados em produção |

## Registro por caso

Para cada linha aprovada, registrar:

1. arquivo de entrada e checksum;
2. configuração completa;
3. software e versão de referência;
4. valores esperados e tolerâncias;
5. saída do Solver;
6. revisor, data e conclusão.
