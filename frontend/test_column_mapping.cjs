// Regressão P1 — mapeamento de colunas no upload (não bloqueante).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');

assert.match(html, /id="mappingPanel"/, 'painel de mapeamento ausente no HTML');
assert.match(html, /id="mappingFields"/, 'container de campos de mapeamento ausente');
assert.match(html, /nenhum passo é obrigatório/, 'copy deixando claro que é não bloqueante');

assert.match(js, /function renderColumnMapping\(headers\)/, 'renderColumnMapping ausente');
// Defaults vêm da auto-detecção existente.
assert.match(js, /syncImportedColumns\(headers\);\n\s*renderEditableTable\(headers, rows\);\n\s*renderColumnMapping\(headers\);/,
  'upload deve auto-detectar e depois oferecer o mapeamento');
// Overrides escrevem de volta nos campos de configuração (preserva contrato do backend).
assert.match(js, /if \(\$\(id\)\) \$\(id\)\.value = val;/, 'override de coluna deve atualizar o campo de config');
// Não reintroduz etapa obrigatória: painel some no modo manual e no reset.
assert.match(js, /if \(isManual\) \$\('mappingPanel'\)\?\.classList\.add\('hidden'\)/, 'mapeamento deve sumir no modo manual');

console.log('test_column_mapping: OK');
