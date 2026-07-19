// Regressão P0 — prevenção de perda de dados.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');

// app.js deve ter sido desduplicado (uma única IIFE / uma única init).
assert.equal((js.match(/document\.addEventListener\('DOMContentLoaded', init\)/g) || []).length, 1,
  'app.js não pode conter a IIFE duplicada (init deve ser registrada uma única vez)');

// Guarda beforeunload quando há dados não analisados.
assert.match(js, /addEventListener\('beforeunload'/, 'guarda beforeunload ausente');
assert.match(js, /function isTableDirty\(\)/, 'isTableDirty ausente');
assert.match(js, /function confirmDestructive\(/, 'confirmDestructive ausente');

// Limpar tabela pede confirmação.
assert.match(js, /clearDataWithGuard/, 'clearRows deve usar clearDataWithGuard');
assert.match(js, /Limpar todos os dados inseridos\?/, 'confirmação de limpeza ausente');

// Regenerar tabela / importar / trocar config / exemplo pedem confirmação quando há dados.
assert.match(js, /Gerar uma nova tabela vai substituir/, 'confirmação ao regenerar ausente');
assert.match(js, /Importar um arquivo vai substituir/, 'confirmação ao importar ausente');
assert.match(js, /Mudar a configuração vai limpar/, 'confirmação ao mudar config ausente');
assert.match(js, /Carregar um exemplo vai substituir/, 'confirmação ao carregar exemplo ausente');

// Autosave de rascunho em sessionStorage + restauração.
assert.match(js, /sessionStorage\.setItem\(DRAFT_KEY/, 'saveDraft deve usar sessionStorage');
assert.match(js, /function restoreDraft\(\)/, 'restoreDraft ausente');
assert.match(js, /function maybeOfferDraftRestore\(\)/, 'maybeOfferDraftRestore ausente');
assert.match(html, /id="draftBanner"/, 'banner de rascunho ausente no HTML');
assert.match(html, /id="restoreDraft"/, 'botão restaurar rascunho ausente');

console.log('test_data_loss_guard: OK');
