const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const js = fs.readFileSync(path.join(__dirname, 'assets/js/app.js'), 'utf8');

assert.ok(js.includes('const API_HEALTH_TIMEOUT_MS = 45000;'), 'health check deve tolerar cold start do Render');
assert.ok(js.includes('fetchWithTimeout(`${base}/health`, {}, API_HEALTH_TIMEOUT_MS)'), 'health check deve usar timeout dedicado');
assert.ok(js.includes("err?.code === 'timeout'"), 'timeout de health deve ser tratado');
assert.ok(js.includes("setApiStatus('API iniciando', '');"), 'timeout de health nao deve exibir falso erro');

// Auto-aquecimento: em vez de um único ping, o serviço é reaquecido com polling até responder.
assert.ok(js.includes('async function warmUpService('), 'deve haver rotina de aquecimento do serviço');
assert.ok(js.includes('WARMUP_MAX_MS') && js.includes('WARMUP_INTERVAL_MS'), 'aquecimento deve ter janela e intervalo configuráveis');
assert.ok(js.includes('warmUpService();'), 'init deve disparar o aquecimento no carregamento');
assert.ok(js.includes("setApiStatus('Serviço online', 'ok')"), 'estado online deve ser sinalizado ao usuário');
assert.ok(js.includes("setApiStatus('Aquecendo o serviço…', '')"), 'estado de aquecimento deve ser exibido em vez de erro');

console.log('Health check: cold start do backend tratado corretamente');