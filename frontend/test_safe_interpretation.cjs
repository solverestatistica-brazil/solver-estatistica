// Regressão P1 — interpretação segura dos resultados.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');

// Alerta quando pressupostos não são atendidos.
assert.match(html, /id="interpretationCaveat"/, 'banner de ressalva ausente');
assert.match(js, /function updateInterpretationCaveat\(pressupostos\)/, 'updateInterpretationCaveat ausente');
assert.match(js, /updateInterpretationCaveat\(result\?\.pressupostos\)/, 'renderResults deve atualizar a ressalva');
assert.match(js, /pressupostos da ANOVA não foram plenamente atendidos/, 'texto de ressalva ausente');

// Disclaimer de causalidade + tooltips de termos técnicos.
assert.match(html, /id="interpretationDisclaimer"/, 'disclaimer de causalidade ausente');
assert.match(html, /não implica causalidade/, 'texto de não-causalidade ausente');
assert.match(html, /<abbr title="Coeficiente de variação/, 'tooltip de CV ausente');
assert.match(html, /compartilham a mesma letra não diferem/, 'explicação dos grupos de médias ausente');

console.log('test_safe_interpretation: OK');
