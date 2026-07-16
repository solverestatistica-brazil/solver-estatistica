# Evidência de validação científica

A suíte `backend/test_golden_oracles.py` usa fórmulas analíticas independentes do caminho de
execução principal para conferir somas de quadrados, graus de liberdade e estatísticas F de DIC,
DBC, DQL, fatorial balanceado e parcelas subdivididas. Também valida regressão polinomial contra
NumPy/Statsmodels, falta de ajuste e somas de quadrados I, II e III.

Isso aumenta a confiança e impede regressões numéricas, mas não substitui a homologação final em R
ou SAS. Para cada cenário destinado a laudo oficial, anexar:

1. dataset e SHA-256;
2. configuração completa e tipo de soma de quadrados;
3. script e versão de R/SAS;
4. saída de referência;
5. tolerância numérica;
6. nome, data e assinatura do revisor independente.

## Regra pedagógica do alfa

O modo `auto` é o padrão pedagógico do produto e segue 1% ou 5% conforme a significância do teste
F. O modo `fixed` permanece disponível para protocolos que definem alfa a priori. O modo usado e o
valor efetivo são gravados na resposta, no PDF e no Excel.

## Estado da homologação externa

Não havia R/SAS instalado no ambiente desta implementação. Portanto, nenhum item deve ser marcado
como “homologado por R/SAS” até que os artefatos acima sejam versionados e revisados.
