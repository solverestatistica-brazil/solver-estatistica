const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = __dirname;
const analytics = fs.readFileSync(path.join(root, 'assets/js/analytics.js'), 'utf8');
assert.match(analytics, /G-KNSPBWRLQD/);
assert.match(analytics, /solver_analytics_consent/);
assert.match(analytics, /readConsent\(\) !== 'granted'/);
assert.match(analytics, /allow_ad_personalization_signals:\s*false/);

for (const page of ['index.html', 'resultados.html', 'privacidade.html', 'termos.html']) {
  const html = fs.readFileSync(path.join(root, page), 'utf8');
  assert.match(html, /assets\/js\/analytics\.js/);
}

const privacy = fs.readFileSync(path.join(root, 'privacidade.html'), 'utf8');
assert.match(privacy, /Google Analytics/);
assert.match(privacy, /resetAnalyticsConsent/);
console.log('Analytics: consentimento, páginas e privacidade aprovados');
