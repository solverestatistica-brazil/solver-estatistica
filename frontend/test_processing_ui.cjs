const fs = require('fs');
const assert = require('assert');

const html = fs.readFileSync('frontend/resultados.html', 'utf8');
const js = fs.readFileSync('frontend/assets/js/app.js', 'utf8');
const css = fs.readFileSync('frontend/assets/css/styles.css', 'utf8');

for (const id of [
  'processingOverlay', 'processingTitle', 'processingMessage', 'processingProgress',
  'processingProgressBar', 'processingSteps', 'processingElapsed', 'cancelAnalysis'
]) {
  assert(html.includes(`id="${id}"`), `elemento interativo ausente: ${id}`);
}

assert(html.includes('role="progressbar"'), 'o progresso precisa ser acessível');
assert(html.includes('aria-modal="true"'), 'o processamento precisa bloquear a interação de fundo');
assert(js.includes('currentAnalysisController = new AbortController()'), 'a análise precisa aceitar cancelamento');
assert(js.includes('signal: currentAnalysisController.signal'), 'o cancelamento precisa chegar ao fetch');
assert(js.includes("setAttribute('aria-busy', 'true')"), 'o estado ocupado precisa ser anunciado');
assert(js.includes('completeProcessing()'), 'o progresso precisa indicar conclusão');
assert(css.includes('@keyframes solver-spin'), 'a interface precisa ter feedback visual contínuo');
assert(css.includes('@media (prefers-reduced-motion:reduce)'), 'a animação precisa respeitar acessibilidade');

console.log('Processamento: progresso, etapas, acessibilidade e cancelamento aprovados');
