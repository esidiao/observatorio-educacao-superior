/**
 * Observatório Nacional da Educação Superior
 * Formatação, cor e normalização dos indicadores.
 *
 * INDICADOR_META é a fonte única de verdade de como cada indicador é exibido.
 * Todo `key` presente no GLOSSARIO (glossario.js) PRECISA ter entrada aqui —
 * sem isso o valor cai no fallback de 3 casas decimais e uma contagem como 19
 * aparece "19.000", que em pt-BR se lê como dezenove mil. O teste
 * tests/test_catalogo.py trava o build se algum indicador ficar sem entrada.
 */

const NODATA_COLOR = '#C9CDD2';
const RDBU = ['#2166AC','#4393C3','#92C5DE','#D1E5F0','#F7F7F7','#FDDBC7','#F4A582','#D6604D','#B2182B'];

const INDICADOR_META = {
  // Território
  ICT:                  { label: 'ICT',                 dec: 3, min: 0, max: 1,   maiorMelhor: false },
  E:                    { label: 'Equidade',            dec: 3, min: 0, max: 1,   maiorMelhor: true  },
  municipios_oferta:    { label: 'Municípios c/ oferta',dec: 0, min: null, max: null, maiorMelhor: null },
  municipios_deserto:   { label: 'Desertos',            dec: 0, min: null, max: null, maiorMelhor: false },
  municipios_total:     { label: 'Municípios na UF',    dec: 0, min: null, max: null, maiorMelhor: null },
  ead_polos_municipios: { label: 'Municípios c/ polo EaD', dec: 0, min: null, max: null, maiorMelhor: null },
  ead_polos_registros:  { label: 'Polos EaD (registros)', dec: 0, min: null, max: null, maiorMelhor: null },
  mun_ead_only:         { label: 'Municípios só EaD',   dec: 0, min: null, max: null, maiorMelhor: null },
  cobertura:            { label: 'Cobertura correlata', dec: 1, min: null, max: null, maiorMelhor: true  },

  // Qualidade
  IAF:                  { label: 'IAF',                 dec: 1, min: 0, max: 100, maiorMelhor: true  },
  CC:                   { label: 'CC (ENADE)',          dec: 2, min: 0, max: 5,   maiorMelhor: true  },
  ENADE:                { label: 'ENADE',               dec: 2, min: 0, max: 5,   maiorMelhor: true  },
  IDD:                  { label: 'IDD',                 dec: 2, min: 0, max: 5,   maiorMelhor: true  },
  CPC_cont:             { label: 'CPC',                 dec: 2, min: 0, max: 5,   maiorMelhor: true  },
  cpc_org_didatico:     { label: 'Org. didático-ped.',  dec: 2, min: 1, max: 6,   maiorMelhor: true  },
  cpc_infraestrutura:   { label: 'Infraestrutura',      dec: 2, min: 1, max: 6,   maiorMelhor: true  },
  cpc_oportunidade:     { label: 'Oport. de ampliação', dec: 2, min: 1, max: 6,   maiorMelhor: true  },
  pct_doc_doutores:     { label: '% Doutores',          dec: 1, min: 0, max: 100, maiorMelhor: true  },
  pct_doc_mestres:      { label: '% Mestres+',          dec: 1, min: 0, max: 100, maiorMelhor: true  },
  pct_doc_regime:       { label: '% Regime int./parc.', dec: 1, min: 0, max: 100, maiorMelhor: true  },
  vagas_avaliadas:      { label: 'Vagas avaliadas',     dec: 0, min: null, max: null, maiorMelhor: null },
  n_cursos_avaliados:   { label: 'Cursos avaliados',    dec: 0, min: null, max: null, maiorMelhor: null },
  concluintes_avaliados:{ label: 'Concluintes avaliados', dec: 0, min: null, max: null, maiorMelhor: null },

  igc_continuo:         { label: 'IGC',                 dec: 2, min: 0, max: 5,   maiorMelhor: true  },
  igc_faixa:            { label: 'IGC (faixa)',         dec: 0, min: 1, max: 5,   maiorMelhor: true  },

  pos_programas:        { label: 'Programas de pós',   dec: 0, min: null, max: null, maiorMelhor: null },
  pos_conceito_medio:   { label: 'Conceito CAPES',      dec: 2, min: 1, max: 7,   maiorMelhor: true  },

  // Capacidade
  vagas_total:          { label: 'Vagas totais',        dec: 0, min: null, max: null, maiorMelhor: null },
  vagas_presencial:     { label: 'Vagas presenciais',   dec: 0, min: null, max: null, maiorMelhor: null },
  vagas_ead:            { label: 'Vagas EaD',           dec: 0, min: null, max: null, maiorMelhor: null },
  vagas_capital:        { label: 'Vagas na capital',    dec: 0, min: null, max: null, maiorMelhor: null },
  pct_ead:              { label: '% EaD',               dec: 1, min: 0, max: 100, maiorMelhor: null },
  vagas_por_100k:       { label: 'Vagas / 100 mil hab.',dec: 1, min: null, max: null, maiorMelhor: null },
  populacao:            { label: 'População',           dec: 0, min: null, max: null, maiorMelhor: null },
  matriculas:           { label: 'Matrículas',          dec: 0, min: null, max: null, maiorMelhor: null },
  matriculas_ead:       { label: 'Matrículas EaD',      dec: 0, min: null, max: null, maiorMelhor: null },
  ingressos:            { label: 'Ingressantes',        dec: 0, min: null, max: null, maiorMelhor: null },
  concluintes:          { label: 'Concluintes',         dec: 0, min: null, max: null, maiorMelhor: null },
  taxa_conclusao:       { label: 'Taxa de conclusão',   dec: 1, min: 0, max: 100, maiorMelhor: true  },
  n_cursos_presencial:  { label: 'Cursos presenciais',  dec: 0, min: null, max: null, maiorMelhor: null },
  n_cursos_ead:         { label: 'Cursos EaD',          dec: 0, min: null, max: null, maiorMelhor: null },

  // Acesso & equidade
  pct_mulheres:         { label: '% Mulheres',          dec: 1, min: 0, max: 100, maiorMelhor: null },
  pct_ppi:              { label: '% Pretos/pardos/ind.',dec: 1, min: 0, max: 100, maiorMelhor: null },
  pct_financiamento:    { label: '% FIES/PROUNI',       dec: 1, min: 0, max: 100, maiorMelhor: null },
  pct_noturno:          { label: '% Vagas noturnas',    dec: 1, min: 0, max: 100, maiorMelhor: null },
  pct_rede_publica:     { label: '% Rede pública',      dec: 1, min: 0, max: 100, maiorMelhor: null },

  // Mercado
  n_ies:                { label: 'IES',                 dec: 0, min: null, max: null, maiorMelhor: null },
  HHI:                  { label: 'HHI',                 dec: 4, min: 0, max: 1, maiorMelhor: false },
  CR2:                  { label: 'CR2',                 dec: 1, min: 0, max: 1, maiorMelhor: false, mult: 100 },
  CR10:                 { label: 'CR10',                dec: 1, min: 0, max: 1, maiorMelhor: false, mult: 100 },
};

/** Formata conforme o indicador. `mult` converte fração→percentual antes de arredondar. */
function fmtIndicador(indicador, val) {
  if (val === null || val === undefined) return '—';
  const m = INDICADOR_META[indicador] || { dec: 3 };
  const v = Number(val) * (m.mult || 1);
  if (m.dec === 0) return v.toLocaleString('pt-BR');
  return v.toFixed(m.dec).replace('.', ',');
}

function rotuloIndicador(indicador) {
  return (INDICADOR_META[indicador] || {}).label || indicador;
}

/** Escala divergente RdBu — nunca RdYlGn (regra de acessibilidade para daltonismo). */
function corGenerica(val, min, max, maiorMelhor) {
  if (val === null || val === undefined || min === null || max === null) return NODATA_COLOR;
  if (maiorMelhor === null) return '#2E5496';
  let norm = (val - min) / (max - min);
  norm = Math.max(0, Math.min(1, norm));
  if (maiorMelhor) norm = 1 - norm;
  return RDBU[Math.min(8, Math.floor(norm * 9))];
}

function getCor(indicador, val, dominio) {
  const m = INDICADOR_META[indicador];
  if (!m) return NODATA_COLOR;
  let { min, max } = m;
  if ((min === null || max === null) && dominio) {
    min = dominio.min; max = dominio.max;
  }
  return corGenerica(val, min, max, m.maiorMelhor);
}

/** Normaliza 0–1 com 1 = melhor, para radar e barras comparativas. */
function normalizar(indicador, val, valores) {
  if (val === null || val === undefined || isNaN(val)) return null;
  const m = INDICADOR_META[indicador] || {};
  let { min, max } = m;
  if (min === null || max === null || min === undefined || max === undefined) {
    const vs = (valores || []).filter(v => v !== null && v !== undefined && !isNaN(v));
    if (!vs.length) return null;
    min = Math.min(...vs); max = Math.max(...vs);
  }
  if (max === min) return 0.5;
  let n = (val - min) / (max - min);
  if (m.maiorMelhor === false) n = 1 - n;
  return Math.max(0, Math.min(1, n));
}

function exportarCSV(linhas, nomeArquivo) {
  if (!linhas || !linhas.length) return;
  const cols = Object.keys(linhas[0]);
  const escapar = v => {
    let s = v === null || v === undefined ? '' : String(v);
    // Injeção de fórmula: uma célula iniciada por = + - @ ou tab vira fórmula ao
    // abrir o CSV no Excel/Calc. O apóstrofo à frente força leitura como texto.
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const csv = [cols.join(';')]
    .concat(linhas.map(l => cols.map(c => escapar(l[c])).join(';')))
    .join('\n');
  baixar(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }), nomeArquivo);
}

function exportarJSON(dados, nomeArquivo) {
  baixar(new Blob([JSON.stringify(dados, null, 2)], { type: 'application/json' }), nomeArquivo);
}

function baixar(blob, nomeArquivo) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = nomeArquivo;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
