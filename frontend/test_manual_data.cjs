const assert = require('node:assert/strict');
const { allowedDesigns, buildManualTable } = require('./assets/js/manual-data.js');

const base = {
  response: 'valor', treatment: 'tratamento', block: 'bloco', row: 'linha', column: 'coluna',
  numeric: 'dose', factors: ['fator_a', 'fator_b'], nTreatments: 4, nBlocks: 3,
  aLevels: 2, bLevels: 3,
};

function build(overrides) {
  return buildManualTable({ ...base, ...overrides });
}

function assertFilled(table, columns) {
  for (const row of table.rows) {
    for (const column of columns) assert.notEqual(row[column], '', `${column} ficou vazio`);
  }
}

assert.deepEqual(allowedDesigns('single'), ['DIC', 'DBC', 'DQL']);
assert.deepEqual(allowedDesigns('factorial'), ['DIC', 'DBC']);
assert.deepEqual(allowedDesigns('split_plot'), ['DBC']);
assert.deepEqual(allowedDesigns('regression'), ['DIC']);

let table = build({ design: 'DIC', analysisType: 'single' });
assert.deepEqual(table.headers, ['tratamento', 'valor']);
assert.equal(table.rows.length, 12);
assertFilled(table, ['tratamento']);

table = build({ design: 'DBC', analysisType: 'single' });
assert.deepEqual(table.headers, ['bloco', 'tratamento', 'valor']);
assert.equal(table.rows.length, 12);
assertFilled(table, ['bloco', 'tratamento']);

table = build({ design: 'DQL', analysisType: 'single' });
assert.deepEqual(table.headers, ['linha', 'coluna', 'tratamento', 'valor']);
assert.equal(table.rows.length, 16);
assertFilled(table, ['linha', 'coluna', 'tratamento']);
for (const line of ['L1', 'L2', 'L3', 'L4']) {
  assert.equal(new Set(table.rows.filter((row) => row.linha === line).map((row) => row.tratamento)).size, 4);
}

table = build({ design: 'DIC', analysisType: 'factorial' });
assert.deepEqual(table.headers, ['fator_a', 'fator_b', 'valor']);
assert.equal(table.rows.length, 18);
assertFilled(table, ['fator_a', 'fator_b']);

table = build({ design: 'DBC', analysisType: 'factorial' });
assert.deepEqual(table.headers, ['bloco', 'fator_a', 'fator_b', 'valor']);
assert.equal(table.rows.length, 18);
assertFilled(table, ['bloco', 'fator_a', 'fator_b']);

table = build({ design: 'DBC', analysisType: 'split_plot' });
assert.deepEqual(table.headers, ['bloco', 'fator_a', 'fator_b', 'valor']);
assert.equal(table.rows.length, 18);
assertFilled(table, ['bloco', 'fator_a', 'fator_b']);
for (const block of ['B1', 'B2', 'B3']) {
  const combinations = table.rows.filter((row) => row.bloco === block).map((row) => `${row.fator_a}/${row.fator_b}`);
  assert.equal(new Set(combinations).size, 6);
}

table = build({ design: 'DIC', analysisType: 'regression', nTreatments: 5 });
assert.deepEqual(table.headers, ['dose', 'valor']);
assert.equal(table.rows.length, 15);
assert.deepEqual([...new Set(table.rows.map((row) => row.dose))], [0, 50, 100, 150, 200]);

assert.throws(() => build({ design: 'DIC', analysisType: 'split_plot' }), /não está disponível/);
assert.throws(() => build({ design: 'DBC', analysisType: 'regression' }), /não está disponível/);
assert.throws(() => build({ design: 'DIC', analysisType: 'factorial', factors: [] }), /exatamente dois fatores/);
assert.throws(() => build({ design: 'DIC', analysisType: 'factorial', factors: ['a', 'b', 'c'] }), /exatamente dois fatores/);
assert.throws(() => build({ design: 'DIC', analysisType: 'regression', numeric: '' }), /coluna de dose/);
assert.throws(() => build({ design: 'DQL', analysisType: 'single', nTreatments: 2 }), /pelo menos 3 tratamentos/);
assert.throws(() => build({ design: 'DIC', analysisType: 'single', nBlocks: 1 }), /pelo menos 2 repetições/);
assert.throws(() => build({ design: 'DIC', analysisType: 'single', response: 'tratamento' }), /precisam ser diferentes/);

console.log('Manual data generator tests passed.');
