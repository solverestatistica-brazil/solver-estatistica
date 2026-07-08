/* Solver Frontend: aplicação estática para GitHub Pages. */
(() => {
  const $ = (id) => document.getElementById(id);
  const apiInput = $('apiBase');
  const apiStatus = $('apiStatus');
  const dataTable = $('dataTable');
  let currentHeaders = ['bloco', 'tratamento', 'valor'];
  let currentResult = null;
  let regressionChart = null;

  function init() {
    const savedApi = localStorage.getItem('solver_api_base_url') || window.SOLVER_API_BASE_URL || '';
    apiInput.value = savedApi;
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
        $(`tab-${btn.dataset.tab}`).classList.add('active');
      });
    });
  }

  function bindActions() {
    $('saveApi').addEventListener('click', () => {
      localStorage.setItem('solver_api_base_url', cleanApiBase(apiInput.value));
      testApi(true);
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
    ['design','analysisType'].forEach((id) => $(id).addEventListener('change', generateManualTable));
  }

  function cleanApiBase(value) {
    return String(value || '').trim().replace(/\/$/, '');
  }

  async function testApi(showSuccess) {
    const base = cleanApiBase(apiInput.value);
    if (!base) {
      setApiStatus('API não configurada', 'err');
      return;
    }
    try {
      const res = await fetch(`${base}/health`);
      if (!res.ok) throw new Error('status ' + res.status);
      setApiStatus('API online', 'ok');
      if (showSuccess) notify('Backend salvo e respondendo.', 'success');
    } catch (err) {
      setApiStatus('API sem resposta', 'err');
      if (showSuccess) notify('Não consegui conectar. Verifique a URL do Render e o CORS.', 'error');
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
    actionTh.textContent = 'Ações';
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
      regression_degree: degree ? Number(degree) : null,
      goal: $('goal').value,
      alpha: 0.05,
      data: tableToRows()
    };
  }

  async function runAnalysis() {
    const base = cleanApiBase(apiInput.value);
    if (!base) return notify('Configure primeiro a URL do backend no Render.', 'error');
    const payload = payloadFromUi();
    if (!payload.data.length) return notify('Insira ou carregue dados antes de analisar.', 'error');
    try {
      setApiStatus('Processando...', '');
      const res = await fetch(`${base}/api/analyze`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Erro na análise');
      currentResult = json;
      renderResults(json);
      openTab('resultados');
      setApiStatus('API online', 'ok');
    } catch (err) {
      setApiStatus('Erro na análise', 'err');
      notify(err.message || 'Erro ao rodar análise.', 'error');
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

    renderSimpleTable('anovaTable', ['source','df','sum_sq','mean_sq','f_calc','f_5','f_1','p_value','significance'], result?.anova?.table || []);
    renderSimpleTable('meansTable', ['treatment','mean','n','sd','group'], result?.means?.treatment_means || []);
    renderRecommendations(result?.recommendations || []);
    renderRegression(result?.regression);

    const firstF = (result?.anova?.table || []).find((r) => r.f_calc != null);
    $('previewCv').textContent = cv == null ? '—' : `${format(cv)}%`;
    $('previewF').textContent = firstF ? format(firstF.f_calc) : '—';
    const reg = result?.regression?.selected_model;
    $('previewR2').textContent = reg?.r2 == null ? '—' : format(reg.r2);
    const opt = reg?.optimum;
    $('previewDose').textContent = opt?.x == null ? '—' : `${format(opt.x)} ${result?.regression?.x_label || ''}`;
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
        td.textContent = row[c] == null ? '—' : (typeof row[c] === 'number' ? format(row[c]) : row[c]);
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
      `R²: ${format(selected.r2)}`,
      `R² ajustado: ${format(selected.adj_r2)}`,
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
      if (ext === 'csv') {
        const text = await file.text();
        const rows = parseCsv(text);
        renderEditableTable(Object.keys(rows[0] || {}), rows);
      } else if (['xlsx','xls'].includes(ext)) {
        const buffer = await file.arrayBuffer();
        const workbook = XLSX.read(buffer, {type:'array'});
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(sheet, {defval:''});
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
    const sep = text.includes(';') ? ';' : ',';
    const lines = text.trim().split(/\r?\n/).filter(Boolean);
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
    $('design').value = 'DBC';
    $('analysisType').value = 'single';
    $('responseColumn').value = 'valor';
    $('treatmentColumn').value = 'tratamento';
    $('blockColumn').value = 'bloco';
    const rows = [
      {bloco:'B1', tratamento:'T1', valor:58.2}, {bloco:'B1', tratamento:'T2', valor:61.4}, {bloco:'B1', tratamento:'T3', valor:66.8}, {bloco:'B1', tratamento:'T4', valor:64.7},
      {bloco:'B2', tratamento:'T1', valor:57.6}, {bloco:'B2', tratamento:'T2', valor:60.1}, {bloco:'B2', tratamento:'T3', valor:66.4}, {bloco:'B2', tratamento:'T4', valor:63.1},
      {bloco:'B3', tratamento:'T1', valor:59.4}, {bloco:'B3', tratamento:'T2', valor:62.0}, {bloco:'B3', tratamento:'T3', valor:67.2}, {bloco:'B3', tratamento:'T4', valor:65.9},
      {bloco:'B4', tratamento:'T1', valor:59.7}, {bloco:'B4', tratamento:'T2', valor:63.6}, {bloco:'B4', tratamento:'T3', valor:68.9}, {bloco:'B4', tratamento:'T4', valor:66.1}
    ]
    renderEditableTable(['bloco','tratamento','valor'], rows);
    notify('Exemplo DBC carregado.', 'success');
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
    return Number(v).toLocaleString('pt-BR', {maximumFractionDigits: 4});
  }

  function labelFor(key) {
    const map = {
      source:'FV', df:'GL', sum_sq:'SQ', mean_sq:'QM', f_calc:'F calc', f_5:'F 5%', f_1:'F 1%', p_value:'p', significance:'Sig.',
      treatment:'Tratamento', mean:'Média', n:'n', sd:'DP', group:'Grupo'
    };
    return map[key] || key;
  }

  document.addEventListener('DOMContentLoaded', init);
})();
