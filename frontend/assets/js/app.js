/* Solver Frontend — v2 (dark bento). Preserva contratos do backend. */
(() => {
  const $ = (id) => document.getElementById(id);
  const apiInput = $('apiBase');
  const apiStatus = $('apiStatus');
  const dataTable = $('dataTable');
  let currentHeaders = ['bloco', 'tratamento', 'valor'];
  let currentResult = null;
  let regressionChart = null;
  let currentAnalysisController = null;
  let processingTimer = null;
  let processingStartedAt = 0;
  let analysisRan = false;
  let draftSaveTimer = null;
  let lastDesign = null;
  let lastAnalysis = null;
  const DRAFT_KEY = 'solver_draft_v1';
  const PROCESSING_STEPS = [
    'Validando os dados experimentais…',
    'Montando o modelo estatístico…',
    'Calculando ANOVA e comparações…',
    'Organizando resultados e diagnósticos…'
  ];

  // paleta sincronizada com o tema ativo
  let COLOR_BRAND = '#22C55E';
  let COLOR_BRAND_HI = '#4ADE80';
  let COLOR_ACCENT = '#F5A85B';
  let COLOR_TEXT_D1 = '#F5F5F5';
  let COLOR_TEXT_D2 = '#A3A3A3';
  let COLOR_BORDER = 'rgba(255,255,255,.08)';
  const MAX_FILE_BYTES = 5 * 1024 * 1024;
  const MAX_DATA_ROWS = 10000;
  const API_TIMEOUT_MS = 60000;
  const API_HEALTH_TIMEOUT_MS = 45000;

  function cssColor(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function syncThemeColors() {
    COLOR_BRAND = cssColor('--brand', COLOR_BRAND);
    COLOR_BRAND_HI = cssColor('--brand-hi', COLOR_BRAND_HI);
    COLOR_ACCENT = cssColor('--accent', COLOR_ACCENT);
    COLOR_TEXT_D1 = cssColor('--text-d1', COLOR_TEXT_D1);
    COLOR_TEXT_D2 = cssColor('--text-d2', COLOR_TEXT_D2);
    COLOR_BORDER = cssColor('--border', COLOR_BORDER);

    if (regressionChart) {
      regressionChart.data.datasets[0].backgroundColor = COLOR_BRAND;
      regressionChart.data.datasets[0].borderColor = COLOR_BRAND;
      regressionChart.data.datasets[1].borderColor = COLOR_BRAND_HI;
      regressionChart.options.plugins.legend.labels.color = COLOR_TEXT_D2;
      ['x', 'y'].forEach((axis) => {
        regressionChart.options.scales[axis].title.color = COLOR_TEXT_D2;
        regressionChart.options.scales[axis].ticks.color = COLOR_TEXT_D2;
        regressionChart.options.scales[axis].grid.color = COLOR_BORDER;
      });
      regressionChart.update('none');
    }
  }

  function init() {
    if (!apiInput || !dataTable) return; // página não é a de resultados
    syncThemeColors();
    const allowCustomApi = window.SOLVER_ALLOW_CUSTOM_API === true;
    const savedApi = allowCustomApi ? localStorage.getItem('solver_api_base_url') : '';
    apiInput.value = savedApi || window.SOLVER_API_BASE_URL || '';
    bindTabs();
    bindActions();
    resetDataEntry();
    setupDataLossGuard();
    lastDesign = $('design')?.value;
    lastAnalysis = $('analysisType')?.value;
    maybeOfferDraftRestore();
    updateStepAvailability();
    testApi(false);
  }

  function bindTabs() {
    document.querySelectorAll('.side-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.getAttribute('aria-disabled') === 'true') {
          const label = btn.textContent.trim();
          announce(`Conclua as etapas anteriores para acessar ${label}.`);
          notify('Conclua as etapas anteriores primeiro.', 'info');
          return;
        }
        activateTab(btn.dataset.tab);
      });
    });
  }

  function bindActions() {
    $('saveApi')?.addEventListener('click', () => {
      if (window.SOLVER_ALLOW_CUSTOM_API !== true) return;
      localStorage.setItem('solver_api_base_url', cleanApiBase(apiInput.value));
      testApi(true);
    });
    $('generateTable').addEventListener('click', generateManualTable);
    $('addRow').addEventListener('click', addEmptyRow);
    $('clearRows').addEventListener('click', clearDataWithGuard);
    $('loadExample').addEventListener('click', loadExampleData);
    $('runAnalysis').addEventListener('click', runAnalysis);
    $('cancelAnalysis')?.addEventListener('click', () => currentAnalysisController?.abort());
    $('fileInput').addEventListener('change', handleFileUpload);
    $('downloadPdf').addEventListener('click', (event) => downloadExport('/api/export/pdf', 'solver-relatorio.pdf', 'PDF técnico', event.currentTarget));
    $('downloadExcel').addEventListener('click', (event) => downloadExport('/api/export/excel', 'solver-resultados.xlsx', 'planilha Excel', event.currentTarget));
    $('downloadPng').addEventListener('click', (event) => downloadExport('/api/export/regression-plot?fmt=png', 'solver-regressao.png', 'PNG da regressão', event.currentTarget));
    $('downloadPlotPdf').addEventListener('click', (event) => downloadExport('/api/export/regression-plot?fmt=pdf', 'solver-regressao.pdf', 'PDF vetorial da regressão', event.currentTarget));
    $('design')?.addEventListener('change', handleConfigurationChange);
    $('analysisType')?.addEventListener('change', handleConfigurationChange);
    $('manualMode')?.addEventListener('click', () => setDataMode('manual'));
    $('uploadMode')?.addEventListener('click', () => setDataMode('upload'));
    $('goToData')?.addEventListener('click', goToDataEntry);
    $('goToExports')?.addEventListener('click', () => {
      if (!currentResult) return notify('Execute uma análise antes de acessar as exportações.', 'info');
      activateTab('exports');
    });
    $('dismissValidation')?.addEventListener('click', hideValidationErrors);
    $('restoreDraft')?.addEventListener('click', restoreDraft);
    $('discardDraft')?.addEventListener('click', discardDraft);
    $('comparisonTest').addEventListener('change', updateControlGroupVisibility);
    $('alphaMode').addEventListener('change', updateAlphaValueState);
    $('treatmentColumn').addEventListener('change', updateControlGroupOptions);
    updateControlGroupVisibility();
    updateAlphaValueState();
    updateAnalysisConfiguration();
    updateFactorLevelsVisibility();
    updateSumSquaresVisibility();
    updateExportAvailability(false, false);
  }

  function handleConfigurationChange() {
    if (isTableDirty() && !window.confirm('Mudar a configuração vai limpar os dados já inseridos. Continuar?')) {
      if ($('design')) $('design').value = lastDesign;
      if ($('analysisType')) $('analysisType').value = lastAnalysis;
      return;
    }
    updateAnalysisConfiguration();
    updateFactorLevelsVisibility();
    updateSumSquaresVisibility();
    updateControlGroupVisibility();
    resetDataEntry();
    clearDraft();
    lastDesign = $('design')?.value;
    lastAnalysis = $('analysisType')?.value;
  }

  function setDataMode(mode) {
    const isManual = mode !== 'upload';
    $('manualDataPanel')?.classList.toggle('hidden', !isManual);
    $('uploadDataPanel')?.classList.toggle('hidden', isManual);
    $('manualMode')?.classList.toggle('active', isManual);
    $('uploadMode')?.classList.toggle('active', !isManual);
    $('manualMode')?.setAttribute('aria-selected', String(isManual));
    $('uploadMode')?.setAttribute('aria-selected', String(!isManual));
    if (isManual) $('mappingPanel')?.classList.add('hidden');
  }

  function goToDataEntry() {
    updateFactorLevelsVisibility();
    setDataMode('manual');
    openTab('dados');
    const firstInput = document.querySelector('#manualDataPanel label:not([style*="display: none"]) input');
    firstInput?.focus();
  }

  function updateControlGroupVisibility() {
    const wrap = $('controlGroupWrap');
    if (!wrap) return;
    wrap.style.display = $('analysisType').value !== 'regression' && $('comparisonTest').value === 'dunnett' ? '' : 'none';
  }

  function updateFactorLevelsVisibility() {
    const analysisType = $('analysisType').value;
    const isFactorial = ['factorial', 'split_plot'].includes(analysisType);
    const design = $('design').value;
    if ($('nTreatmentsWrap')) $('nTreatmentsWrap').style.display = isFactorial ? 'none' : '';
    if ($('nBlocksWrap')) $('nBlocksWrap').style.display = design === 'DQL' ? 'none' : '';
    if ($('nTreatmentsLabel')) {
      $('nTreatmentsLabel').textContent = analysisType === 'regression' ? 'Número de doses' : 'Número de tratamentos';
    }
    const blockLabels = {
      regression: 'Repetições por dose',
      factorial: design === 'DBC' ? 'Número de blocos' : 'Repetições por combinação',
      split_plot: 'Número de blocos',
      single: design === 'DBC' ? 'Número de blocos' : 'Repetições por tratamento'
    };
    if ($('nBlocksLabel')) $('nBlocksLabel').textContent = blockLabels[analysisType] || 'Repetições';
    if ($('factorALevelsLabel')) $('factorALevelsLabel').textContent = analysisType === 'split_plot' ? 'Níveis do fator A · parcela' : 'Níveis do fator A';
    if ($('factorBLevelsLabel')) $('factorBLevelsLabel').textContent = analysisType === 'split_plot' ? 'Níveis do fator B · subparcela' : 'Níveis do fator B';
    ['factorALevelsWrap', 'factorBLevelsWrap'].forEach((id) => {
      const wrap = $(id);
      if (wrap) wrap.style.display = isFactorial ? '' : 'none';
    });

    const titles = {
      single: design === 'DQL' ? 'Informe a ordem do quadrado latino' : 'Defina tratamentos e repetições',
      factorial: 'Defina os níveis dos dois fatores',
      split_plot: 'Defina blocos, parcelas e subparcelas',
      regression: 'Defina as doses e repetições'
    };
    const descriptions = {
      single: design === 'DQL'
        ? 'O número de tratamentos também define o número de linhas e colunas do quadrado.'
        : 'A tabela será montada com uma linha para cada tratamento em cada repetição ou bloco.',
      factorial: 'O Solver criará todas as combinações entre os níveis A e B em cada repetição ou bloco.',
      split_plot: 'Em cada bloco, o fator A representa as parcelas e o fator B representa as subparcelas.',
      regression: 'O Solver criará doses igualmente espaçadas; você poderá editar os valores diretamente na tabela.'
    };
    if ($('manualBuilderTitle')) $('manualBuilderTitle').textContent = titles[analysisType] || '';
    if ($('manualBuilderDescription')) $('manualBuilderDescription').textContent = descriptions[analysisType] || '';
  }

  function updateSumSquaresVisibility() {
    const wrap = $('sumSquaresTypeWrap');
    if (wrap) wrap.style.display = $('analysisType').value === 'factorial' ? '' : 'none';
  }

  function updateAnalysisConfiguration() {
    const analysisType = $('analysisType').value;
    const isFactorial = ['factorial', 'split_plot'].includes(analysisType);
    const isRegression = analysisType === 'regression';
    const allowed = window.SolverManualData?.allowedDesigns(analysisType) || ['DIC', 'DBC', 'DQL'];
    const design = $('design');
    Array.from(design.options).forEach((option) => {
      option.disabled = !allowed.includes(option.value);
    });
    if (!allowed.includes(design.value)) design.value = allowed[0];
    const selectedDesign = design.value;

    if (isFactorial && !$('factorColumns').value.trim()) $('factorColumns').value = 'fator_a,fator_b';
    if (isRegression && !$('numericFactorColumn').value.trim()) $('numericFactorColumn').value = 'dose';
    if ($('comparisonTestWrap')) $('comparisonTestWrap').style.display = isRegression ? 'none' : '';
    if ($('factorColumnsWrap')) $('factorColumnsWrap').style.display = isFactorial ? '' : 'none';
    if ($('numericFactorColumnWrap')) $('numericFactorColumnWrap').style.display = isRegression ? '' : 'none';
    if ($('regressionDegreeWrap')) $('regressionDegreeWrap').style.display = isRegression ? '' : 'none';
    if ($('treatmentColumnWrap')) $('treatmentColumnWrap').style.display = analysisType === 'single' ? '' : 'none';
    if ($('blockColumnWrap')) $('blockColumnWrap').style.display = selectedDesign === 'DBC' ? '' : 'none';
    if ($('rowColumnWrap')) $('rowColumnWrap').style.display = selectedDesign === 'DQL' ? '' : 'none';
    if ($('columnColumnWrap')) $('columnColumnWrap').style.display = selectedDesign === 'DQL' ? '' : 'none';

    const notes = {
      single: 'DIC, DBC e DQL disponíveis para análise simples.',
      factorial: 'Fatorial manual disponível em DIC ou DBC, com exatamente dois fatores.',
      split_plot: 'Parcelas subdivididas usam DBC: fator de parcela primeiro e subparcela depois.',
      regression: 'Regressão direta manual usa DIC e uma coluna numérica de doses.'
    };
    if ($('designCompatibilityNote')) $('designCompatibilityNote').textContent = notes[analysisType] || '';

    const analysisLabels = {
      single: 'Fator único', factorial: 'Fatorial', split_plot: 'Parcelas subdivididas', regression: 'Regressão direta'
    };
    const guidance = {
      single: selectedDesign === 'DQL'
        ? ['Estrutura do quadrado latino', 'O número de tratamentos determinará também o número de linhas e colunas.']
        : ['Estrutura do experimento', selectedDesign === 'DBC' ? 'Cada bloco conterá todos os tratamentos uma vez.' : 'Cada tratamento será repetido sem a formação de blocos.'],
      factorial: ['Combinações dos fatores', `Todas as combinações entre A e B serão geradas em cada ${selectedDesign === 'DBC' ? 'bloco' : 'repetição'}.`],
      split_plot: ['Parcelas e subparcelas', 'O fator A será tratado como parcela e o fator B como subparcela dentro de cada bloco.'],
      regression: ['Níveis de dose', 'Informe pelo menos três doses. Sem grau fixo, o Solver seleciona o modelo significativo mais parcimonioso.']
    };
    const [guidanceTitle, guidanceText] = guidance[analysisType] || ['', ''];
    if ($('analysisGuidanceTitle')) $('analysisGuidanceTitle').textContent = guidanceTitle;
    if ($('analysisGuidanceText')) $('analysisGuidanceText').textContent = guidanceText;
    const summary = `${selectedDesign} · ${analysisLabels[analysisType] || analysisType}`;
    if ($('configSummary')) $('configSummary').textContent = summary;
    if ($('dataContextSummary')) $('dataContextSummary').textContent = `${summary}. Escolha como deseja informar os dados.`;
  }

  function updateAlphaValueState() {
    const input = $('alphaValue');
    if (!input) return;
    const isFixed = $('alphaMode').value === 'fixed';
    input.disabled = !isFixed;
    if ($('alphaValueWrap')) $('alphaValueWrap').style.display = isFixed ? '' : 'none';
  }

  function updateControlGroupOptions() {
    const select = $('controlGroup');
    if (!select) return;
    const treatmentCol = $('treatmentColumn').value || 'tratamento';
    const values = unique(tableToRows().map((row) => row[treatmentCol]).filter((v) => v !== undefined && v !== ''));
    const previous = select.value;
    select.innerHTML = '';
    if (!values.length) {
      select.appendChild(new Option('Gerar/carregar dados para escolher', ''));
      return;
    }
    select.appendChild(new Option('Selecione a testemunha…', ''));
    values.forEach((v) => select.appendChild(new Option(String(v), String(v))));
    if (values.map(String).includes(previous)) select.value = previous;
  }

  function cleanApiBase(value) {
    return String(value || '').trim().replace(/\/$/, '');
  }

  async function fetchWithTimeout(url, options = {}, timeoutMs = API_TIMEOUT_MS) {
    const controller = new AbortController();
    const externalSignal = options.signal;
    let didTimeout = false;
    const relayAbort = () => controller.abort();
    if (externalSignal?.aborted) relayAbort();
    else externalSignal?.addEventListener('abort', relayAbort, { once: true });
    const timer = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } catch (err) {
      if (err?.name === 'AbortError') {
        const wrapped = new Error(
          didTimeout
            ? 'O serviço demorou além do limite. Tente novamente em instantes.'
            : 'Análise cancelada pelo usuário.'
        );
        wrapped.code = didTimeout ? 'timeout' : 'cancelled';
        throw wrapped;
      }
      throw err;
    } finally {
      clearTimeout(timer);
      externalSignal?.removeEventListener('abort', relayAbort);
    }
  }

  async function testApi(showSuccess) {
    const base = cleanApiBase(apiInput.value);
    if (!base) { setApiStatus('API não configurada', 'err'); return; }
    try {
      const res = await fetchWithTimeout(`${base}/health`, {}, API_HEALTH_TIMEOUT_MS);
      if (!res.ok) throw new Error('status ' + res.status);
      setApiStatus('API online', 'ok');
      if (showSuccess) notify('Backend salvo e respondendo.', 'success');
    } catch (err) {
      if (err?.code === 'timeout') {
        setApiStatus('API iniciando', '');
        if (showSuccess) notify('O servico esta iniciando. Aguarde e tente novamente em instantes.', 'info');
        return;
      }
      setApiStatus('API sem resposta', 'err');
      if (showSuccess) notify('O serviço estatístico está indisponível. Tente novamente em instantes.', 'error');
    }
  }

  function setApiStatus(text, type) {
    apiStatus.textContent = text;
    apiStatus.className = `status-pill ${type || ''}`;
  }

  function notify(message, type = 'info') {
    const div = document.createElement('div');
    div.textContent = message;
    div.setAttribute('role', type === 'error' ? 'alert' : 'status');
    div.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
    Object.assign(div.style, {
      position: 'fixed', right: '18px', bottom: '18px', zIndex: '50',
      maxWidth: '360px', padding: '12px 14px', borderRadius: '12px',
      fontFamily: "'Open Sans', sans-serif", fontSize: '12.5px', fontWeight: '600',
      boxShadow: `0 18px 40px ${cssColor('--toast-shadow', 'rgba(0,0,0,.5)')}`, border: '1px solid ' + COLOR_BORDER,
      backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
    });
    if (type === 'error') {
      div.style.color = cssColor('--danger-foreground', '#FCA5A5');
      div.style.background = cssColor('--danger-tint', 'rgba(239,68,68,.12)');
      div.style.borderColor = cssColor('--danger-border', 'rgba(239,68,68,.35)');
    } else {
      div.style.color = COLOR_BRAND;
      div.style.background = cssColor('--success-tint', 'rgba(34,197,94,.14)');
      div.style.borderColor = cssColor('--border-brand', 'rgba(34,197,94,.35)');
    }
    announce(message);
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 4200);
  }

  function setProcessingStep(stepIndex, progress, message) {
    const progressNode = $('processingProgress');
    const progressBar = $('processingProgressBar');
    if (progressNode) progressNode.setAttribute('aria-valuenow', String(Math.round(progress)));
    if (progressBar) progressBar.style.width = `${progress}%`;
    if ($('processingMessage')) $('processingMessage').textContent = message;
    document.querySelectorAll('[data-processing-step]').forEach((node, index) => {
      node.classList.toggle('active', index === stepIndex);
      node.classList.toggle('completed', index < stepIndex);
    });
  }

  function startProcessing() {
    processingStartedAt = performance.now();
    $('processingOverlay')?.classList.remove('hidden');
    document.body.classList.add('is-processing');
    document.querySelector('main')?.setAttribute('aria-busy', 'true');
    if ($('cancelAnalysis')) $('cancelAnalysis').disabled = false;
    setProcessingStep(0, 8, PROCESSING_STEPS[0]);
    processingTimer = window.setInterval(() => {
      const elapsed = performance.now() - processingStartedAt;
      const stepIndex = Math.min(PROCESSING_STEPS.length - 1, Math.floor(elapsed / 1200));
      const bases = [14, 38, 64, 84];
      const withinStep = Math.min(10, ((elapsed % 1200) / 1200) * 10);
      setProcessingStep(stepIndex, Math.min(94, bases[stepIndex] + withinStep), PROCESSING_STEPS[stepIndex]);
      if ($('processingElapsed')) {
        $('processingElapsed').textContent = `${(elapsed / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s decorridos`;
      }
    }, 180);
  }

  function completeProcessing() {
    if (processingTimer) window.clearInterval(processingTimer);
    processingTimer = null;
    setProcessingStep(PROCESSING_STEPS.length - 1, 100, 'Resultados prontos. Abrindo o painel…');
    document.querySelectorAll('[data-processing-step]').forEach((node) => {
      node.classList.remove('active');
      node.classList.add('completed');
    });
    if ($('cancelAnalysis')) $('cancelAnalysis').disabled = true;
    return new Promise((resolve) => window.setTimeout(resolve, 320));
  }

  function stopProcessing() {
    if (processingTimer) window.clearInterval(processingTimer);
    processingTimer = null;
    $('processingOverlay')?.classList.add('hidden');
    document.body.classList.remove('is-processing');
    document.querySelector('main')?.removeAttribute('aria-busy');
  }

  function resetDataEntry() {
    currentResult = null;
    analysisRan = false;
    currentHeaders = [];
    dataTable.innerHTML = '';
    $('dataWorkspace')?.classList.add('hidden');
    $('dataEntryEmpty')?.classList.remove('hidden');
    $('mappingPanel')?.classList.add('hidden');
    hideValidationErrors();
    if ($('rowCount')) $('rowCount').textContent = 'Nenhuma linha carregada.';
    updateControlGroupOptions();
    updateExportAvailability(false, false);
    updateStepAvailability();
  }

  function generateManualTable() {
    if (!confirmDestructive('Gerar uma nova tabela vai substituir os dados atuais. Continuar?')) return;
    try {
      if (!window.SolverManualData) throw new Error('Gerador manual não carregado. Atualize a página e tente novamente.');
      const generated = window.SolverManualData.buildManualTable({
        design: $('design').value,
        analysisType: $('analysisType').value,
        nTreatments: Number($('nTreatments').value),
        nBlocks: Number($('nBlocks').value),
        response: $('responseColumn').value,
        treatment: $('treatmentColumn').value,
        block: $('blockColumn').value,
        row: $('rowColumn').value,
        column: $('columnColumn').value,
        numeric: $('numericFactorColumn').value.trim(),
        factors: splitColumns($('factorColumns').value),
        aLevels: Number($('factorALevels').value),
        bLevels: Number($('factorBLevels').value)
      });
      renderEditableTable(generated.headers, generated.rows);
    } catch (error) {
      notify(error.message || 'Não foi possível gerar a tabela manual.', 'error');
    }
  }

  function renderEditableTable(headers, rows) {
    currentResult = null;
    analysisRan = false;
    updateExportAvailability(false, false);
    updateStepAvailability();
    currentHeaders = unique(headers);
    dataTable.innerHTML = '';
    $('dataWorkspace')?.classList.remove('hidden');
    $('dataEntryEmpty')?.classList.add('hidden');
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    currentHeaders.forEach((h) => {
      const th = document.createElement('th');
      th.textContent = h;
      th.scope = 'col';
      trh.appendChild(th);
    });
    const actionTh = document.createElement('th');
    actionTh.textContent = 'Ações';
    actionTh.scope = 'col';
    trh.appendChild(actionTh);
    thead.appendChild(trh);
    dataTable.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach((row) => tbody.appendChild(rowElement(row)));
    dataTable.appendChild(tbody);
    updateRowCount();
  }

  function rowElement(row = {}) {
    const tr = document.createElement('tr');
    currentHeaders.forEach((h) => {
      const td = document.createElement('td');
      const input = document.createElement('input');
      input.value = row[h] ?? '';
      input.dataset.column = h;
      input.setAttribute('aria-label', `${h} (linha de dados)`);
      td.appendChild(input);
      tr.appendChild(td);
    });
    const action = document.createElement('td');
    const btn = document.createElement('button');
    btn.className = 'btn ghost danger';
    btn.type = 'button';
    btn.textContent = 'Remover';
    btn.setAttribute('aria-label', 'Remover esta linha de dados');
    btn.addEventListener('click', () => {
      tr.remove();
      updateRowCount();
    });
    action.appendChild(btn);
    tr.appendChild(action);
    return tr;
  }

  function addEmptyRow() {
    const tbody = dataTable.querySelector('tbody');
    if (!tbody) return renderEditableTable(currentHeaders, [{}]);
    tbody.appendChild(rowElement({}));
    updateRowCount();
  }

  function updateRowCount() {
    const count = dataTable.querySelectorAll('tbody tr').length;
    $('rowCount').textContent = `${count} linha(s) carregada(s).`;
    updateControlGroupOptions();
    scheduleDraftSave();
  }

  function tableToRows() {
    return Array.from(dataTable.querySelectorAll('tbody tr')).map((tr) => {
      const row = {};
      tr.querySelectorAll('input').forEach((input) => {
        const value = input.value.trim();
        const numeric = value.replace(',', '.');
        row[input.dataset.column] = numeric !== '' && !Number.isNaN(Number(numeric)) ? Number(numeric) : value;
      });
      return row;
    }).filter((row) => Object.values(row).some((v) => v !== ''));
  }

  function payloadFromUi() {
    const degree = $('regressionDegree').value;
    return {
      design: $('design').value,
      analysis_type: $('analysisType').value,
      response_column: $('responseColumn').value || 'valor',
      treatment_column: $('treatmentColumn').value || 'tratamento',
      block_column: $('blockColumn').value || 'bloco',
      row_column: $('rowColumn').value || 'linha',
      column_column: $('columnColumn').value || 'coluna',
      factor_columns: splitColumns($('factorColumns').value),
      numeric_factor_column: $('numericFactorColumn').value.trim() || null,
      comparison_test: $('comparisonTest').value,
      control_group: $('controlGroup').value || null,
      alpha_mode: $('alphaMode').value,
      sum_squares_type: Number($('sumSquaresType').value) || 2,
      regression_degree: degree ? Number(degree) : null,
      goal: $('goal').value,
      alpha: Number($('alphaValue').value) || 0.05,
      author_name: $('authorName')?.value.trim() || null,
      data: tableToRows()
    };
  }

  async function runAnalysis() {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('O serviço estatístico não está configurado.', 'error');
    const payload = payloadFromUi();
    if (!payload.data.length) { showValidationErrors(['Insira ou carregue dados antes de analisar.']); return; }
    const issues = collectValidationIssues(payload);
    if (issues.length) { showValidationErrors(issues); return; }
    hideValidationErrors();
    const runButton = $('runAnalysis');
    try {
      runButton.disabled = true;
      currentAnalysisController = new AbortController();
      startProcessing();
      setApiStatus('Processando...', '');
      const res = await fetchWithTimeout(`${base}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: currentAnalysisController.signal
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Erro na análise');
      await completeProcessing();
      currentResult = json;
      analysisRan = true;
      clearDraft();
      renderResults(json);
      openTab('resultados');
      setApiStatus('API online', 'ok');
    } catch (err) {
      if (err?.code === 'cancelled') {
        setApiStatus('API online', 'ok');
        notify('Análise cancelada. Nenhum resultado foi alterado.', 'info');
        return;
      }
      setApiStatus('Erro na análise', 'err');
      notify(err.message || 'Erro ao rodar análise.', 'error');
    } finally {
      stopProcessing();
      currentAnalysisController = null;
      runButton.disabled = false;
    }
  }

  function renderResults(result) {
    $('emptyResults').classList.add('hidden');
    $('results').classList.remove('hidden');
    const cv = result?.anova?.cv;
    $('resCv').textContent = cv == null ? '—' : `${format(cv)}%`;
    $('resCvLabel').textContent = result?.anova?.cv_label || '—';
    $('resRows').textContent = result?.meta?.n_rows ?? '—';
    const best = result?.means?.best;
    $('resBest').textContent = best?.treatment ?? '—';
    $('resBestMean').textContent = best?.mean == null ? '—' : `Média ${format(best.mean)}`;

    renderSimpleTable('anovaTable', ['source', 'df', 'sum_sq', 'mean_sq', 'f_calc', 'f_5', 'f_1', 'p_value', 'significance'], result?.anova?.table || [], 'significance');
    renderSimpleTable('meansTable', ['treatment', 'mean', 'n', 'sd', 'group'], result?.means?.treatment_means || []);
    renderComparisonNote(result?.means?.comparison);
    renderRecommendations(result?.recommendations || []);
    renderRegression(result?.regression);
    renderFactorComparisons(result?.factor_comparisons);
    renderInteractionBreakdown(result?.interaction_breakdown);
    renderAssumptions(result?.pressupostos, result?.transformacao_sugerida);
    updateInterpretationCaveat(result?.pressupostos);
    renderProvenance(result?.provenance, result?.meta);
    updateExportAvailability(true, Boolean(result?.regression));
    updateStepAvailability();

    // atualiza previews (mesmo se hidden)
    const firstF = (result?.anova?.table || []).find((r) => r.f_calc != null);
    setPreview('previewCv', cv == null ? '—' : `${format(cv)}%`);
    setPreview('previewF', firstF ? format(firstF.f_calc) : '—');
    const reg = result?.regression?.selected_model;
    setPreview('previewR2', reg?.r2 == null ? '—' : format(reg.r2));
    const opt = reg?.optimum;
    setPreview('previewDose', opt?.x == null ? '—' : `${format(opt.x)} ${result?.regression?.x_label || ''}`);
  }

  function setPreview(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
  }

  function renderSimpleTable(id, columns, rows, sigColumn) {
    const table = $(id);
    table.innerHTML = '';
    buildTableInto(table, columns, rows, sigColumn);
  }

  function buildTableInto(table, columns, rows, sigColumn) {
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    columns.forEach((c) => {
      const th = document.createElement('th');
      th.textContent = labelFor(c);
      th.scope = 'col';
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      columns.forEach((c) => {
        const td = document.createElement('td');
        td.dataset.label = labelFor(c);
        const val = row[c];
        td.textContent = val == null ? '—' : (typeof val === 'number' ? format(val) : val);
        if (c === 'p_value' && val != null) td.textContent = formatPValue(val);
        if (sigColumn && c === sigColumn) {
          const badge = document.createElement('span');
          badge.textContent = val || 'ns';
          Object.assign(badge.style, {
            display: 'inline-block', padding: '3px 10px', borderRadius: '999px',
            fontFamily: "'JetBrains Mono', monospace", fontSize: '10.5px', fontWeight: '600',
          });
          if (val === '1%') { badge.style.background = cssColor('--success-tint', 'rgba(34,197,94,.14)'); badge.style.color = COLOR_BRAND; badge.style.border = '1px solid ' + cssColor('--border-brand', 'rgba(34,197,94,.35)'); }
          else if (val === '5%') { badge.style.background = cssColor('--warning-tint', 'rgba(245,168,91,.14)'); badge.style.color = COLOR_ACCENT; badge.style.border = '1px solid ' + cssColor('--warning', 'rgba(245,168,91,.35)'); }
          else { badge.style.background = cssColor('--neutral-tint', 'rgba(255,255,255,.05)'); badge.style.color = COLOR_TEXT_D2; badge.style.border = '1px solid ' + COLOR_BORDER; }
          td.textContent = '';
          td.appendChild(badge);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }

  function statusBadgeText(status) {
    const map = { ok: 'OK', violado: 'VIOLADO', atencao: 'ATENÇÃO', indeterminado: 'INDETERMINADO' };
    return map[status] || status || '—';
  }

  function renderFactorComparisons(list) {
    const box = $('factorComparisonsBox');
    const container = $('factorComparisonsList');
    container.innerHTML = '';
    if (!list || !list.length) { box.classList.add('hidden'); return; }
    box.classList.remove('hidden');
    list.forEach((fc) => {
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap compact';
      wrap.style.marginBottom = '14px';
      const title = document.createElement('p');
      title.className = 'small-note';
      title.innerHTML = `<b>${fc.factor}</b> — teste: ${fc.test} (α=${format(fc.alpha)}, erro ${fc.error_used === 'a' ? '(a)' : '(b)'})`;
      const table = document.createElement('table');
      table.className = 'result-table';
      buildTableInto(table, ['treatment', 'mean', 'n', 'group'], fc.levels || []);
      wrap.appendChild(title);
      wrap.appendChild(table);
      container.appendChild(wrap);
    });
  }

  function renderInteractionBreakdown(list) {
    const box = $('interactionBox');
    const container = $('interactionList');
    container.innerHTML = '';
    if (!list || !list.length) { box.classList.add('hidden'); return; }
    box.classList.remove('hidden');
    list.forEach((block) => {
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap compact';
      wrap.style.marginBottom = '14px';
      const title = document.createElement('p');
      title.className = 'small-note';
      title.innerHTML = `<b>${block.factor} = ${block.level}</b> — níveis de ${block.sub_factor} (${block.test}, α=${format(block.alpha)})`;
      const table = document.createElement('table');
      table.className = 'result-table';
      buildTableInto(table, ['treatment', 'mean', 'n', 'group'], block.levels || []);
      wrap.appendChild(title);
      wrap.appendChild(table);
      container.appendChild(wrap);
    });
  }

  function renderAssumptions(pressupostos, transformacao) {
    const box = $('assumptionsBox');
    if (!pressupostos) { box.classList.add('hidden'); return; }
    box.classList.remove('hidden');
    $('assumptionsSummary').textContent = `Veredito: ${statusBadgeText(pressupostos.veredito)} — ${pressupostos.resumo || ''}`;
    const rows = Object.entries(pressupostos.testes || {}).map(([chave, t]) => ({
      pressuposto: chave, teste: t.teste, status: statusBadgeText(t.status),
      statistic: t.statistic, p_value: t.p_value, mensagem: t.mensagem,
    }));
    renderSimpleTable('assumptionsTable', ['pressuposto', 'teste', 'status', 'statistic', 'p_value', 'mensagem'], rows);
    const note = $('transformationNote');
    if (transformacao) {
      note.textContent = `Transformação sugerida (${transformacao.metodo}): ${transformacao.descricao} ${transformacao.mensagem || ''}`;
    } else {
      note.textContent = '';
    }
  }

  function renderComparisonNote(comparison) {
    const el = $('comparisonNote');
    if (!el) return;
    if (!comparison || !comparison.note) {
      el.textContent = '';
      el.classList.remove('warning-note');
      return;
    }
    let text = comparison.note;
    if (comparison.test === 'DUNNETT' && comparison.control) {
      text += ` Testemunha usada: ${comparison.control}.`;
    }
    el.textContent = text;
    // Aviso de testemunha nao informada precisa se destacar, nao passar despercebido
    // como uma nota metodologica comum (era invisivel antes desta correcao).
    const isWarning = /testemunha não informada|testemunha nao informada/i.test(comparison.note);
    el.classList.toggle('warning-note', isWarning);
  }

  function renderRecommendations(messages) {
    const ul = $('recommendations');
    ul.innerHTML = '';
    messages.forEach((m) => {
      const li = document.createElement('li');
      li.textContent = m;
      ul.appendChild(li);
    });
  }

  function renderRegression(reg) {
    const box = $('regressionBox');
    const summary = $('regressionSummary');
    summary.innerHTML = '';
    if (!reg) {
      box.classList.add('hidden');
      if (regressionChart) regressionChart.destroy();
      return;
    }
    box.classList.remove('hidden');
    const selected = reg.selected_model || {};
    const lack = selected.lack_of_fit || {};
    [
      `Modelo: grau ${reg.selected_degree}`,
      `R²: ${format(selected.r2)}`,
      `R² ajustado: ${format(selected.adj_r2)}`,
      lack.testable ? `Falta de ajuste: F=${format(lack.f_value)} · p=${format(lack.p_value)}` : (lack.note || ''),
      selected.equation || '',
      selected.optimum ? `Ótimo: ${format(selected.optimum.x)} → ${format(selected.optimum.y)}` : ''
    ].filter(Boolean).forEach((text) => {
      const span = document.createElement('span');
      span.textContent = text;
      summary.appendChild(span);
    });

    const ctx = $('regressionChart');
    if (regressionChart) regressionChart.destroy();
    regressionChart = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Observado',
            data: (reg.points || []).map((p) => ({ x: p.x, y: p.y })),
            backgroundColor: COLOR_BRAND, borderColor: COLOR_BRAND, pointRadius: 5,
          },
          {
            label: 'Ajustado', type: 'line',
            data: (reg.fitted_curve || []).map((p) => ({ x: p.x, y: p.y })),
            pointRadius: 0, borderWidth: 2.4, borderColor: COLOR_BRAND_HI, fill: false,
          }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { color: COLOR_TEXT_D2, font: { family: 'Open Sans', size: 12 } } }
        },
        scales: {
          x: {
            title: { display: true, text: reg.x_label || 'x', color: COLOR_TEXT_D2 },
            ticks: { color: COLOR_TEXT_D2 }, grid: { color: COLOR_BORDER }
          },
          y: {
            title: { display: true, text: reg.y_label || 'Resposta', color: COLOR_TEXT_D2 },
            ticks: { color: COLOR_TEXT_D2 }, grid: { color: COLOR_BORDER }
          }
        }
      }
    });
  }

  function formatBrasiliaTimestamp(value) {
    if (!value) return '—';
    const instant = new Date(value);
    if (Number.isNaN(instant.getTime())) return String(value);
    return `${new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short', timeStyle: 'medium', timeZone: 'America/Sao_Paulo'
    }).format(instant)} BRT`;
  }

  function renderProvenance(provenance, meta) {
    const box = $('provenanceSummary');
    if (!box) return;
    const config = provenance?.config || {};
    const dataHash = String(provenance?.data_sha256 || '—');
    const items = [
      ['Motor', provenance?.engine_version || '—'],
      ['Commit', String(provenance?.git_commit || '—').slice(0, 12)],
      ['Gerado em Brasília', formatBrasiliaTimestamp(provenance?.generated_at_brasilia || provenance?.generated_at_utc)],
      ['Dados SHA-256', dataHash === '—' ? dataHash : `${dataHash.slice(0, 16)}…`],
      ['Alfa', `${meta?.alpha_mode || config.alpha_mode || 'auto'} · ${format(meta?.alpha ?? config.alpha)}`],
      ['Soma de quadrados', `Tipo ${meta?.sum_squares_type || config.sum_squares_type || 2}`],
    ];
    box.innerHTML = '';
    items.forEach(([label, value]) => {
      const item = document.createElement('div');
      const key = document.createElement('span');
      const val = document.createElement('strong');
      key.textContent = label;
      val.textContent = value;
      item.append(key, val);
      box.appendChild(item);
    });
  }
  function updateExportAvailability(hasResult, hasRegression) {
    ['downloadPdf', 'downloadExcel'].forEach((id) => { if ($(id)) $(id).disabled = !hasResult; });
    ['downloadPng', 'downloadPlotPdf'].forEach((id) => { if ($(id)) $(id).disabled = !hasRegression; });
    const note = $('exportsNote');
    if (!note) return;
    note.textContent = !hasResult
      ? 'Execute uma análise para liberar as exportações correspondentes.'
      : hasRegression
        ? 'Todas as exportações estão disponíveis para a análise atual.'
        : 'PDF e Excel disponíveis. Gráficos exigem uma análise de regressão.';
  }

  function setExportStatus(message, state) {
    const status = $('exportStatus');
    if (status) {
      status.textContent = message;
      if (state) status.dataset.state = state;
      else delete status.dataset.state;
    }
    announce(message);
  }

  async function downloadExport(endpoint, filename, label, button) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('O serviço estatístico não está configurado.', 'error');
    const payload = payloadFromUi();
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    setExportStatus(`Gerando ${label}. O download começará automaticamente.`, 'loading');
    try {
      const res = await fetchWithTimeout(`${base}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        let detail = 'Erro ao exportar.';
        try { detail = (await res.json()).detail || detail; } catch (_) { }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setExportStatus(`${label} pronto. O download foi iniciado.`, 'success');
    } catch (err) {
      setExportStatus(`Não foi possível gerar ${label}. Tente novamente.`, 'error');
      notify(err.message || 'Erro ao exportar.', 'error');
    } finally {
      button.removeAttribute('aria-busy');
      updateExportAvailability(Boolean(currentResult), Boolean(currentResult?.regression));
    }
  }
  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      event.target.value = '';
      return notify('Arquivo muito grande. O limite é 5 MB.', 'error');
    }
    if (!confirmDestructive('Importar um arquivo vai substituir os dados atuais. Continuar?')) {
      event.target.value = '';
      return;
    }
    const ext = file.name.split('.').pop().toLowerCase();
    try {
      if (ext === 'csv') {
        const text = await file.text();
        const rows = parseCsv(text);
        validateImportedRows(rows);
        const headers = Object.keys(rows[0] || {});
        syncImportedColumns(headers);
        renderEditableTable(headers, rows);
        renderColumnMapping(headers);
      } else if (['xlsx', 'xls'].includes(ext)) {
        const buffer = await file.arrayBuffer();
        const workbook = XLSX.read(buffer, { type: 'array' });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
        validateImportedRows(rows);
        const headers = Object.keys(rows[0] || {});
        syncImportedColumns(headers);
        renderEditableTable(headers, rows);
        renderColumnMapping(headers);
      } else {
        throw new Error('Formato não suportado. Use CSV, XLS ou XLSX.');
      }
      notify('Arquivo carregado. Confira as colunas antes de analisar.', 'success');
    } catch (err) {
      notify(err.message || 'Erro ao ler arquivo.', 'error');
    }
  }

  function parseCsv(text) {
    if (!window.SolverCsv?.parse) throw new Error('O leitor de CSV não foi carregado.');
    return window.SolverCsv.parse(text);
  }

  function validateImportedRows(rows) {
    if (!Array.isArray(rows) || !rows.length) throw new Error('O arquivo não contém linhas de dados.');
    if (rows.length > MAX_DATA_ROWS) throw new Error(`O limite é ${MAX_DATA_ROWS.toLocaleString('pt-BR')} linhas por análise.`);
  }

  function normalizedHeader(value) {
    return String(value || '').trim().toLocaleLowerCase('pt-BR')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
  }

  function detectHeader(headers, aliases) {
    const accepted = new Set(aliases.map(normalizedHeader));
    const matches = headers.filter((header) => accepted.has(normalizedHeader(header)));
    return matches.length === 1 ? matches[0] : null;
  }

  function syncImportedColumns(headers) {
    const mappings = [
      ['responseColumn', ['valor', 'resposta', 'response']],
      ['treatmentColumn', ['tratamento', 'treatment']],
      ['blockColumn', ['bloco', 'block']],
      ['rowColumn', ['linha', 'row']],
      ['columnColumn', ['coluna', 'column']]
    ];
    mappings.forEach(([id, aliases]) => {
      const detected = detectHeader(headers, aliases);
      if (detected && $(id)) $(id).value = detected;
    });

    if (['factorial', 'split_plot'].includes($('analysisType')?.value)) {
      const factorA = detectHeader(headers, ['fator_a', 'factor_a', 'fator a', 'a']);
      const factorB = detectHeader(headers, ['fator_b', 'factor_b', 'fator b', 'b']);
      const reserved = new Set([
        detectHeader(headers, ['valor', 'resposta', 'response']),
        detectHeader(headers, ['tratamento', 'treatment']),
        detectHeader(headers, ['bloco', 'block']),
        detectHeader(headers, ['linha', 'row']),
        detectHeader(headers, ['coluna', 'column'])
      ].filter(Boolean));
      const candidates = headers.filter((header) => !reserved.has(header));
      const factors = factorA && factorB ? [factorA, factorB] : candidates;
      if (factors.length === 2 && $('factorColumns')) $('factorColumns').value = factors.join(', ');
    }
  }

  async function loadExampleData() {
    if (!confirmDestructive('Carregar um exemplo vai substituir os dados atuais. Continuar?')) return;
    const spec = EXAMPLE_DATASETS[pickExampleKey()];
    applyExampleConfig(spec.config);
    updateAnalysisConfiguration();
    updateFactorLevelsVisibility();
    updateSumSquaresVisibility();
    updateControlGroupVisibility();
    try {
      const response = await fetchWithTimeout(spec.file, {}, 15000);
      if (!response.ok) throw new Error('Não foi possível carregar o exemplo.');
      const rows = await response.json();
      validateImportedRows(rows);
      renderEditableTable(spec.headers, rows);
      lastDesign = $('design')?.value;
      lastAnalysis = $('analysisType')?.value;
      announce(`${spec.label} carregado.`);
      notify(`${spec.label} carregado.`, 'success');
    } catch (err) {
      notify(err.message || 'Erro ao carregar o exemplo.', 'error');
    }
  }

  // ---- Acessibilidade: regiao viva para leitores de tela ----
  function announce(message) {
    const region = $('liveRegion');
    if (!region || !message) return;
    region.textContent = '';
    window.setTimeout(() => { region.textContent = message; }, 40);
  }

  // ---- Navegacao por abas acessivel + gating do fluxo guiado ----
  function activateTab(name) {
    document.querySelectorAll('.side-item').forEach((b) => {
      const on = b.dataset.tab === name;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', String(on));
    });
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    const panel = $(`tab-${name}`);
    if (!panel) return;
    panel.classList.add('active');
    panel.setAttribute('tabindex', '-1');
    const heading = panel.querySelector('h2, h3');
    (heading || panel).focus?.();
    announce((heading?.textContent || name).trim());
  }

  function updateStepAvailability() {
    const hasResult = Boolean(currentResult);
    if ($('goToExports')) $('goToExports').disabled = !hasResult;
    ['resultados', 'exports'].forEach((tabName) => {
      const btn = document.querySelector(`.side-item[data-tab="${tabName}"]`);
      if (btn) btn.setAttribute('aria-disabled', String(!hasResult));
    });
  }
  // ---- Prevencao de perda de dados ----
  function isTableDirty() {
    if (analysisRan || currentResult) return false;
    return Array.from(dataTable.querySelectorAll('tbody input'))
      .some((i) => String(i.value).trim() !== '');
  }

  function confirmDestructive(message) {
    if (!isTableDirty()) return true;
    return window.confirm(message);
  }

  function setupDataLossGuard() {
    window.addEventListener('beforeunload', (e) => {
      if (isTableDirty()) { e.preventDefault(); e.returnValue = ''; return ''; }
      return undefined;
    });
    dataTable.addEventListener('input', scheduleDraftSave);
  }

  function clearDataWithGuard() {
    if (!confirmDestructive('Limpar todos os dados inseridos? Esta ação não pode ser desfeita.')) return;
    renderEditableTable(currentHeaders, []);
    clearDraft();
    announce('Dados limpos.');
  }

  // ---- Rascunho automatico (sessionStorage) ----
  function currentTableSnapshot() {
    return { headers: currentHeaders, rows: tableToRows() };
  }
  function scheduleDraftSave() {
    window.clearTimeout(draftSaveTimer);
    draftSaveTimer = window.setTimeout(saveDraft, 600);
  }
  function saveDraft() {
    try {
      if (analysisRan) return;
      const snap = currentTableSnapshot();
      if (!snap.rows.length) return;
      window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(snap));
    } catch (_) { /* armazenamento indisponivel */ }
  }
  function clearDraft() {
    try { window.sessionStorage.removeItem(DRAFT_KEY); } catch (_) { /* noop */ }
  }
  function readDraft() {
    try {
      const raw = window.sessionStorage.getItem(DRAFT_KEY);
      if (!raw) return null;
      const snap = JSON.parse(raw);
      return snap && Array.isArray(snap.rows) && snap.rows.length ? snap : null;
    } catch (_) { return null; }
  }
  function maybeOfferDraftRestore() {
    if (readDraft()) $('draftBanner')?.classList.remove('hidden');
  }
  function restoreDraft() {
    const snap = readDraft();
    if (!snap) return;
    renderEditableTable(snap.headers || currentHeaders, snap.rows);
    $('draftBanner')?.classList.add('hidden');
    announce('Rascunho restaurado.');
    notify('Rascunho restaurado.', 'success');
  }
  function discardDraft() {
    clearDraft();
    $('draftBanner')?.classList.add('hidden');
  }

  // ---- Pre-validacao no cliente (antes do backend) ----
  function requiredColumnsFor(payload) {
    const cols = [payload.response_column];
    const t = payload.analysis_type;
    if (t === 'regression') {
      if (payload.numeric_factor_column) cols.push(payload.numeric_factor_column);
    } else if (t === 'factorial' || t === 'split_plot') {
      payload.factor_columns.forEach((c) => cols.push(c));
    } else {
      cols.push(payload.treatment_column);
    }
    if (payload.design === 'DBC' || t === 'split_plot') cols.push(payload.block_column);
    if (payload.design === 'DQL') { cols.push(payload.row_column, payload.column_column); }
    return unique(cols.filter(Boolean));
  }

  function collectValidationIssues(payload) {
    const issues = [];
    if (['factorial', 'split_plot'].includes(payload.analysis_type) && payload.factor_columns.length !== 2) {
      issues.push('Informe exatamente dois fatores, separados por vírgula, antes de analisar.');
    }
    if (payload.analysis_type === 'split_plot' && payload.design !== 'DBC') {
      issues.push('Parcelas subdivididas devem ser analisadas em DBC.');
    }
    if (payload.analysis_type === 'regression' && !payload.numeric_factor_column) {
      issues.push('Informe a coluna de dose/fator numérico antes de analisar.');
    }
    const rows = payload.data || [];
    if (rows.length < 3) {
      issues.push('São necessárias ao menos 3 observações para uma análise confiável.');
    }
    const headers = rows.length ? Object.keys(rows[0]) : [];
    const required = requiredColumnsFor(payload);
    const missing = required.filter((c) => !headers.includes(c));
    if (missing.length) {
      issues.push(`Coluna(s) ausente(s) nos dados: ${missing.join(', ')}. Ajuste os nomes na configuração ou no mapeamento de colunas.`);
    }
    const presentRequired = required.filter((c) => headers.includes(c));
    let emptyCells = 0;
    rows.forEach((row) => presentRequired.forEach((c) => {
      const v = row[c];
      if (v === '' || v == null) emptyCells += 1;
    }));
    if (emptyCells) {
      issues.push(`Há ${emptyCells} célula(s) vazia(s) em colunas obrigatórias. Preencha ou remova as linhas incompletas.`);
    }
    if (headers.includes(payload.response_column)) {
      const bad = rows.filter((row) => {
        const v = row[payload.response_column];
        return v === '' || v == null || Number.isNaN(Number(v));
      }).length;
      if (bad) issues.push(`A coluna resposta "${payload.response_column}" tem ${bad} valor(es) não numérico(s).`);
    }
    if (payload.analysis_type === 'regression' && payload.numeric_factor_column && headers.includes(payload.numeric_factor_column)) {
      const bad = rows.filter((row) => Number.isNaN(Number(row[payload.numeric_factor_column]))).length;
      if (bad) issues.push(`A coluna de dose "${payload.numeric_factor_column}" tem ${bad} valor(es) não numérico(s).`);
    }
    return issues;
  }

  function showValidationErrors(issues) {
    const panel = $('validationPanel');
    const list = $('validationList');
    if (!panel || !list) { notify(issues[0], 'error'); return; }
    list.innerHTML = '';
    issues.forEach((msg) => {
      const li = document.createElement('li');
      li.textContent = msg;
      list.appendChild(li);
    });
    panel.classList.remove('hidden');
    announce(`${issues.length} problema(s) impedem a análise. ${issues[0]}`);
    panel.setAttribute('tabindex', '-1');
    panel.focus?.();
  }
  function hideValidationErrors() {
    $('validationPanel')?.classList.add('hidden');
    if ($('validationList')) $('validationList').innerHTML = '';
  }

  // ---- Mapeamento de colunas do upload (nao bloqueante) ----
  const MAPPING_ROLES = [
    ['responseColumn', 'Resposta'],
    ['treatmentColumn', 'Tratamento'],
    ['blockColumn', 'Bloco'],
    ['rowColumn', 'Linha (DQL)'],
    ['columnColumn', 'Coluna (DQL)']
  ];
  function mappingFieldSelect(labelText, ariaText, currentValue, headers, allowNone, onChange) {
    const wrap = document.createElement('label');
    wrap.className = 'mapping-field';
    const span = document.createElement('span');
    span.textContent = labelText;
    const select = document.createElement('select');
    select.setAttribute('aria-label', ariaText);
    if (allowNone) {
      const none = document.createElement('option');
      none.value = ''; none.textContent = '— não usar —';
      select.appendChild(none);
    }
    headers.forEach((h) => {
      const opt = document.createElement('option');
      opt.value = h; opt.textContent = h;
      if (currentValue === h) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener('change', () => { onChange(select.value); hideValidationErrors(); });
    wrap.appendChild(span); wrap.appendChild(select);
    return wrap;
  }
  function renderColumnMapping(headers) {
    const panel = $('mappingPanel');
    const fields = $('mappingFields');
    if (!panel || !fields) return;
    fields.innerHTML = '';
    const type = $('analysisType')?.value;
    const design = $('design')?.value;
    const roles = MAPPING_ROLES.filter(([id]) => {
      if (id === 'blockColumn') return design === 'DBC' || type === 'split_plot';
      if (id === 'rowColumn' || id === 'columnColumn') return design === 'DQL';
      if (id === 'treatmentColumn') return !['factorial', 'split_plot', 'regression'].includes(type);
      return true;
    });
    roles.forEach(([id, label]) => {
      fields.appendChild(mappingFieldSelect(
        label, `Coluna para ${label}`, $(id)?.value, headers, true,
        (val) => { if ($(id)) $(id).value = val; }
      ));
    });
    if (['factorial', 'split_plot'].includes(type)) {
      const wrap = document.createElement('label');
      wrap.className = 'mapping-field';
      const span = document.createElement('span');
      span.textContent = 'Fatores (2, separados por vírgula)';
      const input = document.createElement('input');
      input.value = $('factorColumns')?.value || '';
      input.setAttribute('aria-label', 'Colunas dos dois fatores');
      input.addEventListener('change', () => { if ($('factorColumns')) $('factorColumns').value = input.value; hideValidationErrors(); });
      wrap.appendChild(span); wrap.appendChild(input);
      fields.appendChild(wrap);
    }
    if (type === 'regression') {
      fields.appendChild(mappingFieldSelect(
        'Coluna de dose', 'Coluna de dose ou fator numérico', $('numericFactorColumn')?.value, headers, false,
        (val) => { if ($('numericFactorColumn')) $('numericFactorColumn').value = val; }
      ));
    }
    panel.classList.remove('hidden');
  }

  // ---- Exemplos contextuais (por delineamento/tipo de analise) ----
  const EXAMPLE_DATASETS = {
    dic_single: { file: 'assets/data/dic_exemplo.json', headers: ['tratamento', 'valor'], config: { design: 'DIC', analysisType: 'single', response: 'valor', treatment: 'tratamento' }, label: 'Exemplo DIC (fator único)' },
    dbc_single: { file: 'assets/data/dbc_exemplo.json', headers: ['bloco', 'tratamento', 'valor'], config: { design: 'DBC', analysisType: 'single', response: 'valor', treatment: 'tratamento', block: 'bloco' }, label: 'Exemplo DBC (fator único)' },
    regression: { file: 'assets/data/regressao_exemplo.json', headers: ['dose', 'valor'], config: { design: 'DIC', analysisType: 'regression', response: 'valor', numeric: 'dose' }, label: 'Exemplo de regressão (doses)' },
    factorial: { file: 'assets/data/fatorial_exemplo.json', headers: ['bloco', 'hibrido', 'dose', 'valor'], config: { design: 'DBC', analysisType: 'factorial', response: 'valor', block: 'bloco', factors: 'hibrido, dose' }, label: 'Exemplo fatorial ilustrativo (DBC)' }
  };
  function pickExampleKey() {
    const type = $('analysisType')?.value;
    const design = $('design')?.value;
    if (type === 'regression') return 'regression';
    if (type === 'factorial' || type === 'split_plot') return 'factorial';
    return design === 'DIC' ? 'dic_single' : 'dbc_single';
  }
  function applyExampleConfig(cfg) {
    if (cfg.design && $('design')) $('design').value = cfg.design;
    if (cfg.analysisType && $('analysisType')) $('analysisType').value = cfg.analysisType;
    if (cfg.response && $('responseColumn')) $('responseColumn').value = cfg.response;
    if (cfg.treatment && $('treatmentColumn')) $('treatmentColumn').value = cfg.treatment;
    if (cfg.block && $('blockColumn')) $('blockColumn').value = cfg.block;
    if (cfg.factors && $('factorColumns')) $('factorColumns').value = cfg.factors;
    if (cfg.numeric && $('numericFactorColumn')) $('numericFactorColumn').value = cfg.numeric;
  }

  // ---- Interpretacao segura: alerta quando pressupostos nao sao atendidos ----
  function updateInterpretationCaveat(pressupostos) {
    const el = $('interpretationCaveat');
    if (!el) return;
    const veredito = String(pressupostos?.veredito || '').toLowerCase();
    if (pressupostos && veredito === 'atencao') {
      el.textContent = 'Nota metodol\u00f3gica: h\u00e1 um diagn\u00f3stico com poder limitado ou resultado inconclusivo. A an\u00e1lise n\u00e3o foi invalidada; interprete-a com o tamanho amostral e a raz\u00e3o entre vari\u00e2ncias.';
      el.classList.remove('hidden');
      return;
    }
    const ok = /(ok|atendid|adequad|satisfeit|v[aá]lid)/.test(veredito);
    if (pressupostos && veredito && !ok) {
      el.textContent = 'Atenção: um ou mais pressupostos da ANOVA não foram plenamente atendidos. '
        + 'Interprete os testes de significância com cautela, considere a transformação sugerida e '
        + 'lembre que significância estatística não implica causalidade.';
      el.classList.remove('hidden');
    } else {
      el.textContent = '';
      el.classList.add('hidden');
    }
  }

  function openTab(name) {
    const btn = document.querySelector(`.side-item[data-tab="${name}"]`);
    if (btn) btn.setAttribute('aria-disabled', 'false');
    activateTab(name);
  }

  function splitColumns(value) {
    return String(value || '').split(',').map((s) => s.trim()).filter(Boolean);
  }

  function unique(arr) {
    return [...new Set(arr.filter(Boolean))];
  }

  function format(v) {
    if (v == null || Number.isNaN(Number(v))) return '—';
    return Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 });
  }

  function formatPValue(v) {
    if (v == null || Number.isNaN(Number(v))) return format(v);
    const p = Number(v);
    if (p < 0.0001) return '< 0,0001';
    return `= ${p.toLocaleString('pt-BR', { maximumFractionDigits: 4 })}`;
  }

  function labelFor(key) {
    const map = {
      source: 'FV', df: 'GL', sum_sq: 'SQ', mean_sq: 'QM', f_calc: 'F calc', f_5: 'F 5%', f_1: 'F 1%', p_value: 'p', significance: 'Sig.',
      treatment: 'Tratamento', mean: 'Média', n: 'n', sd: 'DP', group: 'Grupo',
      pressuposto: 'Pressuposto', teste: 'Teste', status: 'Status', statistic: 'Estatística', mensagem: 'Mensagem'
    };
    return map[key] || key;
  }

  window.addEventListener('solver-theme-change', syncThemeColors);
  document.addEventListener('DOMContentLoaded', init);
})();
