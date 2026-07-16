const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'resultados.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'assets/js/app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets/css/styles.css'), 'utf8');

for (const id of [
  'goToData', 'configSummary', 'analysisGuidance', 'advanced-settings',
  'manualMode', 'uploadMode', 'manualDataPanel', 'uploadDataPanel',
  'manualBuilderTitle', 'manualBuilderDescription', 'nTreatmentsWrap', 'nBlocksWrap',
  'factorALevelsWrap', 'factorBLevelsWrap', 'dataEntryEmpty', 'dataWorkspace'
]) {
  const pattern = id === 'advanced-settings' ? /class="advanced-settings"/ : new RegExp(`id="${id}"`);
  assert.match(html, pattern, `elemento do fluxo guiado ausente: ${id}`);
}

assert.match(html, /Etapa 1 de 4/, 'a configuração precisa indicar sua etapa');
assert.match(html, /Etapa 2 de 4/, 'a entrada de dados precisa indicar sua etapa');
assert.match(html, /Continuar para dados/, 'a configuração precisa de uma ação explícita para avançar');
assert.match(html, /Preencher manualmente/, 'o modo manual precisa ser uma escolha clara');
assert.match(html, /Enviar CSV ou Excel/, 'o modo upload precisa ser uma escolha separada');

assert.match(js, /function goToDataEntry\(\)/, 'o botão de avanço precisa abrir a etapa de dados');
assert.match(js, /function setDataMode\(mode\)/, 'manual e upload precisam ter painéis exclusivos');
assert.match(js, /function resetDataEntry\(\)/, 'mudanças de configuração precisam invalidar tabelas antigas');
assert.match(js, /analysisType === 'split_plot' \? 'Níveis do fator A · parcela'/, 'parcelas precisam identificar o fator A');
assert.match(js, /analysisType === 'split_plot' \? 'Níveis do fator B · subparcela'/, 'subparcelas precisam identificar o fator B');
assert.match(js, /\$\('blockColumnWrap'\).*selectedDesign === 'DBC'/, 'a coluna de bloco deve aparecer apenas em DBC');
assert.match(js, /\$\('rowColumnWrap'\).*selectedDesign === 'DQL'/, 'linha deve aparecer apenas em DQL');
assert.match(js, /\$\('treatmentColumnWrap'\).*analysisType === 'single'/, 'tratamento deve aparecer apenas na análise simples');

const initBody = js.match(/function init\(\) \{([\s\S]*?)\n  \}\n\n  function bindTabs/)?.[1] || '';
assert.doesNotMatch(initBody, /generateManualTable/, 'a tabela não deve ser gerada antes de o usuário responder ao formulário');

assert.match(css, /\.data-mode-switch/, 'a escolha de entrada precisa de apresentação visual própria');
assert.match(css, /\.data-entry-empty/, 'a interface precisa explicar onde a tabela aparecerá');
assert.match(css, /\.advanced-settings/, 'opções técnicas precisam ficar recolhidas');

console.log('Fluxo guiado: configuração contextual, avanço, manual e upload aprovados');
