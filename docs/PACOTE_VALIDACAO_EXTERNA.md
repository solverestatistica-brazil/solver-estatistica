# Pacote de validacao externa

Use este roteiro para transformar cada item pendente da `VALIDATION_MATRIX.md` em evidencia revisavel. Nao inclua dados pessoais, identificaveis de fazenda ou informacoes confidenciais.

## Arquivos por caso

Crie uma pasta `validation-external/<ID>/` contendo:

1. `entrada.csv` ou `entrada.xlsx` anonimizado;
2. `sha256.txt` do arquivo de entrada;
3. `config.json` com o delineamento, colunas, teste, alfa e tipo de soma de quadrados;
4. `referencia.R` ou `referencia.sas` reproduzivel;
5. `referencia.txt` com versao do software e saida de referencia;
6. `solver.json` com a resposta da API;
7. `comparacao.md` com tolerancias, divergencias e conclusao;
8. `revisao.md` assinado pelo revisor independente.

## Criterio de aceite

- use tolerancia absoluta e relativa declaradas antes da comparacao;
- compare graus de liberdade, somas de quadrados, quadrados medios, F, p-valor e decisao;
- para pos-testes, compare cada decisao par-a-par e grupos/letras quando aplicavel;
- registre qualquer diferenca, inclusive quando o Solver for mais explicito que a referencia;
- so altere o estado da matriz para aprovado com revisor, data e software de referencia.

## Ordem recomendada

1. DIC-01, DBC-01, DQL-01 e REG-01;
2. FAT-01 e SPLIT-01;
3. TUK-01, DUN-01, DUN-03, SNK-01, SCH-01 e SK-01;
4. cenarios de erro e exportacoes.