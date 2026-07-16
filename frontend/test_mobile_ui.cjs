const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets/css/styles.css'), 'utf8');

assert.match(html, /mobile-table-hint/, 'a planilha editável precisa orientar a rolagem horizontal');
assert.match(js, /td\.dataset\.label = labelFor\(c\)/, 'células de resultado precisam expor seus rótulos');
assert.match(js, /th\.scope = 'col'/, 'cabeçalhos precisam manter semântica acessível');
assert.match(css, /\.result-table tbody td::before/, 'resultados precisam exibir rótulos no modo cartão');
assert.match(css, /content:attr\(data-label\)/, 'rótulos móveis precisam vir dos cabeçalhos reais');
assert.match(css, /td\[data-label="Mensagem"\]/, 'mensagens longas precisam usar toda a largura no celular');
assert.match(css, /\.data-table th:first-child\{position:sticky/, 'a primeira coluna editável precisa permanecer visível');
assert.match(css, /font-size:16px/, 'campos móveis precisam evitar zoom automático no iOS');
assert.match(css, /min-height:44px/, 'controles móveis precisam ter alvo de toque adequado');
assert.match(css, /max-height:calc\(100dvh - 24px\)/, 'o modal precisa caber em telas baixas');
assert.match(css, /\.processing-dialog\{width:100%;max-width:100%;min-width:0/, 'o modal não pode ultrapassar a largura mobile');

console.log('Mobile: tabelas, semântica, toque e modal aprovados');
