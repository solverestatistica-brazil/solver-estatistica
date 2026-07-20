# Baseline de seguranca de dependencias

## Estado em 20/07/2026

O CI executa `pip-audit` para dependencias de producao e desenvolvimento. `python-multipart` foi atualizado para 0.0.31 e `pypdf` para 6.13.3, removendo os alertas conhecidos dessas bibliotecas.

Restam cinco IDs de vulnerabilidade associados a `starlette==0.52.1`:

- `PYSEC-2026-161`
- `PYSEC-2026-248`
- `PYSEC-2026-249`
- `PYSEC-2026-2280`
- `PYSEC-2026-2281`

As correcões publicadas exigem Starlette 1.x. O FastAPI 0.139.x suporta Starlette `>=0.40,<1.0`, portanto esse upgrade nao pode ser aplicado sem suporte oficial ou uma migracao de framework validada. Esses IDs sao excecoes nominadas no workflow; qualquer vulnerabilidade nova continua falhando a auditoria.

## Criterio para remover a excecao

Remova os IDs do workflow assim que uma versao suportada do FastAPI aceitar Starlette 1.x e execute:

```bash
pip-audit -r backend/requirements.txt
pip-audit -r backend/requirements-dev.txt
pytest -v
```

Registre no PR a versao adotada, o resultado do CI e o impacto de compatibilidade.