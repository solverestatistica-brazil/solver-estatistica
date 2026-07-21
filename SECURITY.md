# Politica de seguranca

## Contato privado

Relate vulnerabilidades, incidentes de seguranca ou solicitacoes de privacidade para [solver.estatistica@gmail.com](mailto:solver.estatistica@gmail.com). Nao envie planilhas, dados pessoais, credenciais ou detalhes exploraveis em issues publicas.

Inclua, quando possivel:

- componente e versao afetados;
- impacto observado;
- passos minimos para reproduzir sem dados reais;
- sugestao de mitigacao.

## Versoes suportadas

Enquanto nao houver uma versao `1.x`, somente o commit mais recente de `main` recebe correcoes. Apos a primeira release estavel, esta secao deve indicar explicitamente as versoes suportadas.

## Principios operacionais

- payloads e conteudo de planilhas nao devem ser gravados em logs;
- mensagens 500 expostas ao usuario nao devem conter excecoes internas;
- dependencias devem ser verificadas e atualizadas por PR;
- mudancas no motor estatistico exigem testes de regressao e validacao numerica;
- segredos nunca devem ser armazenados no repositorio.
