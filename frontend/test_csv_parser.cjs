const assert = require('node:assert/strict');
const { parse } = require('./assets/js/csv-parser.js');

assert.deepEqual(parse('tratamento;valor\nT1;12,5\n'), [{ tratamento: 'T1', valor: 12.5 }]);
assert.deepEqual(parse('tratamento;valor\nT1;12.5\n'), [{ tratamento: 'T1', valor: 12.5 }]);
assert.deepEqual(parse('tratamento;nota;valor\nT1;"texto; com separador";3\n'), [
  { tratamento: 'T1', nota: 'texto; com separador', valor: 3 },
]);
assert.deepEqual(parse('tratamento;nota\nT1;"linha 1\nlinha 2"\n'), [
  { tratamento: 'T1', nota: 'linha 1\nlinha 2' },
]);
assert.deepEqual(parse('tratamento;nota\nT1;"disse ""ok"""\n'), [
  { tratamento: 'T1', nota: 'disse "ok"' },
]);
assert.throws(() => parse('a;a\n1;2'), /duplicados/);
assert.throws(() => parse('a;b\n1;2;3'), /linha 2/);
assert.throws(() => parse(''), /vazio/);

console.log('CSV parser: 8 cenários aprovados');
