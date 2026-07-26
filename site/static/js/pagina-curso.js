/* Página de um curso: tabela de indicadores por UF, ordenável, exportável.
 *
 * Os dados chegam por <script type="application/json">, não por script inline —
 * bloco com type não-executável não depende de 'unsafe-inline' na CSP.
 */
(function () {
  var COLUNAS = ['vagas_total', 'vagas_presencial', 'vagas_ead', 'pct_ead',
                 'municipios_oferta', 'municipios_deserto', 'ead_polos_municipios',
                 'n_ies', 'ICT', 'E', 'IAF', 'vagas_por_100k'];

  var DADOS = {};
  var META = {};
  var ordem = 'vagas_total';
  var dir = 'desc';

  function lerJSON(id) {
    var el = document.getElementById(id);
    if (!el) return {};
    try { return JSON.parse(el.textContent); } catch (e) { return {}; }
  }

  function linhasCSV() {
    return Object.keys(DADOS).map(function (uf) {
      var linha = { UF: uf };
      COLUNAS.forEach(function (c) { linha[c] = DADOS[uf][c]; });
      return linha;
    });
  }

  function dominios() {
    var out = {};
    COLUNAS.forEach(function (c) {
      var vs = Object.keys(DADOS)
        .map(function (uf) { return DADOS[uf][c]; })
        .filter(function (v) { return v !== null && v !== undefined; });
      out[c] = vs.length ? { min: Math.min.apply(null, vs), max: Math.max.apply(null, vs) } : null;
    });
    return out;
  }

  function ordenadas() {
    return Object.keys(DADOS).sort(function (a, b) {
      var va = DADOS[a][ordem], vb = DADOS[b][ordem];
      if (va === null || va === undefined) return 1;   // sem dados sempre no fim,
      if (vb === null || vb === undefined) return -1;  // nas duas direções
      return dir === 'desc' ? vb - va : va - vb;
    });
  }

  function renderCabecalho() {
    var linha = document.getElementById('thead-row');
    linha.innerHTML = '';

    var thUF = document.createElement('th');
    thUF.scope = 'col';
    thUF.textContent = 'UF';
    linha.appendChild(thUF);

    COLUNAS.forEach(function (c) {
      var th = document.createElement('th');
      th.scope = 'col';
      var ativa = c === ordem;
      th.setAttribute('aria-sort', ativa ? (dir === 'desc' ? 'descending' : 'ascending') : 'none');

      // Ordenar por clique no cabeçalho — o <select> continua existindo para quem
      // prefere, mas a tabela precisa ser operável onde o usuário já está olhando.
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'th-ordenar';
      b.textContent = rotuloIndicador(c) + (ativa ? (dir === 'desc' ? ' ↓' : ' ↑') : '');
      b.setAttribute('aria-label', 'Ordenar por ' + rotuloIndicador(c));
      b.addEventListener('click', function () {
        if (ordem === c) { dir = dir === 'desc' ? 'asc' : 'desc'; }
        else { ordem = c; dir = 'desc'; }
        var sel = document.getElementById('sel-ordem');
        if (sel) sel.value = ordem;
        render();
      });
      th.appendChild(b);
      linha.appendChild(th);
    });
  }

  function renderCorpo() {
    var doms = dominios();
    var tbody = document.getElementById('tbody-ufs');
    tbody.innerHTML = '';

    ordenadas().forEach(function (uf) {
      var d = DADOS[uf];
      var tr = document.createElement('tr');

      var th = document.createElement('th');
      th.scope = 'row';
      var a = document.createElement('a');
      a.href = 'uf/' + uf + '.html';
      var tag = document.createElement('span');
      tag.className = 'uf-tag';
      tag.textContent = uf;
      a.appendChild(tag);
      a.setAttribute('aria-label', (META.curso || '') + ' em ' + uf);
      th.appendChild(a);
      tr.appendChild(th);

      COLUNAS.forEach(function (c) {
        var td = document.createElement('td');
        var v = d[c];
        if (v === null || v === undefined) {
          td.className = 'sem-dado';
          td.textContent = 'sem dados';
        } else {
          td.style.borderLeft = '3px solid ' + getCor(c, v, doms[c]);
          td.textContent = fmtIndicador(c, v);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function render() {
    renderCabecalho();
    renderCorpo();
  }

  document.addEventListener('DOMContentLoaded', function () {
    DADOS = lerJSON('dados-ufs');
    META = lerJSON('dados-meta');
    if (!Object.keys(DADOS).length) return;

    var sel = document.getElementById('sel-ordem');
    if (sel) {
      COLUNAS.forEach(function (c) {
        var op = document.createElement('option');
        op.value = c;
        op.textContent = rotuloIndicador(c);
        sel.appendChild(op);
      });
      sel.value = ordem;
      sel.addEventListener('change', function () { ordem = sel.value; dir = 'desc'; render(); });
    }

    var btnCSV = document.getElementById('btn-csv');
    if (btnCSV) {
      btnCSV.addEventListener('click', function () {
        exportarCSV(linhasCSV(), (META.slug || 'curso') + '_ufs.csv');
      });
    }
    var btnJSON = document.getElementById('btn-json');
    if (btnJSON) {
      btnJSON.addEventListener('click', function () {
        exportarJSON(DADOS, (META.slug || 'curso') + '_ufs.json');
      });
    }

    render();
  });
})();
