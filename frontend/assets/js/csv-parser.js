(function exposeCsvParser(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SolverCsv = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function createCsvParser() {
  function countUnquoted(line, separator) {
    let quoted = false; let count = 0;
    for (let i = 0; i < line.length; i += 1) {
      if (line[i] === '"') {
        if (quoted && line[i + 1] === '"') i += 1;
        else quoted = !quoted;
      } else if (!quoted && line[i] === separator) count += 1;
    }
    return count;
  }

  function parse(text) {
    const source = String(text || '').replace(/^\uFEFF/, '');
    if (!source.trim()) throw new Error('O CSV está vazio.');
    const firstRecord = source.split(/\r?\n/, 1)[0];
    const sep = countUnquoted(firstRecord, ';') >= countUnquoted(firstRecord, ',') ? ';' : ',';
    const records = [];
    let record = []; let field = ''; let quoted = false;
    for (let i = 0; i < source.length; i += 1) {
      const char = source[i];
      if (char === '"') {
        if (quoted && source[i + 1] === '"') { field += '"'; i += 1; }
        else quoted = !quoted;
      } else if (char === sep && !quoted) {
        record.push(field); field = '';
      } else if ((char === '\n' || char === '\r') && !quoted) {
        if (char === '\r' && source[i + 1] === '\n') i += 1;
        record.push(field); field = '';
        if (record.some((value) => value.trim() !== '')) records.push(record);
        record = [];
      } else {
        field += char;
      }
    }
    if (quoted) throw new Error('CSV inválido: há aspas sem fechamento.');
    record.push(field);
    if (record.some((value) => value.trim() !== '')) records.push(record);
    const headers = (records.shift() || []).map((value) => value.trim());
    if (headers.length < 2 || headers.some((header) => !header)) {
      throw new Error('CSV inválido: informe ao menos duas colunas com cabeçalhos preenchidos.');
    }
    if (new Set(headers).size !== headers.length) throw new Error('CSV inválido: há cabeçalhos duplicados.');
    return records.map((values, rowIndex) => {
      if (values.length !== headers.length) {
        throw new Error(`CSV inválido na linha ${rowIndex + 2}: número de colunas diferente do cabeçalho.`);
      }
      return Object.fromEntries(headers.map((header, i) => {
        const raw = values[i].trim();
        const normalized = sep === ';' && raw.includes(',')
          ? raw.replace(/\./g, '').replace(',', '.')
          : raw;
        const value = normalized !== '' && !Number.isNaN(Number(normalized)) ? Number(normalized) : raw;
        return [header, value];
      }));
    });
  }

  return { parse };
}));
