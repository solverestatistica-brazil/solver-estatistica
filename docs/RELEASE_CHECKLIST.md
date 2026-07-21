# Checklist para a versão 1.0

## Ciência

- [ ] Todos os cenários obrigatórios da `VALIDATION_MATRIX.md` possuem dataset, referência independente, tolerância e responsável.
- [ ] DIC, DBC, DQL, fatorial e parcelas subdivididas foram comparados com R ou SAS.
- [ ] Tukey, Duncan, Dunnett, SNK, Scheffé e Scott–Knott foram comparados com implementação de referência.
- [ ] Um estatístico/agronomista independente aprovou os resultados e limitações.

## Engenharia

- [ ] CI obrigatória e verde no commit candidato.
- [ ] Branch `main` protegida contra push direto e merge sem revisão.
- [ ] Cobertura revisada; caminhos críticos possuem testes, independentemente do percentual global.
- [ ] Testes do frontend cobrem exemplo, upload, timeout, erros e exportações.
- [ ] Dependências sem vulnerabilidades críticas conhecidas.
- [ ] Teste de carga define limite seguro de concorrência e tamanho.
- [ ] Deploy de homologação aprovado e rollback testado.

## Produto e operação

- [ ] Exemplo oficial reproduz os números publicados na matriz de aceite.
- [ ] Monitoramento de disponibilidade, latência e erros configurado.
- [ ] Plano sem cold start ou mensagem operacional compatível com a latência real.
- [ ] Política de retenção confirmada com o provedor de infraestrutura.
- [x] Canal privado para seguranca e privacidade publicado: solver.estatistica@gmail.com.

## Legal

- [ ] Responsável legal revisou Privacidade e Termos.
- [x] Licenca MIT publicada no repositorio.
- [ ] Identificação e canal LGPD publicados.

## Publicação

- [ ] Versão da API e do relatório atualizadas.
- [ ] Changelog revisado.
- [ ] Tag assinada `v1.0.0` criada a partir do commit aprovado.
- [ ] Release do GitHub publicada com artefatos e limitações conhecidas.
