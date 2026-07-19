// Regressão P1 — acessibilidade WCAG.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets/css/styles.css'), 'utf8');

// Região viva anunciada a leitores de tela.
assert.match(html, /id="liveRegion"[^>]*aria-live="polite"/, 'região viva ausente');
assert.match(js, /function announce\(message\)/, 'função announce ausente');
assert.match(css, /\.sr-only\{/, 'classe sr-only ausente no CSS');

// Semântica de abas (tablist/tab/tabpanel).
assert.match(html, /role="tablist"/, 'sidebar deve ser um tablist');
assert.match(html, /<button[^>]*id="tab-config-btn"[^>]*>/, 'aba de configuração deve existir');
assert.match(html, /<button[^>]*data-tab="config"[^>]*role="tab"[^>]*>/, 'aba de configuração deve ter role="tab"');
assert.match(html, /id="tab-config"[^>]*role="tabpanel"/, 'painel deve ter role="tabpanel"');
assert.match(js, /function activateTab\(name\)/, 'activateTab ausente');
assert.match(js, /setAttribute\('aria-selected'/, 'aria-selected não é gerenciado');
assert.match(js, /\.focus\?\.\(\)/, 'foco não é movido ao trocar de aba');

// Inputs de célula gerados dinamicamente têm nome acessível.
assert.match(js, /input\.setAttribute\('aria-label'/, 'inputs de dados sem aria-label');
assert.match(js, /'Remover esta linha de dados'/, 'botão remover sem rótulo acessível');

// Alternativa textual do gráfico.
assert.match(html, /id="regressionChart"[^>]*role="img"[^>]*aria-label=/, 'canvas de regressão sem alternativa textual');

console.log('test_a11y: OK');
