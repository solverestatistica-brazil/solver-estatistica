// Regressão P1 — exemplos contextuais por delineamento/tipo.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');

assert.match(js, /const EXAMPLE_DATASETS = \{/, 'catálogo de exemplos ausente');
assert.match(js, /function pickExampleKey\(\)/, 'pickExampleKey ausente');
for (const key of ['dic_single', 'dbc_single', 'regression', 'factorial']) {
  assert.ok(js.includes(key), `exemplo contextual ausente: ${key}`);
}
// Cada exemplo referencia um arquivo de dados existente.
const dataDir = path.join(root, 'assets/data');
for (const f of ['dic_exemplo.json', 'dbc_exemplo.json', 'regressao_exemplo.json', 'fatorial_exemplo.json']) {
  assert.ok(fs.existsSync(path.join(dataDir, f)), `dataset de exemplo ausente: ${f}`);
  const rows = JSON.parse(fs.readFileSync(path.join(dataDir, f), 'utf8'));
  assert.ok(Array.isArray(rows) && rows.length >= 3, `dataset ${f} deve ter linhas suficientes`);
}
// loadExample não é mais fixo em DBC.
assert.doesNotMatch(js, /Exemplo oficial DBC carregado/, 'loadExample não deve ser fixo em DBC');
assert.match(js, /const spec = EXAMPLE_DATASETS\[pickExampleKey\(\)\]/, 'loadExample deve escolher pelo contexto');

console.log('test_contextual_examples: OK');
