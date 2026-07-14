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
  let currentResult = null;
  let currentRegressionPayload = null;

  const unlockedSteps = new Set(['modelo', 'dados']);
  let currentStep = 'modelo';

  function init() {
    const savedApi = localStorage.getItem('solver_api_base_url') || window.SOLVER_API_BASE_URL || '';
    apiInput.value = savedApi;
    bindViewSwitch();
    bindFormatosModal();
    bindStepper();
    bindActions();
    bindTypeGrid();
    selectExperimentType('DBC');
    testApi(false);
    updateExportAvailability(null);
    if (window.location.hash === '#analisar') showApp();
  }

  function bindViewSwitch() {
    $('heroOpenApp').addEventListener('click', showApp);
    $('navOpenApp').addEventListener('click', showApp);
    $('navBackToSite').addEventListener('click', showLanding);
    // [FIX P0-7] resultados.html e index.html sao paginas separadas agora; o
    // logo tem href="index.html" e deve navegar normalmente. Antes, este handler
    // dava preventDefault() e chamava showLanding() (que so alterna a secao
    // "view-landing" escondida DENTRO desta mesma pagina), entao o clique nunca
    // saia do resultados.html e parecia nao fazer nada.
  }

  function bindModal(modalId, openBtnIds, closeBtnId) {
    const modal = $(modalId);
    if (!modal) return;
    const openModal = (event) => {
      if (event) event.preventDefault();
      if (typeof modal.showModal === 'function') modal.showModal();
      else modal.setAttribute('open', 'open');
    };
    const closeModal = () => {
      if (typeof modal.close === 'function') modal.close();
      else modal.removeAttribute('open');
    };
    openBtnIds.forEach((id) => {
      const btn = $(id);
      if (btn) btn.addEventListener('click', openModal);
    });
    const closeBtn = $(closeBtnId);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (event) => {
      if (event.target === modal) closeModal();
    });
  }

  function bindFormatosModal() {
    bindModal('formatosModal', ['openFormatosModalNav', 'openFormatosModalHero'], 'closeFormatosModal');
    bindModal('metodologiaModal', ['openMetodologiaModal'], 'closeMetodologiaModal');
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

  function resetAnalysis() {
    // Limpa dados carregados, resultado anterior e erro, e volta ao passo 1.
    // Sem isso, um erro (ex.: opcao errada de delineamento) obrigava a voltar
    // etapa por etapa manualmente para tentar de novo.
    uploadedRows = [];
    currentResult = null;
    currentRegressionPayload = null;
    currentHeaders = ['bloco', 'tratamento', 'valor'];
    $('fileInput').value = '';
    renderEditableTable(currentHeaders, []);
    $('dataTableTools').style.display = 'none';
    $('dataTableWrap').style.display = 'none';
    $('rowCount').textContent = 'Nenhuma linha carregada.';
    $('dataErrorMsg').textContent = '';
    $('dataErrorMsg').classList.add('hidden');
    $('restartAnalysis').classList.add('hidden');
    $('results').classList.add('hidden');
    $('emptyResults').classList.remove('hidden');
    unlockedSteps.clear();
    unlockedSteps.add('modelo');
    unlockedSteps.add('dados');
    updateExportAvailability(null);
    goToStep('modelo');
    notify('Nova analise iniciada.', 'success');
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
    $('newAnalysisBtn').addEventListener('click', resetAnalysis);
    $('restartAnalysis').addEventListener('click', resetAnalysis);

    $('comparisonTestPost').addEventListener('change', () => {
      const isRegression = $('comparisonTestPost').value === 'regression';
      $('regressionDegreePostWrap').classList.toggle('hidden', !isRegression);
    });

    $('downloadPdf').addEventListener('click', (event) => downloadExport('/api/export/pdf', 'solver-relatorio.pdf', null, event.currentTarget));
    $('downloadExcel').addEventListener('click', (event) => downloadExport('/api/export/excel', 'solver-resultados.xlsx', null, event.currentTarget));
    $('downloadPng').addEventListener('click', (event) => downloadRegressionExport('/api/export/regression-plot?fmt=png', 'solver-regressao.png', event.currentTarget));
    $('downloadPlotPdf').addEventListener('click', (event) => downloadRegressionExport('/api/export/regression-plot?fmt=pdf', 'solver-regressao.pdf', event.currentTarget));

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
    // Trocar de modo sempre invalida dados do modo anterior - evita que uma
    // tentativa de upload com erro deixe uploadedRows "preso" e contamine a
    // proxima analise (manual ou de outro arquivo).
    uploadedRows = [];
    if (mode === 'upload') {
      $('dataTableTools').style.display = 'none';
      $('dataTableWrap').style.display = 'none';
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

  // Sem etapa manual de mapeamento: se os nomes das colunas do arquivo nao
  // baterem com a configuracao, tenta encaixar automaticamente por
  // aproximacao (fuzzyMatches) e segue direto para a analise. Se algo
  // essencial realmente nao existir no arquivo, o backend retorna um erro
  // claro ("Colunas ausentes na base: ...") pelo caminho normal de erro.
  function autoMapColumns(headers) {
    const usedHeaders = new Set();
    requiredColumnFields().forEach((f) => {
      const configured = $(f.id).value.trim();
      if (configured && headers.includes(configured)) {
        usedHeaders.add(configured);
        return;
      }
      const guess = headers.find((h) => !usedHeaders.has(h) && fuzzyMatches(h, f.id));
      if (guess) {
        $(f.id).value = guess;
        usedHeaders.add(guess);
      }
    });

    // factorColumns (fatorial/parcelas subdivididas) fica de fora do loop acima porque
    // e um campo de multiplos valores, nao tem hint de fuzzyMatches. Sem isso, um
    // arquivo com nomes de fator diferentes do default ("fator_a,fator_b" etc.) sempre
    // dava "Colunas ausentes na base", mesmo com os fatores presentes no arquivo.
    const type = $('analysisType').value;
    if (type === 'factorial' || type === 'split_plot') {
      const configuredFactors = splitColumns($('factorColumns').value);
      const allConfigured = configuredFactors.length === 2 && configuredFactors.every((f) => headers.includes(f));
      if (allConfigured) {
        configuredFactors.forEach((f) => usedHeaders.add(f));
      } else {
        const leftovers = headers.filter((h) => !usedHeaders.has(h));
        if (leftovers.length >= 2) {
          const picked = leftovers.slice(0, 2);
          $('factorColumns').value = picked.join(',');
          picked.forEach((h) => usedHeaders.add(h));
        }
      }
    }
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

  function startLoadingSequence(btn) {
    // Antes o texto do botao trocava entre varias mensagens a cada 900ms, mudando o
    // tamanho do botao (jitter) - ja existe o indicador "Processando..." fixo na barra
    // de status, entao o botao so precisa sinalizar estado ocupado com texto estatico.
    if (!btn) return () => {};
    const original = btn.textContent;
    btn.disabled = true;
    btn.classList.add('is-loading');
    btn.textContent = 'Executando...';
    return () => {
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
      autoMapColumns(currentHeaders);
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
      currentResult = json;
      currentRegressionPayload = json?.regression ? payload : null;
      renderResults(json);
      setupComparisonPanel(json);
      updateExportAvailability(json);
      unlockResultsAndExports();
      goToStep('resultados');
      setApiStatus('API ativa', 'ok');
    } catch (err) {
      setApiStatus('Erro na analise', 'err');
      const msg = err.message || 'Erro ao rodar analise.';
      notify(msg, 'error');
      $('dataErrorMsg').textContent = msg;
      $('dataErrorMsg').classList.remove('hidden');
      $('restartAnalysis').classList.remove('hidden');
    } finally {
      stopLoading();
    }
  }

  function renderResults(result) {
    currentResult = result || null;
    updateExportAvailability(currentResult);
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
    renderAnovaStatusBanner(result?.anova);          // [FIX P0-5]
    renderRecommendations(result?.recommendations || []);
    renderRegression(result?.regression);
    // checkDoseAdvisory() removido: a opcao "Regressao" ja fica disponivel direto no
    // dropdown "Teste de comparacao" (runFactorComparison/runComparison), entao o
    // banner separado sugerindo trocar o tipo de analise inteiro ficava redundante.
    // Nota: o preview do hero (#previewCv/#previewF/#previewR2/#previewDose e o
    // mini-anova) e' um exemplo fixo, ilustrativo, escrito direto no HTML - ele
    // nunca deve refletir o resultado real do usuario, entao propositalmente
    // nao atualizamos esses elementos aqui.
  }

  function sigPill(value) {
    if (value == null || value === '-' || value === '—') return '<span class="sig-dash">-</span>';
    const cls = value === '1%' ? 'sig-1' : value === '5%' ? 'sig-5' : 'sig-ns';
    const label = value === '1%' ? 'p < 0,01' : value === '5%' ? 'p < 0,05' : 'n.s.';
    return `<span class="sig-pill ${cls}">${label}</span>`;
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

  // [FIX P0-5] O backend ja devolve anova.model_notes e anova.residual_is_singular.
  // O frontend descartava as duas — o usuario nunca via os avisos que o proprio
  // motor estatistico emitiu.
  function renderAnovaStatusBanner(anova) {
    const old = document.getElementById('anovaStatusBanner');
    if (old) old.remove();
    if (!anova) return;

    const singular = anova.residual_is_singular === true;
    const notes = Array.isArray(anova.model_notes) ? anova.model_notes.filter(Boolean) : [];
    if (!singular && !notes.length) return;

    const table = document.getElementById('anovaTable');
    if (!table || !table.parentNode) return;

    const box = document.createElement('div');
    box.id = 'anovaStatusBanner';
    box.className = singular ? 'solver-banner is-danger' : 'solver-banner is-info';
    box.setAttribute('role', singular ? 'alert' : 'note');

    if (singular) {
      const t = document.createElement('p');
      t.className = 'solver-banner-title';
      t.textContent = 'Resultado indeterminado — isto NÃO é "não significativo"';
      box.appendChild(t);

      const b = document.createElement('p');
      b.textContent =
        'O quadrado médio do resíduo é praticamente zero. Como o teste F é '
        + 'QM(tratamento) ÷ QM(resíduo), ele vira uma divisão por zero: o F não existe. '
        + 'Isso não quer dizer que não há efeito — quer dizer que os dados não têm '
        + 'variabilidade dentro das células do experimento. Nenhuma conclusão estatística '
        + 'pode ser tirada. Confira a coleta.';
      box.appendChild(b);
    }

    notes.forEach((n) => {
      const p = document.createElement('p');
      p.className = 'solver-banner-note';
      p.textContent = n;
      box.appendChild(p);
    });

    table.parentNode.insertBefore(box, table);
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
    const degreeLabels = {1: 'Linear', 2: 'Quadrático', 3: 'Cúbico'};
    const superscripts = {2: '²', 3: '³', 4: '⁴'};
    function buildEquation(coeffs) {
      if (!coeffs || !coeffs.length) return '';
      const parts = [format(coeffs[0])];
      for (let power = 1; power < coeffs.length; power++) {
        const coef = coeffs[power];
        const sign = coef >= 0 ? '+' : '−';
        const varTerm = power === 1 ? 'x' : `x${superscripts[power] || ('^' + power)}`;
        parts.push(`${sign} ${format(Math.abs(coef))}${varTerm}`);
      }
      return 'ŷ = ' + parts.join(' ');
    }
    [
      `Modelo: ${degreeLabels[reg.selected_degree] || `Grau ${reg.selected_degree}`}`,
      `R²: ${format(selected.r2)}`,
      `R² ajustado: ${format(selected.adj_r2)}`,
      buildEquation(selected.coefficients),
      selected.optimum ? `Ótimo: ${format(selected.optimum.x)} → ${format(selected.optimum.y)}` : ''
    ].filter(Boolean).forEach((text) => {
      const span = document.createElement('span');
      span.textContent = text;
      summary.appendChild(span);
    });

    if (reg.recommendation) {
      const note = document.createElement('p');
      const overridden = reg.recommendation.includes('não foi o melhor');
      note.className = overridden ? 'regression-note warning' : 'regression-note';
      note.textContent = reg.recommendation;
      summary.appendChild(note);
    }

    const ctx = $('regressionChart');
    if (regressionChart) regressionChart.destroy();

    // Cores lidas das CSS custom properties do proprio site, para o grafico sempre
    // usar a paleta atual da marca (antes eram hex fixos de uma paleta antiga que
    // ficou destoando quando o tema mudou para o verde-azulado/teal atual).
    const rootStyles = getComputedStyle(document.documentElement);
    const cssVar = (name, fallback) => (rootStyles.getPropertyValue(name) || '').trim() || fallback;
    const hexToRgba = (hex, alpha) => {
      const h = String(hex).replace('#', '');
      const r = parseInt(h.substring(0, 2), 16) || 0;
      const g = parseInt(h.substring(2, 4), 16) || 0;
      const b = parseInt(h.substring(4, 6), 16) || 0;
      return `rgba(${r},${g},${b},${alpha})`;
    };
    const cBrand = cssVar('--brand', '#339D89');
    const cBrandDeep = cssVar('--brand-deep', '#194B41');
    const cBrandBright = cssVar('--brand-bright', '#88D8C9');
    const cAccent = cssVar('--accent', '#D16D2E');
    const cTextL1 = cssVar('--text-l1', '#16423A');
    const cTextL2 = cssVar('--text-l2', '#339D89');
    const cSurfaceLine = cssVar('--surface-line', '#E7ECE9');

    const canvasCtx = ctx.getContext && ctx.getContext('2d');
    let fillGradient = hexToRgba(cBrand, 0.16);
    if (canvasCtx) {
      const grad = canvasCtx.createLinearGradient(0, 0, 0, ctx.height || 260);
      grad.addColorStop(0, hexToRgba(cBrand, 0.28));
      grad.addColorStop(1, hexToRgba(cBrand, 0.02));
      fillGradient = grad;
    }

    const datasets = [
      {
        label: 'Observado',
        data: (reg.points || []).map((p) => ({x: p.x, y: p.y})),
        backgroundColor: cBrandBright,
        borderColor: cBrandDeep,
        borderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        pointHoverBorderWidth: 2
      },
      {
        label: 'Ajustado',
        type: 'line',
        data: (reg.fitted_curve || []).map((p) => ({x: p.x, y: p.y})),
        pointRadius: 0,
        borderWidth: 3,
        borderColor: cBrand,
        backgroundColor: fillGradient,
        fill: true,
        tension: 0.35
      }
    ];
    const optimum = selected.optimum;
    if (optimum && optimum.x != null) {
      datasets.push({
        label: 'Ponto ótimo',
        data: [{x: optimum.x, y: optimum.y}],
        backgroundColor: cAccent,
        borderColor: '#ffffff',
        borderWidth: 2.5,
        pointRadius: 7,
        pointHoverRadius: 9,
        pointStyle: 'rectRot',
        showLine: false
      });
    }

    regressionChart = new Chart(ctx, {
      type: 'scatter',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode: 'nearest', intersect: false},
        plugins: {
          legend: {
            position: 'bottom',
            labels: {usePointStyle: true, pointStyle: 'circle', color: cTextL1, font: {family: "'Montserrat', sans-serif", size: 12.5, weight: '600'}, boxWidth: 9, boxHeight: 9, padding: 18}
          },
          tooltip: {
            backgroundColor: cBrandDeep,
            titleFont: {family: "'Montserrat', sans-serif", size: 12.5, weight: '700'},
            bodyFont: {family: "'Open Sans', sans-serif", size: 12},
            padding: 10,
            cornerRadius: 10,
            displayColors: false,
            callbacks: {
              label: (item) => `${format(item.parsed.x)} \u2192 ${format(item.parsed.y)}`
            }
          }
        },
        scales: {
          x: {
            title: {display: true, text: reg.x_label || 'x', color: cTextL1, font: {family: "'Montserrat', sans-serif", size: 12.5, weight: '700'}},
            grid: {color: cSurfaceLine, drawTicks: false},
            ticks: {color: cTextL2, font: {family: "'Open Sans', sans-serif", size: 11.5}, padding: 8}
          },
          y: {
            title: {display: true, text: reg.y_label || 'Resposta', color: cTextL1, font: {family: "'Montserrat', sans-serif", size: 12.5, weight: '700'}},
            grid: {color: cSurfaceLine, drawTicks: false},
            ticks: {color: cTextL2, font: {family: "'Open Sans', sans-serif", size: 11.5}, padding: 8}
          }
        }
      }
    });
  }

  function extractSingleColumn(rawSource) {
    if (!rawSource || rawSource.includes(':')) return null;
    const m = rawSource.match(/Q\("([^"]+)"\)/);
    return m ? m[1] : null;
  }

  function getSourceRow(result, rawSource) {
    return (result?.anova?.table || []).find((row) => row.raw_source === rawSource || row.source === rawSource) || null;
  }

  function isSignificantSource(result, rawSource) {
    const row = getSourceRow(result, rawSource);
    return !!row && (row.significance === '1%' || row.significance === '5%');
  }

  function updateExportAvailability(result) {
    const hasRegression = !!(result && result.regression && result.regression.selected_model);
    ['downloadPng', 'downloadPlotPdf'].forEach((id) => {
      const btn = $(id);
      if (!btn) return;
      btn.disabled = !hasRegression;
      btn.classList.toggle('disabled', !hasRegression);
      btn.title = hasRegression ? '' : 'Disponível somente depois de uma análise de regressão.';
      btn.setAttribute('aria-disabled', hasRegression ? 'false' : 'true');
    });
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
      const raw = `C(Q(\"${result?.meta?.treatment_column || 'tratamento'}\"))`;
      const sig = isSignificantSource(result, raw);
      btn.textContent = 'Comparar medias';
      btn.disabled = !sig;
      btn.title = sig ? '' : 'A comparação de médias só é liberada quando Tratamentos é significativo no teste F.';
      btn.addEventListener('click', () => runComparison(null, null, btn));
      container.appendChild(btn);
      // [FIX P0-5] O pos-teste pode ser bloqueado por DOIS motivos diferentes, e o app
      // tratava os dois como um so:
      //   (a) F calculado e NAO significativo -> conclusao valida: sem efeito detectado
      //   (b) F INDETERMINADO (residuo nulo)  -> nenhuma conclusao e possivel
      const indeterminate = result?.anova?.residual_is_singular === true;
      if (!sig) {
        const p = document.createElement('p');
        p.className = indeterminate ? 'small-note is-danger' : 'small-note';
        p.textContent = indeterminate
          ? 'Teste F indeterminado (resíduo nulo): não é possível afirmar nem efeito, nem ausência de efeito. O pós-teste está bloqueado porque não existe erro experimental para servir de referência.'
          : 'Tratamentos não foi significativo no teste F; o pós-teste fica bloqueado para evitar conclusão indevida.';
        container.appendChild(p);
      }
      return;
    }

    let any = false;
    let anySig = false;
    (result?.anova?.table || []).forEach((row) => {
      if (row.source === 'Total') return;
      // Blocos/Linhas/Colunas sao controle local (nao tratamento): nao faz sentido
      // pos-teste de comparacao de medias nessas fontes, entao nao mostramos o botao.
      if (row.source === 'Blocos' || row.source === 'Linhas' || row.source === 'Colunas') return;
      const col = extractSingleColumn(row.raw_source);
      if (!col) return;
      any = true;
      const sig = row.significance === '1%' || row.significance === '5%';
      if (sig) anySig = true;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn';
      btn.textContent = `Comparar: ${row.source}`;
      btn.disabled = !sig;
      btn.title = sig ? '' : 'So e possivel comparar fatores significativos no teste F.';
      const hasFactorComparisons = Array.isArray(result?.factor_comparisons) && result.factor_comparisons.length > 0;
      if (hasFactorComparisons) {
        btn.addEventListener('click', () => runFactorComparison(col, row.source, btn));
      } else {
        btn.addEventListener('click', () => runComparison(col, row.source, btn));
      }
      container.appendChild(btn);
    });
    if (!any || !anySig) {
      // [FIX P0-5] Mesma distincao do ramo 'single': residuo singular e' indeterminado,
      // nao "nao significativo".
      const indeterminate = result?.anova?.residual_is_singular === true;
      const p = document.createElement('p');
      p.className = indeterminate ? 'small-note is-danger' : 'small-note';
      p.textContent = indeterminate
        ? 'Teste F indeterminado (resíduo nulo): não é possível afirmar nem efeito, nem ausência de efeito para nenhum fator. O pós-teste está bloqueado porque não existe erro experimental para servir de referência.'
        : 'Nenhum fator elegivel foi significativo no teste F - sem comparacao de medias recomendada.';
      container.appendChild(p);
    }
  }

  async function runFactorComparison(col, label, btn) {
    // Antes usava o resultado pre-computado da analise inicial (sempre com o teste
    // default), entao trocar o teste no dropdown (inclusive "Regressao") nao tinha
    // nenhum efeito nos botoes "Comparar: <fator>" de fatorial/parcelas subdivididas.
    // Agora re-executa a comparacao com o teste atualmente selecionado, igual ao
    // fluxo de comparacao simples (runComparison).
    if ($('comparisonTestPost').value === 'regression') {
      return runRegressionFromComparison(col, btn);
    }
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadFromUi();
    payload.comparison_test = $('comparisonTestPost').value;
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
      const entry = (json?.factor_comparisons || []).find((f) => f.factor === col);
      if (!entry) {
        notify('Comparacao de medias indisponivel para este fator com o teste selecionado.', 'error');
        return;
      }
      currentResult = json;
      $('meansResultBox').classList.remove('hidden');
      const errorLabel = entry.error_used === 'a' ? ', Erro (a)' : entry.error_used === 'b' ? ', Erro (b)' : '';
      $('meansFactorLabel').textContent = `Medias e grupos - ${label} (${entry.test}${errorLabel})`;
      renderMeansTable(entry.levels || []);
      setApiStatus('API ativa', 'ok');
    } catch (err) {
      setApiStatus('Erro na comparacao', 'err');
      notify(err.message || 'Erro ao comparar medias.', 'error');
    } finally {
      stopLoading();
    }
  }

  async function runComparison(colOverride, label, btn) {
    if ($('comparisonTestPost').value === 'regression') {
      return runRegressionFromComparison(colOverride, btn);
    }
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

  async function runRegressionFromComparison(colOverride, btn) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadFromUi();
    // [FIX P0-6] Nao sobrescrever analysis_type aqui: isso derrubava a ANOVA e as
    // medias da analise original (o backend zera o quadro de ANOVA quando
    // analysis_type=="regression"). O post-teste "Regressao" deve so ADICIONAR o
    // ajuste de dose sobre a analise ja feita (single/factorial/split_plot),
    // preservando o tipo original.
    payload.numeric_factor_column = colOverride || null;
    const degree = $('regressionDegreePost').value;
    payload.regression_degree = degree ? Number(degree) : null;
    const stopLoading = startLoadingSequence(btn, [
      'Ajustando regressao...',
      'Testando graus polinomiais...'
    ]);
    try {
      setApiStatus('Processando...', '');
      const res = await fetch(`${base}/api/analyze`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Erro na regressao');
      currentRegressionPayload = json?.regression ? payload : null;
      if (currentResult) {
        currentResult.regression = json?.regression || null;
        updateExportAvailability(currentResult);
      } else {
        updateExportAvailability({regression: json?.regression || null});
      }
      renderRegression(json?.regression);
      setApiStatus('API ativa', 'ok');
    } catch (err) {
      setApiStatus('Erro na regressao', 'err');
      notify(err.message || 'Erro ao rodar regressao.', 'error');
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

  function isMobileViewport() {
    return window.matchMedia && window.matchMedia('(max-width: 720px)').matches;
  }

  function ensurePdfExportOverlay() {
    let overlay = $('pdfExportOverlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'pdfExportOverlay';
    overlay.className = 'pdf-export-overlay hidden';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-live', 'polite');
    overlay.innerHTML = `
      <div class="pdf-export-sheet">
        <div class="pdf-export-handle"></div>
        <div class="pdf-export-head">
          <div class="pdf-export-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v6h5"/><path d="M9 14h6M9 17h4"/></svg>
          </div>
          <div class="pdf-export-copy">
            <p class="pdf-export-title" id="pdfExportTitle">Preparando PDF</p>
            <p class="pdf-export-subtitle" id="pdfExportSubtitle">Montando capa, ANOVA e recomendações.</p>
          </div>
          <button class="pdf-export-close" id="pdfExportClose" type="button" aria-label="Fechar">×</button>
        </div>
        <div class="pdf-export-preview" aria-hidden="true">
          <div class="pdf-page-thumb"><b>SOLVER</b><div class="pdf-page-line"></div><div class="pdf-page-line short"></div><div class="pdf-page-kpis"><i></i><i></i><i></i></div><div class="pdf-page-line"></div><div class="pdf-page-line short"></div></div>
          <div class="pdf-page-thumb"><b>ANOVA</b><div class="pdf-page-line"></div><div class="pdf-page-line"></div><div class="pdf-page-chart"></div><div class="pdf-page-line short"></div></div>
        </div>
        <div class="pdf-export-progress">
          <div class="pdf-progress-track"><div class="pdf-progress-fill" id="pdfProgressFill"></div></div>
          <span class="pdf-progress-value" id="pdfProgressValue">0%</span>
        </div>
        <ul class="pdf-export-steps">
          <li id="pdfStepCompile"><i></i><span>Compilando resultados</span></li>
          <li id="pdfStepCharts"><i></i><span>Inserindo gráficos e tabelas</span></li>
          <li id="pdfStepFinish"><i></i><span>Finalizando arquivo</span></li>
        </ul>
        <div class="pdf-export-actions hidden" id="pdfExportActions">
          <button class="btn solid" id="pdfExportDone" type="button">Fechar</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    $('pdfExportClose').addEventListener('click', () => overlay.classList.add('hidden'));
    $('pdfExportDone').addEventListener('click', () => overlay.classList.add('hidden'));
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay && !$('pdfExportActions').classList.contains('hidden')) overlay.classList.add('hidden');
    });
    return overlay;
  }

  function setPdfProgress(percent, title, subtitle, state = 'running') {
    const overlay = ensurePdfExportOverlay();
    overlay.classList.remove('hidden');
    const value = Math.max(0, Math.min(100, Math.round(percent)));
    $('pdfProgressFill').style.width = `${value}%`;
    $('pdfProgressValue').textContent = `${value}%`;
    if (title) $('pdfExportTitle').textContent = title;
    if (subtitle) $('pdfExportSubtitle').textContent = subtitle;
    $('pdfExportActions').classList.toggle('hidden', state !== 'done' && state !== 'error');
    const compile = $('pdfStepCompile');
    const charts = $('pdfStepCharts');
    const finish = $('pdfStepFinish');
    [compile, charts, finish].forEach((el) => el.classList.remove('done', 'active'));
    if (value >= 25) compile.classList.add('done'); else compile.classList.add('active');
    if (value >= 65) charts.classList.add('done'); else if (value >= 25) charts.classList.add('active');
    if (value >= 100) finish.classList.add('done'); else if (value >= 65) finish.classList.add('active');
    if (state === 'error') {
      $('pdfExportTitle').textContent = 'Não foi possível gerar o PDF';
      $('pdfExportSubtitle').textContent = 'Confira a conexão com o backend e tente novamente.';
    }
  }

  function startMobilePdfProgress(filename) {
    if (!isMobileViewport()) return () => {};
    let progress = 8;
    setPdfProgress(progress, 'Preparando PDF', `Gerando ${filename} sem alterar sua análise.`);
    const timer = setInterval(() => {
      progress = Math.min(88, progress + Math.ceil(Math.random() * 12));
      setPdfProgress(progress, 'Preparando PDF', progress < 60 ? 'Compilando resultados e ANOVA.' : 'Inserindo gráficos, médias e recomendações.');
    }, 420);
    return (state = 'done') => {
      clearInterval(timer);
      if (state === 'done') {
        setPdfProgress(100, 'PDF pronto para baixar', 'O download foi iniciado automaticamente.', 'done');
        window.setTimeout(() => ensurePdfExportOverlay().classList.add('hidden'), 2200);
      } else {
        setPdfProgress(progress, 'Não foi possível gerar o PDF', 'A exportação não foi concluída.', 'error');
      }
    };
  }

  async function downloadRegressionExport(endpoint, filename, button = null) {
    if (!currentResult?.regression?.selected_model) {
      notify('Gráfico disponível somente depois de rodar uma regressão.', 'error');
      updateExportAvailability(currentResult);
      return;
    }
    return downloadExport(endpoint, filename, currentRegressionPayload, button);
  }

  function setExportLoading(button, loading) {
    if (!button) return;
    const label = button.querySelector('b');
    if (loading) {
      button.dataset.originalLabel = label ? label.textContent : '';
      button.disabled = true;
      button.classList.add('loading');
      if (label) label.innerHTML = '<span class="btn-spinner"></span>Gerando...';
    } else {
      button.disabled = false;
      button.classList.remove('loading');
      if (label && button.dataset.originalLabel) label.textContent = button.dataset.originalLabel;
    }
  }

  async function downloadExport(endpoint, filename, payloadOverride = null, button = null) {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadOverride || payloadFromUi();
    const finishMobilePdfProgress = endpoint === '/api/export/pdf' ? startMobilePdfProgress(filename) : () => {};
    setExportLoading(button, true);
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
      finishMobilePdfProgress('done');
    } catch (err) {
      finishMobilePdfProgress('error');
      notify(err.message || 'Erro ao exportar.', 'error');
    } finally {
      setExportLoading(button, false);
    }
  }

  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    try {
      if (ext !== 'csv') {
        throw new Error('Formato não suportado. Envie um arquivo .csv separado por ponto e vírgula (;).');
      }
      const text = await file.text();
      let rows = parseCsv(text);
      rows = normalizeHeaders(rows);
      if (!rows.length) throw new Error('O arquivo nao tem linhas de dados.');
      uploadedRows = rows;
      currentHeaders = unique(Object.keys(rows[0] || {}));
      $('dataTableTools').style.display = 'none';
      $('dataTableWrap').style.display = 'none';
      $('dataErrorMsg').classList.add('hidden');
      autoMapColumns(currentHeaders);
      $('rowCount').textContent = `${rows.length} linha(s) carregada(s) de "${file.name}". Clique em Iniciar analise.`;
      notify('Arquivo carregado. Clique em Iniciar analise.', 'success');
    } catch (err) {
      notify(err.message || 'Erro ao ler arquivo.', 'error');
    }
  }

  function parseCsv(text) {
    const cleaned = text.replace(/^\uFEFF/, '').replace(/^ /, '');
    const firstLine = cleaned.split(/\r?\n/).find((line) => line.trim()) || '';
    if (!firstLine.includes(';')) {
      throw new Error('O arquivo não parece separado por ponto e vírgula (;). Confirme o formato e tente novamente.');
    }
    const sep = ';';
    const rows = [];
    let current = [];
    let value = '';
    let inQuotes = false;

    for (let i = 0; i < cleaned.length; i++) {
      const char = cleaned[i];
      const next = cleaned[i + 1];
      if (char === '"') {
        if (inQuotes && next === '"') {
          value += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === sep && !inQuotes) {
        current.push(value.trim());
        value = '';
      } else if ((char === '\n' || char === '\r') && !inQuotes) {
        if (char === '\r' && next === '\n') i++;
        current.push(value.trim());
        value = '';
        if (current.some((cell) => cell !== '')) rows.push(current);
        current = [];
      } else {
        value += char;
      }
    }
    current.push(value.trim());
    if (current.some((cell) => cell !== '')) rows.push(current);

    const headers = (rows.shift() || []).map((h) => h.trim());
    return rows.map((line) => {
      const obj = {};
      headers.forEach((h, i) => {
        const raw = line[i] ?? '';
        obj[h] = toNumericValue(raw);
      });
      return obj;
    });
  }

  function toNumericValue(raw) {
    const trimmed = String(raw ?? '').trim();
    if (trimmed === '') return trimmed;
    // Padrao brasileiro: milhar com '.', decimal com ',' (ex.: '1.234,56' ou '12,5').
    if (/^-?\d{1,3}(\.\d{3})*,\d+$/.test(trimmed) || /^-?\d+,\d+$/.test(trimmed)) {
      const normalized = trimmed.replace(/\./g, '').replace(',', '.');
      const n = Number(normalized);
      return Number.isNaN(n) ? raw : n;
    }
    // Numero simples (inteiro ou decimal com ponto), sem separador de milhar ambiguo.
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
      const n = Number(trimmed);
      return Number.isNaN(n) ? raw : n;
    }
    return raw;
  }

  function loadExampleData() {
    uploadedRows = [];
    hideColumnMapping();
    selectDataMode('manual');
    updateManualFieldsUI();

    const type = experimentType;
    const base = $('baseDesign').value || 'DBC';
    const response = $('responseColumn').value || 'valor';
    const treatment = $('treatmentColumn').value || 'tratamento';
    const block = $('blockColumn').value || 'bloco';
    const row = $('rowColumn').value || 'linha';
    const col = $('columnColumn').value || 'coluna';
    const numeric = $('numericFactorColumn').value.trim();
    const factors = splitColumns($('factorColumns').value);
    const jitter = [0, 0.8, -0.6, 1.1, -0.9, 0.5];
    const jit = (i) => jitter[i % jitter.length];
    const r1 = (v) => Math.round(v * 10) / 10;

    let headers = [];
    const rows = [];
    let label = 'DBC';

    if (type === 'DIC') {
      const means = { 1: 58.2, 2: 61.4, 3: 66.8, 4: 64.7 };
      headers = unique([treatment, response]);
      let k = 0;
      for (let t = 1; t <= 4; t++) {
        for (let rep = 1; rep <= 4; rep++) {
          rows.push({ [treatment]: `T${t}`, [response]: r1(means[t] + jit(k++)) });
        }
      }
      label = 'DIC';
    } else if (type === 'DQL') {
      const means = { 1: 58.4, 2: 61.6, 3: 66.9, 4: 64.5 };
      const n = 4;
      headers = unique([row, col, treatment, response]);
      let k = 0;
      for (let r = 1; r <= n; r++) {
        for (let c = 1; c <= n; c++) {
          const idx = ((r + c - 2) % n) + 1;
          rows.push({ [row]: `L${r}`, [col]: `C${c}`, [treatment]: `T${idx}`, [response]: r1(means[idx] + jit(k++)) });
        }
      }
      label = 'DQL';
    } else if (type === 'regression') {
      const doseCol = numeric || 'dose';
      const doses = [0, 50, 100, 150, 200];
      headers = unique([doseCol, response]);
      let k = 0;
      doses.forEach((dose) => {
        for (let rep = 1; rep <= 4; rep++) {
          const val = 40 + 0.5 * dose - 0.0013 * dose * dose;
          rows.push({ [doseCol]: dose, [response]: r1(val + jit(k++)) });
        }
      });
      label = 'Regressão';
    } else if (type === 'factorial') {
      const fa = factors[0] || 'fator_a';
      const fb = factors[1] || 'fator_b';
      const means = { '1-1': 58, '1-2': 64, '2-1': 63, '2-2': 72 };
      const blockDrift = [0, 0.8, -0.5, 1.2];
      headers = base === 'DBC' ? unique([block, fa, fb, treatment, response]) : unique([fa, fb, treatment, response]);
      let k = 0;
      for (let r = 1; r <= 4; r++) {
        for (let i = 1; i <= 2; i++) {
          for (let j = 1; j <= 2; j++) {
            const obj = {};
            if (base === 'DBC') obj[block] = `B${r}`;
            obj[fa] = `A${i}`;
            obj[fb] = `B${j}`;
            obj[treatment] = `A${i}B${j}`;
            obj[response] = r1(means[`${i}-${j}`] + blockDrift[r - 1] + jit(k++) * 0.3);
            rows.push(obj);
          }
        }
      }
      label = 'Fatorial';
    } else if (type === 'split_plot') {
      const fp = factors[0] || 'fator_parcela';
      const fs = factors[1] || 'fator_subparcela';
      const means = { '1-1': 55, '1-2': 61, '2-1': 63, '2-2': 71 };
      const blockDrift = [0, 0.6, -0.4, 1.0];
      headers = unique([block, fp, fs, treatment, response]);
      let k = 0;
      for (let r = 1; r <= 4; r++) {
        for (let i = 1; i <= 2; i++) {
          for (let j = 1; j <= 2; j++) {
            rows.push({
              [block]: `B${r}`, [fp]: `P${i}`, [fs]: `S${j}`, [treatment]: `P${i}S${j}`,
              [response]: r1(means[`${i}-${j}`] + blockDrift[r - 1] + jit(k++) * 0.3)
            });
          }
        }
      }
      label = 'Parcelas subdivididas';
    } else {
      // DBC (padrao) — produtividade de cultivares de soja (sc/ha), dataset real
      // (mesmo de examples/dbc_exemplo.csv). [FIX P0-4] O gerador anterior era
      // media[tratamento] + drift[bloco], ou seja, PERFEITAMENTE ADITIVO: SQ residuo
      // = 0, F indefinido, e o app publicava "nenhuma fonte foi significativa" para
      // todo visitante novo. Valores literais para reproduzir exatamente a tabela de
      // aceite (F=14,412 a 1% em Tratamentos, CV=6,21%).
      const valores = {
        B1: { 1: 52.4, 2: 54.6, 3: 60.9, 4: 58.0 },
        B2: { 1: 56.6, 2: 57.3, 3: 72.0, 4: 54.5 },
        B3: { 1: 59.6, 2: 59.0, 3: 80.9, 4: 59.7 },
        B4: { 1: 61.6, 2: 59.6, 3: 77.5, 4: 67.6 },
      };
      headers = unique([block, treatment, response]);
      for (let r = 1; r <= 4; r++) {
        for (let t = 1; t <= 4; t++) {
          rows.push({ [block]: `B${r}`, [treatment]: `T${t}`, [response]: valores[`B${r}`][t] });
        }
      }
      label = 'DBC';
    }

    renderEditableTable(headers, rows);
    updateMatrixSizeNote();
    notify(`Exemplo ${label} carregado.`, 'success');
  }

  function splitColumns(value) {
    return String(value || '').split(',').map((s) => s.trim()).filter(Boolean);
  }

  function unique(arr) {
    return [...new Set(arr.filter(Boolean))];
  }

  function format(v) {
    if (v == null || Number.isNaN(Number(v))) return '—';
    const num = Number(v);
    if (Math.abs(num) > 999999) {
      return num.toLocaleString('pt-BR', {notation: 'scientific', maximumFractionDigits: 4});
    }
    const isInt = Number.isInteger(num);
    return num.toLocaleString('pt-BR', {
      minimumFractionDigits: isInt ? 0 : 2,
      maximumFractionDigits: isInt ? 0 : 4,
    });
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
