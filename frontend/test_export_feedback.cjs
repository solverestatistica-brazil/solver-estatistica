const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets/css/styles.css'), 'utf8');

assert.match(html, /id="goToExports"/, 'o resultado precisa oferecer avanço explícito para exportações');
assert.match(html, /id="exportStatus"[^>]*role="status"[^>]*aria-live="polite"/, 'a exportação precisa anunciar progresso');
assert.match(js, /function setExportStatus\(message, state\)/, 'o estado da exportação precisa ser controlado');
assert.match(js, /Gerando \$\{label\}/, 'a geração precisa informar início ao usuário');
assert.match(js, /O download foi iniciado/, 'a geração precisa confirmar o download');
assert.match(js, /setAttribute\('aria-busy', 'true'\)/, 'o botão precisa expor estado ocupado');
assert.match(js, /timeZone: 'America\/Sao_Paulo'/, 'a interface precisa exibir horários de Brasília');
assert.match(js, /Gerado em Brasília/, 'a proveniência precisa usar o rótulo local');
assert.match(css, /\.export-card\[aria-busy="true"\]/, 'o estado de geração precisa ser visível');
assert.match(css, /\.results-actions/, 'o avanço precisa ter apresentação própria');

console.log('Exportações: avanço, feedback de geração e horário de Brasília aprovados');