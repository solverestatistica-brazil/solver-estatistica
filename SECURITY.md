# Política de segurança

## Relato responsável

Não publique planilhas, dados pessoais, credenciais ou detalhes que facilitem exploração em uma issue pública. Abra inicialmente uma issue sem dados sensíveis solicitando um canal privado ao mantenedor.

Inclua, quando possível:

- componente e versão afetados;
- impacto observado;
- passos mínimos para reprodução sem dados reais;
- sugestão de mitigação.

## Versões suportadas

Enquanto não houver uma versão `1.x`, somente o commit mais recente de `main` recebe correções. Após a primeira release estável, esta seção deve indicar explicitamente as versões suportadas.

## Princípios operacionais

- payloads e conteúdo de planilhas não devem ser gravados em logs;
- mensagens 500 expostas ao usuário não devem conter exceções internas;
- dependências devem ser verificadas e atualizadas por PR;
- mudanças no motor estatístico exigem testes de regressão e validação numérica;
- segredos nunca devem ser armazenados no repositório.
