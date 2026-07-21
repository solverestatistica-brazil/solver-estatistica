const { test, expect } = require('@playwright/test');

const apiBase = 'https://api.solver-estatistica.com.br';

async function preparePage(page) {
  await page.addInitScript(() => {
    localStorage.setItem('solver_analytics_consent', 'denied');
    localStorage.setItem('solver_theme', 'dark');
  });
  await page.route(`${apiBase}/health`, (route) => route.fulfill({ json: { status: 'ok' } }));
}

async function openFilledDic(page) {
  await page.goto('/resultados.html');
  await expect(page.locator('#apiStatus')).toHaveText('API online');
  await page.locator('#goToData').click();
  await page.locator('#generateTable').click();
  await expect(page.locator('#dataTable tbody tr')).toHaveCount(16);
  const values = page.locator('#dataTable input[data-column="valor"]');
  for (let index = 0; index < await values.count(); index += 1) {
    await values.nth(index).fill(String(10 + (index % 4)));
  }
}

const analysisResult = {
  anova: {
    cv: 8.4,
    cv_label: 'Baixo',
    table: [{ source: 'Tratamento', df: 3, sum_sq: 30, mean_sq: 10, f_calc: 9.2, f_5: 3.5, f_1: 5.1, p_value: 0.00001, significance: '1%' }],
  },
  means: {
    best: { treatment: 'T2', mean: 14 },
    treatment_means: [
      { treatment: 'T1', mean: 10, n: 4, sd: 1, group: 'b' },
      { treatment: 'T2', mean: 14, n: 4, sd: 1, group: 'a' },
    ],
    comparison: { test: 'TUKEY', note: 'Comparacao realizada.' },
  },
  recommendations: ['Interpretar o resultado considerando o delineamento.'],
  pressupostos: { veredito: 'ok', resumo: 'Pressupostos atendidos.', testes: {} },
  provenance: { engine_version: 'test', git_commit: 'abcdef1234567890', generated_at_utc: '2026-07-20T00:00:00Z', generated_at_brasilia: '2026-07-19T21:00:00-03:00', data_sha256: 'a'.repeat(64), config: { alpha_mode: 'auto', alpha: 0.05, sum_squares_type: 2 } },
  meta: { n_rows: 16, alpha_mode: 'auto', alpha: 0.05, sum_squares_type: 2 },
};

test('tema claro preserva identidade e layout mobile nao transborda', async ({ page }) => {
  await preparePage(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/index.html');

  await page.getByRole('button', { name: 'Ativar tema claro' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('.logo-group small')).toBeHidden();

  const widths = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
});

test('upload CSV detecta colunas e oferece mapeamento sem bloquear o usuario', async ({ page }) => {
  await preparePage(page);
  await page.goto('/resultados.html');
  await page.locator('#goToData').click();
  await page.locator('#uploadMode').click();

  await page.locator('#fileInput').setInputFiles({
    name: 'ensaio.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('Tratamento;Resposta\nT1;10\nT2;12\nT1;11\nT2;13\n'),
  });

  await expect(page.locator('#mappingPanel')).toBeVisible();
  await expect(page.getByLabel('Coluna para Resposta')).toHaveValue('Resposta');
  await expect(page.getByLabel('Coluna para Tratamento')).toHaveValue('Tratamento');
  await expect(page.locator('#dataTable tbody tr')).toHaveCount(4);
});

test('fluxo DIC valida dados, analisa e libera exportacoes', async ({ page }) => {
  await preparePage(page);
  await page.route(`${apiBase}/api/analyze`, (route) => route.fulfill({ json: analysisResult }));
  let releaseExport;
  const exportGate = new Promise((resolve) => { releaseExport = resolve; });
  await page.route(`${apiBase}/api/export/pdf`, async (route) => {
    await exportGate;
    await route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4 test document' });
  });
  await page.goto('/resultados.html');

  await page.locator('#goToData').click();
  await page.locator('#generateTable').click();
  await page.locator('#runAnalysis').click();
  await expect(page.locator('#validationPanel')).toBeVisible();

  const values = page.locator('#dataTable input[data-column="valor"]');
  for (let index = 0; index < await values.count(); index += 1) {
    await values.nth(index).fill(String(10 + (index % 4)));
  }

  await page.locator('#runAnalysis').click();
  await expect(page.locator('#results')).toBeVisible();
  await expect(page.locator('#resBest')).toHaveText('T2');
  await expect(page.locator('#anovaTable')).toContainText('< 0,0001');
  await expect(page.locator('#downloadPdf')).toBeEnabled();
  await expect(page.locator('#downloadExcel')).toBeEnabled();
  await expect(page.locator('#goToExports')).toBeVisible();
  await page.locator('#goToExports').click();
  await expect(page.locator('#tab-exports')).toHaveClass(/active/);
  await expect(page.locator('#downloadPdf')).toBeVisible();

  const exportRequest = page.waitForRequest((request) => request.url() === `${apiBase}/api/export/pdf` && request.method() === 'POST');
  await page.locator('#downloadPdf').click();
  await expect(page.locator('#downloadPdf')).toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('#exportStatus')).toContainText('Gerando PDF técnico');
  releaseExport();
  await exportRequest;
  await expect(page.locator('#exportStatus')).toContainText('O download foi iniciado.');
  await expect(page.locator('#downloadPdf')).toBeEnabled();
});

test('falha da API e comunicada de forma acessivel', async ({ page }) => {
  await preparePage(page);
  await page.route(`${apiBase}/api/analyze`, (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Servico indisponivel para teste.' }),
  }));
  await openFilledDic(page);
  await page.locator('#runAnalysis').click();
  await expect(page.locator('[role="alert"]').filter({ hasText: 'Servico indisponivel para teste.' })).toBeVisible();
  await expect(page.locator('#apiStatus')).toHaveText('Erro na análise');
});

test('cancelamento interrompe uma analise pendente sem alterar resultados', async ({ page }) => {
  await preparePage(page);
  let releaseResponse;
  const responseGate = new Promise((resolve) => { releaseResponse = resolve; });
  await page.route(`${apiBase}/api/analyze`, async (route) => {
    await responseGate;
    try { await route.fulfill({ json: analysisResult }); } catch (_) { }
  });
  await openFilledDic(page);

  await page.locator('#runAnalysis').click();
  await expect(page.locator('#processingOverlay')).toBeVisible();
  await page.locator('#cancelAnalysis').click();
  releaseResponse();

  await expect(page.locator('#processingOverlay')).toBeHidden();
  await expect(page.locator('body > [role="status"]').filter({ hasText: 'Análise cancelada. Nenhum resultado foi alterado.' })).toBeVisible();
  await expect(page.locator('#results')).toBeHidden();
});
