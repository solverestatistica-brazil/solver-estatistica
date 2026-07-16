# Matriz de validação científica

Esta matriz é o critério de aceite numérico para uma release destinada a laudos. Cada caso deve guardar o dataset sem dados pessoais, a saída de referência e a versão exata do software usado na conferência.

| ID | Método | Cenário mínimo | Referência | Estado |
|---|---|---|---|---|
| DIC-01 | ANOVA DIC | balanceado, efeito significativo | R `aov`/SAS | Pendente |
| DIC-02 | ANOVA DIC | não significativo e resíduo singular | R `aov`/SAS | Pendente |
| DBC-01 | ANOVA DBC | exemplo oficial, F≈14,412 e CV≈6,21% | tabela de aceite atual | Automatizado internamente; falta referência independente |
| DQL-01 | ANOVA DQL | quadrado latino válido | R/SAS | Pendente |
| FAT-01 | Fatorial | efeitos principais sem interação | R/SAS | Pendente |
| FAT-02 | Fatorial | interação significativa e desdobramento | R/SAS | Pendente |
| SPLIT-01 | Parcelas subdivididas | Erro (a) e Erro (b) não singulares | R `aov`/SAS | Pendente |
| REG-01 | Regressão | linear, quadrática e cúbica | R `lm` | Pendente |
| TUK-01 | Tukey-Kramer | grupos balanceados e desbalanceados | R `TukeyHSD`/SAS | Pendente |
| DUN-01 | Dunnett | testemunha explícita | SciPy `dunnett` + R | Parcial: conferência SciPy automatizada |
| DUN-02 | Dunnett | testemunha ausente | regra de produto | Automatizado |
| DUN-03 | Duncan | médias conhecidas | R/SAS | Pendente |
| SNK-01 | SNK | médias conhecidas | R/SAS | Pendente |
| SCH-01 | Scheffé | contrastes conhecidos | R/SAS | Pendente |
| SK-01 | Scott–Knott | partição canônica | artigo + R `ScottKnott` | Parcial: fórmula/teste interno; falta R |
| EXP-01 | Exportações | PDF, XLSX, PNG e PDF vetorial | snapshot/inspeção | Pendente |

## Registro por caso

Para cada linha aprovada, registrar:

1. arquivo de entrada e checksum;
2. configuração completa;
3. software e versão de referência;
4. valores esperados e tolerâncias;
5. saída do Solver;
6. revisor, data e conclusão.
