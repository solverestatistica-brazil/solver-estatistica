const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const js = fs.readFileSync(path.join(__dirname, 'assets/js/app.js'), 'utf8');

assert.ok(js.includes('const API_HEALTH_TIMEOUT_MS = 45000;'), 'health check deve tolerar cold start do Render');
assert.ok(js.includes('fetchWithTimeout(`${base}/health`, {}, API_HEALTH_TIMEOUT_MS)'), 'health check deve usar timeout dedicado');
assert.ok(js.includes("err?.code === 'timeout'"), 'timeout de health deve ser tratado');
assert.ok(js.includes("setApiStatus('API iniciando', '');"), 'timeout de health nao deve exibir falso erro');

console.log('Health check: cold start do backend tratado corretamente');