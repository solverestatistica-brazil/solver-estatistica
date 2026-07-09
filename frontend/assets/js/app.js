/* Solver Frontend: aplicacao estatica para GitHub Pages. */
(() => {
  const $ = (id) => document.getElementById(id);
  const apiInput = $('apiBase');
  const apiStatus = $('apiStatus');
  const dataTable = $('dataTable');
  let currentHeaders = ['bloco', 'tratamento', 'valor'];
  let regressionChart = null;
  let uploadedRows = [];
  let experimentType = 'DBC';

  const unlockedSteps = new Set(['modelo', 'dados']);
  let currentStep = 'modelo';

  function init() {
    const savedApi = localStorage.getItem('solver_api_base_url') || window.SOLVER_API_BASE_URL || '';
    apiInput.value = savedApi;
    bindViewSwitch();
    bindStepper();
    bindActions();
    bindTypeGrid();
    selectExperimentType('DBC');
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
      selectExperimentType('regression');
      if (col) $('numericFactorColumn').value = col;
      goToStep('modelo');
      notify('Tipo de analise alterado para Regressao direta. Confira os campos e rode novamente.', 'success');
    });

    $('baseDesign').addEventListener('change', () => {
      selectExperimentType(experimentType);
    });
  }

  function bindTypeGrid() {
    document.querySelectorAll('.type-card').forEach((btn) => {
      btn.addEventListener('click', () => selectExperimentType(btn.dataset.type));
    });
  }

  function selectExperimentType(type) {
    experimentType = type;
    document.querySelectorAll('.type-card').forEach((btn) => {
      btn.classList.toggle('selected', btn.dataset.type === type);
    });

    const needsBase = type === 'factorial' || type === 'split_plot';
    $('baseDesignWrap').style.display = needsBase ? 'block' : 'none';
    const base = $('baseDesign').value || 'DBC';

    let design, analysisType;
    switch (type) {
      case 'DIC': design = 'DIC'; analysisType = 'single'; break;
      case 'DBC': design = 'DBC'; analysisType = 'single'; break;
      case 'DQL': design = 'DQL'; analysisType = 'single'; break;
      case 'factorial': design = base; analysisType = 'factorial'; break;
      case 'split_plot': design = base; analysisType = 'split_plot'; break;
      case 'regression': design = 'DIC'; analysisType = 'regression'; break;
      default: design = 'DBC'; analysisType = 'single';
    }
    $('design').value = design;
    $('analysisType').value = analysisType;

    applyDefaultColumnNames();
    updateFieldVisibility();
    updateManualFieldsUI();
    hideColumnMapping();
    if (!$('dataManualPanel').classList.contains('hidden')) generateManualTable();
  }

  function applyDefaultColumnNames() {
    $('responseColumn').value = $('responseColumn').value.trim() || 'valor';
    if (experimentType === 'regression') {
      $('numericFactorColumn').value = $('numericFactorColumn').value.trim() || 'dose';
      $('treatmentColumn').value = 'tratamento';
    } else if (experimentType === 'factorial') {
      $('treatmentColumn').value = 'tratamento';
      $('blockColumn').value = $('blockColumn').value.trim() || 'bloco';
      const current = splitColumns($('factorColumns').value);
      $('factorColumns').value = current.length === 2 ? current.join(',') : 'fator_a,fator_b';
    } else if (experimentType === 'split_plot') {
      $('treatmentColumn').value = 'tratamento';
      $('blockColumn').value = $('blockColumn').value.trim() || 'bloco';
      const current = splitColumns($('factorColumns').value);
      $('factorColumns').value = current.length === 2 ? current.join(',') : 'fator_parcela,fator_subparcela';
    } else {
      $('treatmentColumn').value = $('treatmentColumn').value.trim() || 'tratamento';
      $('blockColumn').value = $('blockColumn').value.trim() || 'bloco';
      $('rowColumn').value = $('rowColumn').value.trim() || 'linha';
      $('columnColumn').value = $('columnColumn').value.trim() || 'coluna';
    }
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

  // --- Campos numericos contextuais (modo manual) ---

  function numberField(id, label, value) {
    const wrap = document.createElement('label');
    const span = document.createElement('span');
    span.textContent = label;
    wrap.appendChild(span);
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '1';
    input.id = id;
    input.value = value;
    input.addEventListener('input', updateMatrixSizeNote);
    wrap.appendChild(input);
    return wrap;
  }

  function updateManualFieldsUI() {
    const box = $('manualFieldsDynamic');
    if (!box) return;
    box.innerHTML = '';
    const type = experimentType;
    const base = $('baseDesign').value || 'DBC';
    const grid = document.createElement('div');
    grid.className = 'manual-builder';

    if (type === 'DIC') {
      grid.appendChild(numberField('nTreatments', 'Nº de tratamentos', 4));
      grid.appendChild(numberField('nReps', 'Nº de repetições', 4));
    } else if (type === 'DBC') {
      grid.appendChild(numberField('nTreatments', 'Nº de tratamentos', 4));
      grid.appendChild(numberField('nBlocks', 'Nº de blocos', 4));
    } else if (type === 'DQL') {
      grid.appendChild(numberField('nTreatments', 'Nº de tratamentos (= linhas = colunas)', 4));
    } else if (type === 'factorial') {
      grid.appendChild(numberField('nFactorA', 'Níveis do Fator A', 2));
      grid.appendChild(numberField('nFactorB', 'Níveis do Fator B', 2));
      grid.appendChild(numberField('nBlocks', base === 'DBC' ? 'Nº de blocos' : 'Nº de repetições', 4));
    } else if (type === 'split_plot') {
      grid.appendChild(numberField('nFactorA', 'Níveis do fator parcela', 2));
      grid.appendChild(numberField('nFactorB', 'Níveis do fator subparcela', 2));
      grid.appendChild(numberField('nBlocks', 'Nº de blocos', 4));
    } else if (type === 'regression') {
      grid.appendChild(numberField('nTreatments', 'Nº de doses/níveis', 5));
      grid.appendChild(numberField('nBlocks', 'Repetições por dose', 4));
    }

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn solid';
    btn.id = 'generateTable';
    btn.textContent = 'Gerar tabela manual';
    btn.addEventListener('click', generateManualTable);
    grid.appendChild(btn);

    box.appendChild(grid);
    const note = document.createElement('p');
    note.className = 'small-note';
    note.id = 'matrixSizeNote';
    box.appendChild(note);
    updateMatrixSizeNote();
  }

  function numVal(id, fallback) {
    const el = $(id);
    if (!el) return fallback;
    return Number(el.value || fallback);
  }

  function updateMatrixSizeNote() {
    const note = $('matrixSizeNote');
    if (!note) return;
    const type = experimentType;
    const base = $('baseDesign').value || 'DBC';
    let text = '';
    if (type === 'DIC') {
      const t = numVal('nTreatments', 4), r = numVal('nReps', 4);
      text = `${t} tratamentos × ${r} repetições = ${t * r} linhas na matriz.`;
    } else if (type === 'DBC') {
      const t = numVal('nTreatments', 4), b = numVal('nBlocks', 4);
      text = `${t} tratamentos × ${b} blocos = ${t * b} linhas na matriz.`;
    } else if (type === 'DQL') {
      const t = numVal('nTreatments', 4);
      text = `${t} × ${t} = ${t * t} linhas (linhas × colunas × 1 tratamento por célula).`;
    } else if (type === 'factorial') {
      const a = numVal('nFactorA', 2), b = numVal('nFactorB', 2), r = numVal('nBlocks', 4);
      text = `${a} × ${b} × ${r} (fator A × fator B × ${base === 'DBC' ? 'blocos' : 'repetições'}) = ${a * b * r} linhas.`;
    } else if (type === 'split_plot') {
      const p = numVal('nFactorA', 2), s = numVal('nFactorB', 2), r = numVal('nBlocks', 4);
      text = `${p} × ${s} × ${r} (parcela × subparcela × blocos) = ${p * s * r} linhas.`;
    } else if (type === 'regression') {
      const d = numVal('nTreatments', 5), r = numVal('nBlocks', 4);
      text = `${d} doses × ${r} repetições = ${d * r} linhas.`;
    }
    note.textContent = text;
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
    setApiStatus('Verificando API...', '');
    try {
      const res = await fetch(`${base}/health`);
      if (!res.ok) throw new Error('status ' + res.status);
      setApiStatus('API ativa', 'ok');
      if (showSuccess) notify('Backend salvo e respondendo.', 'success');
    } catch (err) {
      setApiStatus('API indisponivel', 'err');
      if (showSuccess) notify('Nao consegui conectar. Verifique a URL do Render e o CORS.', 'error');
    }
  }

  function setApiStatus(text, type) {
    apiStatus.textContent = text;
    apiStatus.className = `status-pill ${type || ''}`;
    const dot = $('apiDot');
    if (dot) dot.className = `api-dot ${type === 'ok' ? 'ok' : type === 'err' ? 'err' : ''}`;
  }

  // --- Feedback de carregamento (spinner + mensagens dinamicas) ---

  function startLoadingSequence(btn, messages) {
    if (!btn) return () => {};
    const original = btn.textContent;
    btn.disabled = true;
    btn.classList.add('is-loading');
    let i = 0;
    btn.textContent = messages[0];
    const interval = setInterval(() => {
      i = (i + 1) % messages.length;
      btn.textContent = messages[i];
    }, 900);
    return () => {
      clearInterval(interval);
      btn.disabled = false;
      btn.classList.remove('is-loading');
      btn.textContent = original;
    };
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
    applyDefaultColumnNames();

    const type = experimentType;
    const base = $('baseDesign').value || 'DBC';
    const response = $('responseColumn').value || 'valor';
    const treatment = $('treatmentColumn').value || 'tratamento';
    const block = $('blockColumn').value || 'bloco';
    const row = $('rowColumn').value || 'linha';
    const col = $('columnColumn').value || 'coluna';
    const numeric = $('numericFactorColumn').value.trim();
    const factors = splitColumns($('factorColumns').value);

    let headers = [];
    const rows = [];

    if (type === 'DQL') {
      const n = numVal('nTreatments', 4);
      headers = unique([row, col, treatment, response]);
      for (let r = 1; r <= n; r++) {
        for (let c = 1; c <= n; c++) {
          const idx = ((r + c - 2) % n) + 1;
          rows.push({ [row]: `L${r}`, [col]: `C${c}`, [treatment]: `T${idx}`, [response]: '' });
        }
      }
    } else if (type === 'regression') {
      const nDoses = numVal('nTreatments', 5);
      const nReps = numVal('nBlocks', 4);
      const doseCol = numeric || 'dose';
      headers = unique([doseCol, response]);
      for (let i = 0; i < nDoses; i++) {
        for (let rep = 1; rep <= nReps; rep++) {
          rows.push({ [doseCol]: i * 50, [response]: '' });
        }
      }
    } else if (type === 'factorial') {
      const a = numVal('nFactorA', 2);
      const b = numVal('nFactorB', 2);
      const reps = numVal('nBlocks', 4);
      const fa = factors[0] || 'fator_a';
      const fb = factors[1] || 'fator_b';
      headers = base === 'DBC' ? unique([block, fa, fb, treatment, response]) : unique([fa, fb, treatment, response]);
      for (let r = 1; r <= reps; r++) {
        for (let i = 1; i <= a; i++) {
          for (let j = 1; j <= b; j++) {
            const obj = {};
            if (base === 'DBC') obj[block] = `B${r}`;
            obj[fa] = `A${i}`;
            obj[fb] = `B${j}`;
            obj[treatment] = `A${i}B${j}`;
            obj[response] = '';
            rows.push(obj);
          }
        }
      }
    } else if (type === 'split_plot') {
      const p = numVal('nFactorA', 2);
      const s = numVal('nFactorB', 2);
      const nBlk = numVal('nBlocks', 4);
      const fp = factors[0] || 'fator_parcela';
      const fs = factors[1] || 'fator_subparcela';
      headers = unique([block, fp, fs, treatment, response]);
      for (let r = 1; r <= nBlk; r++) {
        for (let i = 1; i <= p; i++) {
          for (let j = 1; j <= s; j++) {
            rows.push({ [block]: `B${r}`, [fp]: `P${i}`, [fs]: `S${j}`, [treatment]: `P${i}S${j}`, [response]: '' });
          }
        }
      }
    } else {
      // DIC ou DBC (fator unico)
      const nT = numVal('nTreatments', 4);
      const nRepOrBlock = numVal(type === 'DBC' ? 'nBlocks' : 'nReps', 4);
      headers = type === 'DBC' ? unique([block, treatment, response]) : unique([treatment, response]);
      for (let r = 1; r <= nRepOrBlock; r++) {
        for (let t = 1; t <= nT; t++) {
          const obj = {};
          if (type === 'DBC') obj[block] = `B${r}`;
          obj[treatment] = `T${t}`;
          obj[response] = '';
          rows.push(obj);
        }
      }
    }

    renderEditableTable(headers, rows);
    updateMatrixSizeNote();
  }

  function renderEditableTable(headers, rows) {
    currentHeaders = unique(headers);
    const responseCol = $('responseColumn').value || 'valor';
    dataTable.innerHTML = '';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    currentHeaders.forEach((h) => {
      const th = document.createElement('th');
      th.textContent = h;
      if (h === responseCol) th.classList.add('col-resp');
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
    const responseCol = $('responseColumn').value || 'valor';
    const tr = document.createElement('tr');
    currentHeaders.forEach((h) => {
      const td = document.createElement('td');
      if (h === responseCol) td.classList.add('col-resp');
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
    const stopLoading = startLoadingSequence($('runAnalysis'), [
      'Carregando dados...',
      'Executando ANOVA (teste F)...',
      'Calculando medias e organizando resultados...'
    ]);
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
      unlockResultsAndExports();
      goToStep('resultados');
      setApiStatus('API ativa', 'ok');
    } catch (err) {
      setApiStatus('Erro na analise', 'err');
      const msg = err.message || 'Erro ao rodar analise.';
      notify(msg, 'error');
      $('dataErrorMsg').textContent = msg;
      $('dataErrorMsg').classList.remove('hidden');
    } finally {
      stopLoading();
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

  function renderMeansTable(rows) {
    const table = $('meansTable');
    table.innerHTML = '';
    const columns = ['treatment', 'mean', 'n', 'sd', 'group'];
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    columns.forEach((c) => {
      const th = document.createElement('th');
      th.textContent = labelFor(c);
      trh.appendChild(th);
    });
    const barTh = document.createElement('th');
    barTh.textContent = 'Média (melhor → pior)';
    trh.appendChild(barTh);
    thead.appendChild(trh);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const n = rows.length;
    rows.forEach((row, idx) => {
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
      const barTd = document.createElement('td');
      const t = n > 1 ? 1 - idx / (n - 1) : 1;
      const pct = Math.round(15 + t * 85);
      const hue = Math.round(t * 120);
      barTd.innerHTML = `<div class="mean-bar-wrap"><div class="mean-bar" style="width:${pct}%;background:hsl(${hue},65%,45%)"></div></div>`;
      tr.appendChild(barTd);
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

    // Cores da marca Solver, para o grafico nao ficar com o azul/vermelho
    // padrao do Chart.js (destoando do resto do site).
    const datasets = [
      {
        label: 'Observado',
        data: (reg.points || []).map((p) => ({x: p.x, y: p.y})),
        backgroundColor: 'rgba(62,126,84,.55)',
        borderColor: '#3E7E54',
        borderWidth: 1.5,
        pointRadius: 4,
        pointHoverRadius: 5
      },
      {
        label: 'Ajustado',
        type: 'line',
        data: (reg.fitted_curve || []).map((p) => ({x: p.x, y: p.y})),
        pointRadius: 0,
        borderWidth: 2.5,
        borderColor: '#24492E',
        backgroundColor: 'rgba(36,73,46,.08)',
        tension: 0.15
      }
    ];
    const optimum = selected.optimum;
    if (optimum && optimum.x != null) {
      datasets.push({
        label: 'Ponto ótimo',
        data: [{x: optimum.x, y: optimum.y}],
        backgroundColor: '#C2703D',
        borderColor: '#ffffff',
        borderWidth: 2,
        pointRadius: 6,
        pointHoverRadius: 7,
        showLine: false
      });
    }

    regressionChart = new Chart(ctx, {
      type: 'scatter',
      data: { datasets },
      options: {
        responsive: true,
        plugins: {legend: {position: 'bottom', labels: {color: '#5C6D64', font: {family: 'Montserrat'}}}},
        scales: {
          x: {title: {display: true, text: reg.x_label || 'x', color: '#5C6D64'}, grid: {color: '#E7ECE9'}, ticks: {color: '#5C6D64'}},
          y: {title: {display: true, text: reg.y_label || 'Resposta', color: '#5C6D64'}, grid: {color: '#E7ECE9'}, ticks: {color: '#5C6D64'}}
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
      btn.addEventListener('click', () => runComparison(null, null, btn));
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
      btn.addEventListener('click', () => runComparison(col, row.source, btn));
      container.appendChild(btn);
    });
    if (!any) {
      const p = document.createElement('p');
      p.className = 'small-note';
      p.textContent = 'Nenhum fator elegivel foi significativo no teste F - sem comparacao de medias recomendada.';
      container.appendChild(p);
    }
  }

  async function runComparison(colOverride, label, btn) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadFromUi();
    payload.comparison_test = $('comparisonTestPost').value;
    if (colOverride) payload.treatment_column = colOverride;
    const stopLoading = startLoadingSequence(btn, [
      'Comparando medias...',
      'Aplicando teste de agrupamento...'
    ]);
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
      renderMeansTable(json?.means?.treatment_means || []);
      setApiStatus('API ativa', 'ok');
    } catch (err) {
      setApiStatus('Erro na comparacao', 'err');
      notify(err.message || 'Erro ao comparar medias.', 'error');
    } finally {
      stopLoading();
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
    selectExperimentType('DBC');
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
