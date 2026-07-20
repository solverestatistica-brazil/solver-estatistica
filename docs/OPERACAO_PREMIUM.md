# Operação premium

## Objetivos de serviço

- disponibilidade mensal alvo: 99,5%;
- latência p95 com serviço aquecido: até 10 segundos para o exemplo oficial;
- taxa de respostas 5xx: inferior a 1%;
- zero perda intencional de planilhas: o serviço não mantém banco de dados de análises;
- recuperação de uma release defeituosa: rollback em até 30 minutos.

O plano gratuito do Render pode suspender a API e não atende ao objetivo de disponibilidade. A
migração para um plano sem suspensão é uma decisão de cobrança e deve ser ativada pelo titular no
painel do Render. O `render.yaml` permanece sem alteração de plano para não iniciar cobrança
automaticamente.

## Monitoramento

1. Monitorar `GET /health` e validar `status=ok` e a versão do motor.
2. Alertar após duas falhas consecutivas e quando a latência exceder 15 segundos.
3. Centralizar logs de `request_id`, rota, status e duração, sem registrar payloads ou planilhas.
4. Acompanhar respostas 429, 503 e 5xx separadamente.
5. Registrar incidente, causa, impacto, duração, correção e ação preventiva.

## Proxy e limite por cliente

No Render, `TRUST_PROXY_HEADERS=true` permite que o limite por minuto use o IP encaminhado pelo balanceador. Em hospedagem direta ou atras de proxy nao administrado, mantenha essa variavel ausente ou com valor `false`, pois o cabecalho pode ser forjado pelo cliente.
## Carga e capacidade

O limite padrão é de duas análises pesadas simultâneas e 60 requisições de escrita por IP/minuto.
Execute o teste somente em homologação ou janela autorizada:

```bash
python scripts/load_smoke.py --base-url https://api.solver-estatistica.com.br --requests 20 --concurrency 2
```

Aceite inicial: 100% HTTP 200, sem 5xx, p95 aquecido menor que 10 segundos e memória estável.

## Release e rollback

1. Exigir CI verde e revisão do diff.
2. Implantar primeiro em homologação e executar exemplo, upload e quatro exportações.
3. Registrar commit e versão do motor.
4. Criar tag somente após aceite técnico e científico.
5. Se houver regressão, restaurar no Render o último deploy aprovado e reverter o frontend para a
   última tag estável.

## Decisões ainda externas

- contratar instância sem suspensão;
- escolher provedor de monitoramento e canal de alertas;
- publicar canal privado de segurança/LGPD;
- aprovar os textos legais e a licença do código.
