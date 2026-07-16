(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SolverManualData = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  'use strict';

  const DESIGNS = ['DIC', 'DBC', 'DQL'];
  const ANALYSES = ['single', 'factorial', 'split_plot', 'regression'];

  function unique(values) {
    return [...new Set(values.filter(Boolean))];
  }

  function requiredText(value, label, fallback) {
    const normalized = String(value || fallback || '').trim();
    if (!normalized) throw new Error(`Informe o nome da coluna ${label}.`);
    return normalized;
  }

  function positiveInteger(value, label, minimum) {
    const normalized = Number(value);
    if (!Number.isInteger(normalized) || normalized < minimum) {
      throw new Error(`${label} deve ser um número inteiro maior ou igual a ${minimum}.`);
    }
    return normalized;
  }

  function allowedDesigns(analysisType) {
    if (analysisType === 'split_plot') return ['DBC'];
    if (analysisType === 'regression') return ['DIC'];
    if (analysisType === 'factorial') return ['DIC', 'DBC'];
    return [...DESIGNS];
  }

  function buildManualTable(config) {
    const design = String(config.design || 'DIC').toUpperCase();
    const analysisType = String(config.analysisType || 'single');
    if (!DESIGNS.includes(design)) throw new Error(`Delineamento manual inválido: ${design}.`);
    if (!ANALYSES.includes(analysisType)) throw new Error(`Tipo de análise manual inválido: ${analysisType}.`);
    if (!allowedDesigns(analysisType).includes(design)) {
      const labels = { factorial: 'Fatorial', split_plot: 'Parcelas subdivididas', regression: 'Regressão direta' };
      throw new Error(`${labels[analysisType] || analysisType} não está disponível com ${design} no gerador manual.`);
    }

    const response = requiredText(config.response, 'resposta', 'valor');
    const treatment = requiredText(config.treatment, 'tratamento', 'tratamento');
    const block = requiredText(config.block, 'bloco', 'bloco');
    const row = requiredText(config.row, 'linha', 'linha');
    const column = requiredText(config.column, 'coluna', 'coluna');
    const nTreatments = positiveInteger(config.nTreatments, analysisType === 'regression' ? 'Número de doses' : 'Número de tratamentos', 2);
    const nBlocks = positiveInteger(config.nBlocks, 'Número de blocos/repetições', 1);
    const factors = unique((config.factors || []).map((value) => String(value).trim()));
    const numeric = String(config.numeric || '').trim();

    if (analysisType === 'single' && design !== 'DQL' && nBlocks < 2) {
      throw new Error('Informe pelo menos 2 repetições/blocos para estimar o erro experimental.');
    }
    if (analysisType === 'single' && design === 'DQL' && nTreatments < 3) {
      throw new Error('O DQL manual precisa de pelo menos 3 tratamentos para estimar o resíduo.');
    }
    if (analysisType === 'factorial' || analysisType === 'split_plot') {
      if (factors.length !== 2) {
        throw new Error('O gerador manual exige exatamente dois fatores, separados por vírgula.');
      }
      if (nBlocks < 2) {
        throw new Error('Informe pelo menos 2 repetições/blocos para estimar os erros do experimento fatorial.');
      }
    }
    if (analysisType === 'regression') {
      if (!numeric) throw new Error('Informe o nome da coluna de dose/fator numérico.');
      if (nTreatments < 3) throw new Error('A regressão manual precisa de pelo menos 3 doses distintas.');
    }

    const headers = [];
    if (design === 'DBC') headers.push(block);
    if (design === 'DQL') headers.push(row, column);
    if (analysisType === 'factorial' || analysisType === 'split_plot') headers.push(...factors);
    if (analysisType === 'regression') headers.push(numeric);
    if (analysisType === 'single') headers.push(treatment);
    headers.push(response);
    if (unique(headers).length !== headers.length) {
      throw new Error('Os nomes das colunas usadas no gerador manual precisam ser diferentes entre si.');
    }

    const emptyRow = () => Object.fromEntries(headers.map((header) => [header, '']));
    const rows = [];

    if (analysisType === 'single' && design === 'DQL') {
      for (let rowIndex = 1; rowIndex <= nTreatments; rowIndex += 1) {
        for (let columnIndex = 1; columnIndex <= nTreatments; columnIndex += 1) {
          const item = emptyRow();
          item[row] = `L${rowIndex}`;
          item[column] = `C${columnIndex}`;
          item[treatment] = `T${((rowIndex + columnIndex - 2) % nTreatments) + 1}`;
          rows.push(item);
        }
      }
    } else if (analysisType === 'regression') {
      for (let doseIndex = 0; doseIndex < nTreatments; doseIndex += 1) {
        for (let repetition = 1; repetition <= nBlocks; repetition += 1) {
          const item = emptyRow();
          item[numeric] = doseIndex * 50;
          rows.push(item);
        }
      }
    } else if (analysisType === 'factorial' || analysisType === 'split_plot') {
      const aLevels = positiveInteger(config.aLevels, 'Níveis do fator A', 2);
      const bLevels = positiveInteger(config.bLevels, 'Níveis do fator B', 2);
      const [factorA, factorB] = factors;
      for (let repetition = 1; repetition <= nBlocks; repetition += 1) {
        for (let a = 1; a <= aLevels; a += 1) {
          for (let b = 1; b <= bLevels; b += 1) {
            const item = emptyRow();
            if (design === 'DBC') item[block] = `B${repetition}`;
            item[factorA] = `A${a}`;
            item[factorB] = `B${b}`;
            rows.push(item);
          }
        }
      }
    } else {
      for (let repetition = 1; repetition <= nBlocks; repetition += 1) {
        for (let treatmentIndex = 1; treatmentIndex <= nTreatments; treatmentIndex += 1) {
          const item = emptyRow();
          if (design === 'DBC') item[block] = `B${repetition}`;
          item[treatment] = `T${treatmentIndex}`;
          rows.push(item);
        }
      }
    }

    return { headers, rows };
  }

  return { allowedDesigns, buildManualTable };
});
