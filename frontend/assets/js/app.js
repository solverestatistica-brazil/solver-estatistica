/* Solver Frontend: aplicacao estatica para GitHub Pages. */
(() => {
  const $ = (id) => document.getElementById(id);
  const apiInput = $('apiBase');
  const apiStatus = $('apiStatus');
  const dataTable = $('dataTable');
  let currentHeaders = ['bloco', 'tratamento', 'valor'];
  let regressionChart = null;
  let uploadedRows = [];

  const unlockedSteps = new Set(['modelo', 'dados']);
  let currentStep = 'modelo';

  function init() {
    const savedApi = localStorage.getItem('solver_api_base_url') || window.SOLVER_API_BASE_URL || '';
    apiInput.value = savedApi;
    bindViewSwitch();
    bindStepper();
    bindActions();
    updateFieldVisibility();
    testApi(false);
    if (window.location.hash === '#analisar') showApp();
  }

  function bindViewSwitch() {
    $('heroOpenApp').addEventListener('click', showApp);
    $('navOpenApp').addEventListener('click', showApp);
    $('navBackToSite').addEventListener('click', showLanding);
    $('logoHome').addEventListener('click', (event) => {
      if (!$('view-app').classList.contains('hidden')) {
        event.preventDefault();
        showLanding();
      }
    });
  }

  function showApp() {
    $('view-landing').classList.add('hidden');
    $('view-app').classList.remove('hidden');
    $('navActionsLanding').classList.add('hidden');
    $('navActionsApp').classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'auto' });
    history.replaceState(null, '', '#analisar');
  }

  function showLanding() {
    $('view-app').classList.add('hidden');
    $('view-landing').classList.remove('hidden');
    $('navActionsApp').classList.add('hidden');
    $('navActionsLanding').classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'auto' });
    history.replaceState(null, '', '#top');
  }

  function bindStepper() {
    document.querySelectorAll('.step-pill').forEach((btn) => {
      btn.addEventListener('click', () => goToStep(btn.dataset.step));
    });
    document.querySelectorAll('[data-back]').forEach((btn) => {
      btn.addEventListener('click', () => goToStep(btn.dataset.back));
    });
    $('toDadosNext').addEventListener('click', () => goToStep('dados'));
    $('toExportsNext').addEventListener('click', () => goToStep('exports'));
    updateStepper();
  }

  function goToStep(name) {
    if (!unlockedSteps.has(name)) {
      notify('Rode a analise antes de acessar esta etapa.', 'error');
      return;
    }
    currentStep = name;
    document.querySelectorAll('.step').forEach((s) => s.classList.toggle('active', s.id === `step-${name}`));
    updateStepper();
    const flat = document.querySelector('.workspace-flat');
    if (flat) flat.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function updateStepper() {
    document.querySelectorAll('.step-pill').forEach((btn) => {
      const step = btn.dataset.step;
      btn.classList.toggle('active', step === currentStep);
      btn.classList.toggle('done', unlockedSteps.has(step) && step !== currentStep);
      btn.disabled = !unlockedSteps.has(step);
    });
  }

  function unlockResultsAndExports() {
    unlockedSteps.add('resultados');
    unlockedSteps.add('exports');
    updateStepper();
  }

  function bindActions() {
    $('saveApi').addEventListener('click', () => {
      localStorage.setItem('solver_api_base_url', cleanApiBase(apiInput.value));
      testApi(true);
    });

    $('chooseUpload').addEventListener('click', () => selectDataMode('upload'));
    $('chooseManual').addEventListener('click', () => {
      selectDataMode('manual');
      generateManualTable();
    });
    $('generateTable').addEventListener('click', generateManualTable);
    $('addRow').addEventListener('click', addEmptyRow);
    $('clearRows').addEventListener('click', () => renderEditableTable(currentHeaders, []));
    $('loadExample').addEventListener('click', loadExampleData);
    $('runAnalysis').addEventListener('click', runAnalysis);
    $('fileInput').addEventListener('change', handleFileUpload);

    $('downloadPdf').addEventListener('click', () => downloadExport('/api/export/pdf', 'solver-relatorio.pdf'));
    $('downloadExcel').addEventListener('click', () => downloadExport('/api/export/excel', 'solver-resultados.xlsx'));
    $('downloadPng').addEventListener('click', () => downloadExport('/api/export/regression-plot?fmt=png', 'solver-regressao.png'));
    $('downloadPlotPdf').addEventListener('click', () => downloadExport('/api/export/regression-plot?fmt=pdf', 'solver-regressao.pdf'));

    $('switchToRegression').addEventListener('click', () => {
      const col = $('doseAdvisory').dataset.column || '';
      $('analysisType').value = 'regression';
      if (col) $('numericFactorColumn').value = col;
      updateFieldVisibility();
      goToStep('modelo');
      notify('Tipo de analise alterado para Regressao direta. Confira os campos e rode novamente.', 'success');
    });

    ['design', 'analysisType'].forEach((id) => $(id).addEventListener('change', () => {
      updateFieldVisibility();
      hideColumnMapping();
      if (!$('dataManualPanel').classList.contains('hidden')) generateManualTable();
    }));
  }

  function selectDataMode(mode) {
    $('chooseUpload').classList.toggle('selected', mode === 'upload');
    $('chooseManual').classList.toggle('selected', mode === 'manual');
    $('dataUploadPanel').classList.toggle('hidden', mode !== 'upload');
    $('dataManualPanel').classList.toggle('hidden', mode !== 'manual');
    $('dataErrorMsg').classList.add('hidden');
    hideColumnMapping();
    if (mode === 'upload') {
      $('dataTableTools').style.display = 'none';
      $('dataTableWrap').style.display = 'none';
      uploadedRows = [];
      $('rowCount').textContent = 'Nenhum arquivo carregado.';
    }
  }

  function expectedColumnNames() {
    return [
      $('responseColumn').value || 'valor',
      $('treatmentColumn').value || 'tratamento',
      $('blockColumn').value || 'bloco',
      $('rowColumn').value || 'linha',
      $('columnColumn').value || 'coluna',
      $('numericFactorColumn').value.trim(),
      ...splitColumns($('factorColumns').value)
    ].filter(Boolean);
  }

  function normalizeHeaders(rows) {
    if (!rows.length) return rows;
    const actualKeys = Object.keys(rows[0]);
    const renameMap = {};
    expectedColumnNames().forEach((expected) => {
      if (actualKeys.includes(expected)) return;
      const match = actualKeys.find((k) => k.trim().toLowerCase() === expected.trim().toLowerCase());
      if (match) renameMap[match] = expected;
    });
    if (!Object.keys(renameMap).length) return rows;
    return rows.map((row) => {
      const newRow = {};
      Object.entries(row).forEach(([k, v]) => { newRow[renameMap[k] || k] = v; });
      return newRow;
    });
  }

  function getActiveRows() {
    return uploadedRows.length ? uploadedRows : tableToRows();
  }

  // --- Mapeamento de colunas (upload com nomes de coluna diferentes do configurado) ---

  function requiredColumnFields() {
    const design = $('design').value;
    const type = $('analysisType').value;
    const isRegression = type === 'regression';
    const fields = [];
    fields.push({ id: 'responseColumn', label: 'Coluna resposta' });
    if (!isRegression) fields.push({ id: 'treatmentColumn', label: 'Coluna tratamento' });
    if (!isRegression && design === 'DBC') fields.push({ id: 'blockColumn', label: 'Coluna bloco' });
    if (!isRegression && design === 'DQL') {
      fields.push({ id: 'rowColumn', label: 'Coluna linha' });
      fields.push({ id: 'columnColumn', label: 'Coluna coluna' });
    }
    if (isRegression) fields.push({ id: 'numericFactorColumn', label: 'Coluna dose / fator numerico' });
    return fields;
  }

  function missingColumnFields(headers) {
    const set = new Set(headers);
    return requiredColumnFields().filter((f) => {
      const configured = $(f.id).value.trim();
      return !configured || !set.has(configured);
    });
  }

  function hideColumnMapping() {
    const box = $('columnMapping');
    if (!box) return;
    box.classList.add('hidden');
    box.innerHTML = '';
  }

  function showColumnMapping(missing, headers) {
    const box = $('columnMapping');
    if (!box) return;
    box.innerHTML = '';
    box.classList.remove('hidden');

    const title = document.createElement('p');
    title.className = 'small-note';
    title.innerHTML = '<b>Os nomes das colunas do seu arquivo nao batem com a configuracao.</b> Indique qual coluna corresponde a cada campo:';
    box.appendChild(title);

    const usedHeaders = new Set();
    missing.forEach((f) => {
      const wrap = document.createElement('label');
      wrap.style.display = 'block';
      wrap.style.marginTop = '10px';
      wrap.appendChild(document.createTextNode(f.label));

      const select = document.createElement('select');
      select.dataset.target = f.id;
      select.style.marginTop = '6px';

      const emptyOpt = document.createElement('option');
      emptyOpt.value = '';
      emptyOpt.textContent = 'Selecione a coluna do arquivo...';
      select.appendChild(emptyOpt);

      headers.forEach((h) => {
        const opt = document.createElement('option');
        opt.value = h;
        opt.textContent = h;
        select.appendChild(opt);
      });

      const guess = headers.find((h) => !usedHeaders.has(h) && fuzzyMatches(h, f.id));
      if (guess) {
        select.value = guess;
        usedHeaders.add(guess);
      }

      wrap.appendChild(select);
      box.appendChild(wrap);
    });

    const applyBtn = document.createElement('button');
    applyBtn.type = 'button';
    applyBtn.className = 'btn solid';
    applyBtn.style.marginTop = '14px';
    applyBtn.textContent = 'Aplicar mapeamento e iniciar analise';
    applyBtn.addEventListener('click', applyColumnMapping);
    box.appendChild(applyBtn);
  }

  function fuzzyMatches(header, fieldId) {
    const h = header.trim().toLowerCase();
    const hints = {
      responseColumn: ['valor', 'resposta', 'response', 'y'],
      treatmentColumn: ['tratamento', 'treat', 'trat'],
      blockColumn: ['bloco', 'block', 'rep'],
      rowColumn: ['linha', 'row'],
      columnColumn: ['coluna', 'col'],
      numericFactorColumn: ['dose', 'fator', 'x']
    };
    return (hints[fieldId] || []).some((hint) => h.includes(hint));
  }

  function applyColumnMapping() {
    const box = $('columnMapping');
    if (!box) return;
    const selects = Array.from(box.querySelectorAll('select'));
    const incomplete = selects.some((s) => !s.value);
    if (incomplete) {
      notify('Selecione todas as colunas antes de continuar.', 'error');
      return;
    }
    selects.forEach((s) => { $(s.dataset.target).value = s.value; });
    hideColumnMapping();
    $('dataErrorMsg').classList.add('hidden');
    notify('Colunas mapeadas.', 'success');
    runAnalysis();
  }

  function updateFieldVisibility() {
    const design = $('design').value;
    const type = $('analysisType').value;
    const isRegression = type === 'regression';

    const rules = {
      design: !isRegression,
      treatmentColumn: !isRegression,
      blockColumn: !isRegression && design === 'DBC',
      rowColumn: !isRegression && design === 'DQL',
      columnColumn: !isRegression && design === 'DQL',
      factorColumns: type === 'factorial' || type === 'split_plot',
      numericFactorColumn: isRegression || type === 'factorial',
      regressionDegree: isRegression,
    };

    Object.entries(rules).forEach(([field, visible]) => {
      const el = document.querySelector(`[data-field="${field}"]`);
      if (el) el.classList.toggle('field-hidden', !visible);
    });
  }

  function cleanApiBase(value) {
    return String(value || '').trim().replace(/\/$/, '');
  }

  async function testApi(showSuccess) {
    const base = cleanApiBase(apiInput.value);
    if (!base) {
      setApiStatus('API nao configurada', 'err');
      return;
    }
    try {
      const res = await fetch(`${base}/health`);
      if (!res.ok) throw new Error('status ' + res.status);
      setApiStatus('API online', 'ok');
      if (showSuccess) notify('Backend salvo e respondendo.', 'success');
    } catch (err) {
      setApiStatus('API sem resposta', 'err');
      if (showSuccess) notify('Nao consegui conectar. Verifique a URL do Render e o CORS.', 'error');
    }
  }

  function setApiStatus(text, type) {
    apiStatus.textContent = text;
    apiStatus.className = `status-pill ${type || ''}`;
  }

  function notify(message, type = 'info') {
    const div = document.createElement('div');
    div.textContent = message;
    div.style.position = 'fixed';
    div.style.right = '18px';
    div.style.bottom = '18px';
    div.style.zIndex = '50';
    div.style.maxWidth = '360px';
    div.style.padding = '12px 14px';
    div.style.borderRadius = '12px';
    div.style.fontFamily = 'Montserrat, sans-serif';
    div.style.fontSize = '12px';
    div.style.fontWeight = '700';
    div.style.boxShadow = '0 18px 40px rgba(0,0,0,.25)';
    div.style.color = type === 'error' ? '#A8452F' : '#24492E';
    div.style.background = type === 'error' ? '#F0DCD5' : '#E3ECE0';
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 4200);
  }

  function generateManualTable() {
    uploadedRows = [];
    hideColumnMapping();
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
    if (analysisType !== 'regression') headers.push(treatment);
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
    } else {
      for (let b = 1; b <= nBlocks; b++) {
        for (let t = 1; t <= nTreatments; t++) {
          const obj = Object.fromEntries(headers.map((h) => [h, '']));
          if (headers.includes(block)) obj[block] = `B${b}`;
          if (headers.includes(treatment)) obj[treatment] = `T${t}`;
          factors.forEach((f, idx) => {
            if (headers.includes(f)) obj[f] = idx === 0 ? `F${t}` : `${t * 50}`;
          });
          rows.push(obj);
        }
      }
    }
    renderEditableTable(unique(headers), rows);
  }

  function renderEditableTable(headers, rows) {
    currentHeaders = unique(headers);
    dataTable.innerHTML = '';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    currentHeaders.forEach((h) => {
      const th = document.createElement('th');
      th.textContent = h;
      trh.appendChild(th);
    });
    const actionTh = document.createElement('th');
    actionTh.textContent = 'Acoes';
    trh.appendChild(actionTh);
    thead.appendChild(trh);
    dataTable.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach((row) => tbody.appendChild(rowElement(row)));
    dataTable.appendChild(tbody);

    $('dataTableTools').style.display = 'flex';
    $('dataTableWrap').style.display = 'block';
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
      comparison_test: 'tukey',
      regression_degree: degree ? Number(degree) : null,
      goal: $('goal').value,
      alpha: 0.05,
      data: getActiveRows()
    };
  }

  async function runAnalysis() {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');

    const rows = getActiveRows();
    if (!rows.length) return notify('Insira ou carregue dados antes de analisar.', 'error');

    if (uploadedRows.length) {
      const missing = missingColumnFields(currentHeaders);
      if (missing.length) {
        showColumnMapping(missing, currentHeaders);
        notify('Confira o mapeamento de colunas antes de rodar a analise.', 'error');
        return;
      }
    }

    const payload = payloadFromUi();
    try {
      setApiStatus('Processando...', '');
      const res = await fetch(`${base}/api/analyze`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Erro na analise');
      $('dataErrorMsg').classList.add('hidden');
      $('meansResultBox').classList.add('hidden');
      renderResults(json);
      setupComparisonPanel(json);
      checkDoseAdvisory();
      unlockResultsAndExports();
      goToStep('resultados');
      setApiStatus('API online', 'ok');
    } catch (err) {
      setApiStatus('Erro na analise', 'err');
      const msg = err.message || 'Erro ao rodar analise.';
      notify(msg, 'error');
      $('dataErrorMsg').textContent = msg;
      $('dataErrorMsg').classList.remove('hidden');
    }
  }

  function renderResults(result) {
    $('emptyResults').classList.add('hidden');
    $('results').classList.remove('hidden');
    const cv = result?.anova?.cv;
    $('resCv').textContent = cv == null ? '-' : `${format(cv)}%`;
    $('resCvLabel').textContent = result?.anova?.cv_label || '-';
    $('resRows').textContent = result?.meta?.n_rows ?? '-';
    const best = result?.means?.best;
    $('resBest').textContent = best?.treatment ?? '-';
    $('resBestMean').textContent = best?.mean == null ? '-' : `Media ${format(best.mean)}`;

    renderAnovaTable(result?.anova?.table || []);
    renderRecommendations(result?.recommendations || []);
    renderRegression(result?.regression);

    const firstF = (result?.anova?.table || []).find((r) => r.f_calc != null);
    $('previewCv').textContent = cv == null ? '-' : `${format(cv)}%`;
    $('previewF').textContent = firstF ? format(firstF.f_calc) : '-';
    const reg = result?.regression?.selected_model;
    $('previewR2').textContent = reg?.r2 == null ? '-' : format(reg.r2);
    const opt = reg?.optimum;
    $('previewDose').textContent = opt?.x == null ? '-' : `${format(opt.x)} ${result?.regression?.x_label || ''}`;
  }

  function sigPill(value) {
    if (value == null || value === '-' || value === '—') return '<span class="sig-dash">-</span>';
    const cls = value === '1%' ? 'sig-1' : value === '5%' ? 'sig-5' : 'sig-ns';
    return `<span class="sig-pill ${cls}">${value}</span>`;
  }

  function renderAnovaTable(rows) {
    const table = $('anovaTable');
    const columns = ['source', 'df', 'sum_sq', 'mean_sq', 'f_calc', 'f_5', 'f_1', 'significance'];
    table.innerHTML = '';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    columns.forEach((c) => {
      const th = document.createElement('th');
      th.textContent = labelFor(c);
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      columns.forEach((c) => {
        const td = document.createElement('td');
        if (c === 'significance') {
          td.innerHTML = sigPill(row[c]);
        } else if (c === 'source') {
          td.textContent = row[c] ?? '-';
        } else {
          td.classList.add('num');
          td.textContent = row[c] == null ? '-' : format(row[c]);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }

  function renderSimpleTable(id, columns, rows) {
    const table = $(id);
    table.innerHTML = '';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    columns.forEach((c) => {
      const th = document.createElement('th');
      th.textContent = labelFor(c);
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      columns.forEach((c) => {
        const td = document.createElement('td');
        const val = row[c];
        if (typeof val === 'number') {
          td.classList.add('num');
          td.textContent = format(val);
        } else {
          td.textContent = val == null || val === '' ? '-' : val;
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
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
    [
      `Modelo: grau ${reg.selected_degree}`,
      `R2: ${format(selected.r2)}`,
      `R2 ajustado: ${format(selected.adj_r2)}`,
      selected.equation || '',
      selected.optimum ? `Otimo: ${format(selected.optimum.x)} -> ${format(selected.optimum.y)}` : ''
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
          {label: 'Observado', data: (reg.points || []).map((p) => ({x:p.x, y:p.y}))},
          {label: 'Ajustado', type: 'line', data: (reg.fitted_curve || []).map((p) => ({x:p.x, y:p.y})), pointRadius: 0, borderWidth: 2}
        ]
      },
      options: {
        responsive: true,
        plugins: {legend: {position: 'bottom'}},
        scales: {
          x: {title: {display: true, text: reg.x_label || 'x'}},
          y: {title: {display: true, text: reg.y_label || 'Resposta'}}
        }
      }
    });
  }

  function extractSingleColumn(rawSource) {
    if (!rawSource || rawSource.includes(':')) return null;
    const m = rawSource.match(/Q\("([^"]+)"\)/);
    return m ? m[1] : null;
  }

  function setupComparisonPanel(result) {
    const panel = $('comparisonPanel');
    const container = $('comparisonButtons');
    container.innerHTML = '';
    const type = result?.meta?.analysis_type;

    if (type === 'regression') {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');

    if (type === 'single') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn solid';
      btn.textContent = 'Comparar medias';
      btn.addEventListener('click', () => runComparison(null, null));
      container.appendChild(btn);
      return;
    }

    let any = false;
    (result?.anova?.table || []).forEach((row) => {
      if (row.source === 'Total') return;
      const col = extractSingleColumn(row.raw_source);
      if (!col) return;
      any = true;
      const sig = row.significance === '1%' || row.significance === '5%';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn';
      btn.textContent = `Comparar: ${row.source}`;
      btn.disabled = !sig;
      btn.title = sig ? '' : 'So e possivel comparar fatores significativos no teste F.';
      btn.addEventListener('click', () => runComparison(col, row.source));
      container.appendChild(btn);
    });
    if (!any) {
      const p = document.createElement('p');
      p.className = 'small-note';
      p.textContent = 'Nenhum fator elegivel foi significativo no teste F - sem comparacao de medias recomendada.';
      container.appendChild(p);
    }
  }

  async function runComparison(colOverride, label) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadFromUi();
    payload.comparison_test = $('comparisonTestPost').value;
    if (colOverride) payload.treatment_column = colOverride;
    try {
      setApiStatus('Processando...', '');
      const res = await fetch(`${base}/api/analyze`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Erro na comparacao');
      $('meansResultBox').classList.remove('hidden');
      $('meansFactorLabel').textContent = label ? `Medias e grupos - ${label}` : 'Medias e grupos';
      renderSimpleTable('meansTable', ['treatment', 'mean', 'n', 'sd', 'group'], json?.means?.treatment_means || []);
      setApiStatus('API online', 'ok');
    } catch (err) {
      setApiStatus('Erro na comparacao', 'err');
      notify(err.message || 'Erro ao comparar medias.', 'error');
    }
  }

  function isMostlyNumeric(values) {
    const cleaned = values.map((v) => String(v ?? '').trim()).filter((v) => v !== '');
    if (cleaned.length < 3) return false;
    const numericCount = cleaned.filter((v) => !Number.isNaN(Number(v.replace(',', '.')))).length;
    return numericCount / cleaned.length >= 0.8 && new Set(cleaned).size >= 3;
  }

  function checkDoseAdvisory() {
    const type = $('analysisType').value;
    const advisory = $('doseAdvisory');
    if (type === 'regression') {
      advisory.classList.add('hidden');
      return;
    }
    const rows = getActiveRows();
    let candidateCol = null;
    if (type === 'single') {
      const col = $('treatmentColumn').value || 'tratamento';
      if (isMostlyNumeric(rows.map((r) => r[col]))) candidateCol = col;
    } else if (type === 'factorial' || type === 'split_plot') {
      splitColumns($('factorColumns').value).some((col) => {
        if (isMostlyNumeric(rows.map((r) => r[col]))) {
          candidateCol = col;
          return true;
        }
        return false;
      });
    }
    if (candidateCol) {
      advisory.classList.remove('hidden');
      advisory.dataset.column = candidateCol;
      $('doseAdvisoryText').textContent = `A coluna "${candidateCol}" parece conter valores numericos (uma dose). Considere rodar como Regressao direta para estimar a dose otima em vez de so comparar medias.`;
    } else {
      advisory.classList.add('hidden');
      advisory.dataset.column = '';
    }
  }

  async function downloadExport(endpoint, filename) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadFromUi();
    try {
      const res = await fetch(`${base}${endpoint}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        let detail = 'Erro ao exportar.';
        try { detail = (await res.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
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
    const ext = file.name.split('.').pop().toLowerCase();
    try {
      let rows;
      if (ext === 'csv') {
        const text = await file.text();
        rows = parseCsv(text);
      } else if (['xlsx','xls'].includes(ext)) {
        const buffer = await file.arrayBuffer();
        const workbook = XLSX.read(buffer, {type:'array'});
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        rows = XLSX.utils.sheet_to_json(sheet, {defval:''});
      } else {
        throw new Error('Formato nao suportado. Use CSV, XLS ou XLSX.');
      }
      rows = normalizeHeaders(rows);
      if (!rows.length) throw new Error('O arquivo nao tem linhas de dados.');
      uploadedRows = rows;
      currentHeaders = unique(Object.keys(rows[0] || {}));
      $('dataTableTools').style.display = 'none';
      $('dataTableWrap').style.display = 'none';
      $('dataErrorMsg').classList.add('hidden');

      const missing = missingColumnFields(currentHeaders);
      if (missing.length) {
        $('rowCount').textContent = `${rows.length} linha(s) carregada(s) de "${file.name}". Confira o mapeamento de colunas abaixo.`;
        showColumnMapping(missing, currentHeaders);
        notify('Arquivo carregado. Os nomes das colunas nao batem com a configuracao - confira o mapeamento abaixo.', 'info');
      } else {
        $('rowCount').textContent = `${rows.length} linha(s) carregada(s) de "${file.name}". Clique em Iniciar analise.`;
        hideColumnMapping();
        notify('Arquivo carregado. Clique em Iniciar analise.', 'success');
      }
    } catch (err) {
      notify(err.message || 'Erro ao ler arquivo.', 'error');
    }
  }

  function parseCsv(text) {
    const cleaned = text.replace(/^﻿/, '');
    const sep = cleaned.includes(';') ? ';' : ',';
    const lines = cleaned.trim().split(/\r?\n/).filter(Boolean);
    const headers = lines.shift().split(sep).map((h) => h.trim());
    return lines.map((line) => {
      const values = line.split(sep).map((v) => v.trim());
      const obj = {};
      headers.forEach((h, i) => {
        const raw = values[i] ?? '';
        const numeric = raw.replace(',', '.');
        obj[h] = numeric !== '' && !Number.isNaN(Number(numeric)) ? Number(numeric) : raw;
      });
      return obj;
    });
  }

  function loadExampleData() {
    uploadedRows = [];
    hideColumnMapping();
    $('design').value = 'DBC';
    $('analysisType').value = 'single';
    $('responseColumn').value = 'valor';
    $('treatmentColumn').value = 'tratamento';
    $('blockColumn').value = 'bloco';
    updateFieldVisibility();
    const rows = [
      {bloco:'B1', tratamento:'T1', valor:58.2}, {bloco:'B1', tratamento:'T2', valor:61.4}, {bloco:'B1', tratamento:'T3', valor:66.8}, {bloco:'B1', tratamento:'T4', valor:64.7},
      {bloco:'B2', tratamento:'T1', valor:57.6}, {bloco:'B2', tratamento:'T2', valor:60.1}, {bloco:'B2', tratamento:'T3', valor:66.4}, {bloco:'B2', tratamento:'T4', valor:63.1},
      {bloco:'B3', tratamento:'T1', valor:59.4}, {bloco:'B3', tratamento:'T2', valor:62.0}, {bloco:'B3', tratamento:'T3', valor:67.2}, {bloco:'B3', tratamento:'T4', valor:65.9},
      {bloco:'B4', tratamento:'T1', valor:59.7}, {bloco:'B4', tratamento:'T2', valor:63.6}, {bloco:'B4', tratamento:'T3', valor:68.9}, {bloco:'B4', tratamento:'T4', valor:66.1}
    ]
    renderEditableTable(['bloco','tratamento','valor'], rows);
    notify('Exemplo DBC carregado.', 'success');
  }

  function splitColumns(value) {
    return String(value || '').split(',').map((s) => s.trim()).filter(Boolean);
  }

  function unique(arr) {
    return [...new Set(arr.filter(Boolean))];
  }

  function format(v) {
    if (v == null || Number.isNaN(Number(v))) return '-';
    return Number(v).toLocaleString('pt-BR', {maximumFractionDigits: 4});
  }

  function labelFor(key) {
    const map = {
      source:'FV', df:'GL', sum_sq:'SQ', mean_sq:'QM', f_calc:'F calc', f_5:'F 5%', f_1:'F 1%', p_value:'p', significance:'Sig.',
      treatment:'Tratamento', mean:'Media', n:'n', sd:'DP', group:'Grupo'
    };
    return map[key] || key;
  }

  document.addEventListener('DOMContentLoaded', init);
})();
