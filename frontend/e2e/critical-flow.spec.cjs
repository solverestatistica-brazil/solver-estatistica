const { test, expect } = require('@playwright/test');

const apiBase = 'https://api.solver-estatistica.com.br';

async function preparePage(page) {
  await page.addInitScript(() => {
    localStorage.setItem('solver_analytics_consent', 'denied');
    localStorage.setItem('solver_theme', 'dark');
  });
  await page.route(`${apiBase}/health`, (route) => route.fulfill({ json: { status: 'ok' } }));
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
  provenance: { engine_version: 'test', git_commit: 'abcdef1234567890', generated_at_utc: '2026-07-20T00:00:00Z', data_sha256: 'a'.repeat(64), config: { alpha_mode: 'auto', alpha: 0.05, sum_squares_type: 2 } },
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

test('fluxo DIC valida dados, analisa e libera exportacoes', async ({ page }) => {
  await preparePage(page);
  await page.route(`${apiBase}/api/analyze`, (route) => route.fulfill({ json: analysisResult }));
  await page.goto('/resultados.html');

  await expect(page.locator('#apiStatus')).toHaveText('API online');
  await page.locator('#goToData').click();
  await page.locator('#generateTable').click();
  await expect(page.locator('#dataTable tbody tr')).toHaveCount(16);

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
});