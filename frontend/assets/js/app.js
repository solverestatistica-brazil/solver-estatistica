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
    generateManualTable();
    testApi(false);
  }

  function bindTabs() {
    document.querySelectorAll('.side-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.side-item').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        btn.classList.add('active');
        $(`tab-${btn.dataset.tab}`)?.classList.add('active');
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
    $('clearRows').addEventListener('click', () => renderEditableTable(currentHeaders, []));
    $('loadExample').addEventListener('click', loadExampleData);
    $('runAnalysis').addEventListener('click', runAnalysis);
    $('cancelAnalysis')?.addEventListener('click', () => currentAnalysisController?.abort());
    $('fileInput').addEventListener('change', handleFileUpload);
    $('downloadPdf').addEventListener('click', () => downloadExport('/api/export/pdf', 'solver-relatorio.pdf'));
    $('downloadExcel').addEventListener('click', () => downloadExport('/api/export/excel', 'solver-resultados.xlsx'));
    $('downloadPng').addEventListener('click', () => downloadExport('/api/export/regression-plot?fmt=png', 'solver-regressao.png'));
    $('downloadPlotPdf').addEventListener('click', () => downloadExport('/api/export/regression-plot?fmt=pdf', 'solver-regressao.pdf'));
    ['design', 'analysisType'].forEach((id) => $(id)?.addEventListener('change', generateManualTable));
    $('analysisType').addEventListener('change', updateFactorLevelsVisibility);
    $('analysisType').addEventListener('change', updateSumSquaresVisibility);
    $('comparisonTest').addEventListener('change', updateControlGroupVisibility);
    $('alphaMode').addEventListener('change', updateAlphaValueState);
    $('treatmentColumn').addEventListener('change', updateControlGroupOptions);
    updateControlGroupVisibility();
    updateAlphaValueState();
    updateFactorLevelsVisibility();
    updateSumSquaresVisibility();
    updateExportAvailability(false, false);
  }

  function updateControlGroupVisibility() {
    const wrap = $('controlGroupWrap');
    if (!wrap) return;
    wrap.style.display = $('comparisonTest').value === 'dunnett' ? '' : 'none';
  }

  function updateFactorLevelsVisibility() {
    const isFactorial = ['factorial', 'split_plot'].includes($('analysisType').value);
    ['factorALevelsWrap', 'factorBLevelsWrap'].forEach((id) => {
      const wrap = $(id);
      if (wrap) wrap.style.display = isFactorial ? '' : 'none';
    });
  }

  function updateSumSquaresVisibility() {
    const wrap = $('sumSquaresTypeWrap');
    if (wrap) wrap.style.display = $('analysisType').value === 'factorial' ? '' : 'none';
  }

  function updateAlphaValueState() {
    const input = $('alphaValue');
    if (!input) return;
    input.disabled = $('alphaMode').value !== 'fixed';
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
      const res = await fetchWithTimeout(`${base}/health`, {}, 15000);
      if (!res.ok) throw new Error('status ' + res.status);
      setApiStatus('API online', 'ok');
      if (showSuccess) notify('Backend salvo e respondendo.', 'success');
    } catch (err) {
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

  function generateManualTable() {
    const design = $('design').value;
    const analysisType = $('analysisType').value;
    const nTreatments = Number($('nTreatments').value || 4);
    const nBlocks = Number($('nBlocks').value || 4);
    const response = $('responseColumn').value || 'valor';
    const treatment = $('treatmentColumn').value || 'tratamento';
    const block = $('blockColumn').value || 'bloco';
    const row = $('rowColumn').value || 'linha';
    const col = $('columnColumn').value || 'coluna';
    const numeric = $('numericFactorColumn').value.trim();
    const factors = splitColumns($('factorColumns').value);

    const headers = [];
    if (design === 'DBC') headers.push(block);
    if (design === 'DQL') headers.push(row, col);
    if (analysisType === 'factorial' || analysisType === 'split_plot') headers.push(...factors.filter(Boolean));
    if (analysisType === 'regression' && numeric) headers.push(numeric);
    // Fatorial/split-plot: nao inclui a coluna de tratamento — o backend a sintetiza a
    // partir dos fatores. Incluir uma coluna 'tratamento' vazia aqui faria a validacao de
    // "coluna com valor ausente" disparar, mesmo com os dois fatores corretamente
    // preenchidos (a sintese so roda quando a coluna esta AUSENTE, nao vazia).
    if (analysisType !== 'regression' && analysisType !== 'factorial' && analysisType !== 'split_plot') headers.push(treatment);
    if (!headers.includes(response)) headers.push(response);

    const rows = [];
    if (design === 'DQL') {
      for (let r = 1; r <= nTreatments; r++) {
        for (let c = 1; c <= nTreatments; c++) {
          const treatmentIndex = ((r + c - 2) % nTreatments) + 1;
          rows.push(Object.fromEntries(headers.map((h) => [h, ''])));
          rows[rows.length - 1][row] = `L${r}`;
          rows[rows.length - 1][col] = `C${c}`;
          if (headers.includes(treatment)) rows[rows.length - 1][treatment] = `T${treatmentIndex}`;
        }
      }
    } else if (analysisType === 'regression') {
      for (let i = 0; i < nTreatments; i++) {
        for (let rep = 1; rep <= nBlocks; rep++) {
          const obj = Object.fromEntries(headers.map((h) => [h, '']));
          if (numeric) obj[numeric] = i * 50;
          obj[response] = '';
          rows.push(obj);
        }
      }
    } else if (analysisType === 'factorial' || analysisType === 'split_plot') {
      // [FIX auditoria P1-05] A versao anterior amarrava o fator A e o fator B ao MESMO
      // indice de tratamento (ex.: sempre F1x50, F2x100, F3x150, F4x200) — nunca gerava o
      // produto cartesiano completo entre os niveis dos dois fatores, entao um fatorial
      // 4x4 nunca tinha as 16 combinacoes que o delineamento exige. Agora cada fator tem seu
      // proprio numero de niveis e o gerador cria TODAS as combinacoes, em cada bloco.
      const aLevels = Math.max(2, Number($('factorALevels').value || 2));
      const bLevels = Math.max(2, Number($('factorBLevels').value || 2));
      const [factorA, factorB] = factors;
      for (let b = 1; b <= nBlocks; b++) {
        for (let a = 1; a <= aLevels; a++) {
          for (let bLvl = 1; bLvl <= bLevels; bLvl++) {
            const obj = Object.fromEntries(headers.map((h) => [h, '']));
            if (headers.includes(block)) obj[block] = `B${b}`;
            if (factorA && headers.includes(factorA)) obj[factorA] = `A${a}`;
            if (factorB && headers.includes(factorB)) obj[factorB] = `S${bLvl}`;
            rows.push(obj);
          }
        }
      }
    } else {
      for (let b = 1; b <= nBlocks; b++) {
        for (let t = 1; t <= nTreatments; t++) {
          const obj = Object.fromEntries(headers.map((h) => [h, '']));
          if (headers.includes(block)) obj[block] = `B${b}`;
          if (headers.includes(treatment)) obj[treatment] = `T${t}`;
          rows.push(obj);
        }
      }
    }
    renderEditableTable(unique(headers), rows);
  }

  function renderEditableTable(headers, rows) {
    currentResult = null;
    updateExportAvailability(false, false);
    currentHeaders = unique(headers);
    dataTable.innerHTML = '';
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
      td.appendChild(input);
      tr.appendChild(td);
    });
    const action = document.createElement('td');
    const btn = document.createElement('button');
    btn.className = 'btn ghost danger';
    btn.type = 'button';
    btn.textContent = 'Remover';
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
      data: tableToRows()
    };
  }

  async function runAnalysis() {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('O serviço estatístico não está configurado.', 'error');
    const payload = payloadFromUi();
    if (!payload.data.length) return notify('Insira ou carregue dados antes de analisar.', 'error');
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
    renderProvenance(result?.provenance, result?.meta);
    updateExportAvailability(true, Boolean(result?.regression));

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

  function renderProvenance(provenance, meta) {
    const box = $('provenanceSummary');
    if (!box) return;
    const config = provenance?.config || {};
    const dataHash = String(provenance?.data_sha256 || '—');
    const items = [
      ['Motor', provenance?.engine_version || '—'],
      ['Commit', String(provenance?.git_commit || '—').slice(0, 12)],
      ['Gerado em UTC', provenance?.generated_at_utc || '—'],
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

  async function downloadExport(endpoint, filename) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('O serviço estatístico não está configurado.', 'error');
    const payload = payloadFromUi();
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
    } catch (err) {
      notify(err.message || 'Erro ao exportar.', 'error');
    }
  }

  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      event.target.value = '';
      return notify('Arquivo muito grande. O limite é 5 MB.', 'error');
    }
    const ext = file.name.split('.').pop().toLowerCase();
    try {
      if (ext === 'csv') {
        const text = await file.text();
        const rows = parseCsv(text);
        validateImportedRows(rows);
        renderEditableTable(Object.keys(rows[0] || {}), rows);
      } else if (['xlsx', 'xls'].includes(ext)) {
        const buffer = await file.arrayBuffer();
        const workbook = XLSX.read(buffer, { type: 'array' });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
        validateImportedRows(rows);
        renderEditableTable(Object.keys(rows[0] || {}), rows);
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

  async function loadExampleData() {
    $('design').value = 'DBC';
    $('analysisType').value = 'single';
    $('responseColumn').value = 'valor';
    $('treatmentColumn').value = 'tratamento';
    $('blockColumn').value = 'bloco';
    try {
      const response = await fetchWithTimeout('assets/data/dbc_exemplo.json', {}, 15000);
      if (!response.ok) throw new Error('Não foi possível carregar o exemplo oficial.');
      const rows = await response.json();
      validateImportedRows(rows);
      renderEditableTable(['bloco', 'tratamento', 'valor'], rows);
      notify('Exemplo oficial DBC carregado.', 'success');
    } catch (err) {
      notify(err.message || 'Erro ao carregar o exemplo.', 'error');
    }
  }

  function openTab(name) {
    const btn = document.querySelector(`.side-item[data-tab="${name}"]`);
    if (btn) btn.click();
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
