// Regressão P0 — pré-validação no cliente antes do backend.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');

assert.match(js, /function collectValidationIssues\(payload\)/, 'collectValidationIssues ausente');
assert.match(js, /function requiredColumnsFor\(payload\)/, 'requiredColumnsFor ausente');

// Checagens específicas de dados.
assert.match(js, /ao menos 3 observações/, 'checagem de nº mínimo de observações ausente');
assert.match(js, /Coluna\(s\) ausente\(s\) nos dados/, 'checagem de colunas ausentes não implementada');
assert.match(js, /célula\(s\) vazia\(s\) em colunas obrigatórias/, 'checagem de células vazias ausente');
assert.match(js, /valor\(es\) não numérico\(s\)/, 'checagem de resposta numérica ausente');

// Painel persistente (não some sozinho como toast).
assert.match(js, /function showValidationErrors\(/, 'showValidationErrors ausente');
assert.match(js, /function hideValidationErrors\(/, 'hideValidationErrors ausente');
assert.match(html, /id="validationPanel"[^>]*role="alert"/, 'painel de validação deve ter role="alert"');
assert.match(html, /id="validationList"/, 'lista de validação ausente');
assert.match(html, /id="dismissValidation"/, 'botão de fechar validação ausente');

// runAnalysis usa a nova validação e não o antigo caminho de toast único.
assert.doesNotMatch(js, /validatePayloadBeforeRequest/, 'função de validação antiga deve ter sido substituída');
assert.match(js, /const issues = collectValidationIssues\(payload\)/, 'runAnalysis deve chamar collectValidationIssues');

console.log('test_prevalidation: OK');
