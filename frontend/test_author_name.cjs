// Regressão — nome do autor no laudo (PDF), configurável pelo usuário.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');

// Campo de entrada existe e é rotulado.
assert.match(html, /id="authorName"/, 'campo de nome do autor ausente');
assert.match(html, /for="authorName"/, 'label do campo de nome ausente');
assert.match(html, /sem nome pessoal/, 'orientação de campo vazio ausente');

// payloadFromUi envia author_name (null quando vazio, preservando o contrato).
assert.match(js, /author_name: \$\('authorName'\)\?\.value\.trim\(\) \|\| null/, 'author_name não é enviado no payload');

console.log('test_author_name: OK');
