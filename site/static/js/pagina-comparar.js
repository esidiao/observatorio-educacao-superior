/* Comparação entre cursos.
 *
 * window.INDICE.c   — catálogo de navegação, em listas: [nome, slug, vagas, área]
 * window.COMPARACAO — {campos: [...], dados: {slug: {recorte: [valores...]}}}
 *
 * A matriz é colunar: com centenas de cursos × 28 recortes, repetir o nome de
 * cada campo em cada registro multiplicaria o arquivo por várias vezes.
 */
(function () {
  // O índice global guarda o curso como lista, para não repetir as chaves
  // quatro mil vezes no arquivo. Aqui volta a ter nome, porque o resto desta
  // página foi escrito assim.
  var CURSOS = (window.INDICE && window.INDICE.c || []).map(function (r) {
    return { n: r[0], s: r[1], v: r[2], a: r[3] };
  });
  var CAMPOS = (window.COMPARACAO || {}).campos || [];
  var DADOS = (window.COMPARACAO || {}).dados || {};
  var INDICE = {};
  CAMPOS.forEach(function (c, i) { INDICE[c] = i; });

  // As UFs saem dos próprios dados — não há por que o template repetir a lista.
  var UFS = (function () {
    var vistas = {};
    Object.keys(DADOS).forEach(function (slug) {
      Object.keys(DADOS[slug]).forEach(function (r) { if (r !== 'BR') vistas[r] = 1; });
    });
    return Object.keys(vistas).sort();
  })();

  // Abre com os seis maiores: centenas de linhas de tabela não é comparação,
  // é despejo de dados.
  var PADRAO = CURSOS.slice(0, 6).map(function (c) { return c.s; });
  var selCursos = new Set(PADRAO);
  var selKPIs = new Set(['vagas_total', 'pct_ead', 'ICT', 'IAF', 'n_ies', 'HHI']);
  var recorte = 'BR';

  var CATALOGO = (typeof GLOSSARIO !== 'undefined' ? GLOSSARIO : [])
    .filter(function (g) { return INDICE[g.key] !== undefined; });

  var PALETA = ['#2E5496', '#B07D22', '#3F6B2E', '#B23A2E', '#8B5CF6', '#06B6D4'];

  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function valor(slug, key) {
    var linha = (DADOS[slug] || {})[recorte];
    var i = INDICE[key];
    if (!linha || i === undefined) return null;
    var v = linha[i];
    return v === undefined ? null : v;
  }

  function selecionados() {
    return CURSOS.filter(function (c) { return selCursos.has(c.s); })
      .map(function (c) { return { slug: c.s, nome: c.n }; });
  }

  function avisar(texto) {
    var el = document.getElementById('comp-aviso');
    if (el) el.textContent = texto;
  }

  /* ── Seleção de cursos ─────────────────────────────────────────────────── */

  function renderSugestoes() {
    var caixa = document.getElementById('curso-sugestoes-comp');
    var busca = document.getElementById('busca-curso');
    var termo = sem(busca.value.trim());
    caixa.innerHTML = '';
    if (!termo) { caixa.hidden = true; return; }

    var achados = CURSOS.filter(function (c) {
      return !selCursos.has(c.s) && sem(c.n).indexOf(termo) >= 0;
    }).slice(0, 10);

    if (!achados.length) {
      caixa.textContent = 'Nenhum curso com esse termo';
      caixa.hidden = false;
      return;
    }
    achados.forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn outline btn-mini';
      b.textContent = c.n;      // nome vem do Censo, nunca interpretado como HTML
      b.addEventListener('click', function () {
        selCursos.add(c.s);
        busca.value = '';
        avisar(c.n + ' adicionado à comparação');
        renderSugestoes(); renderCursoChips(); renderTudo();
        busca.focus();
      });
      caixa.appendChild(b);
    });
    caixa.hidden = false;
  }

  function renderCursoChips() {
    var raiz = document.getElementById('curso-chips');
    raiz.innerHTML = '';
    var escolhidos = selecionados();
    if (!escolhidos.length) {
      var vazio = document.createElement('span');
      vazio.className = 'chips-vazio';
      vazio.textContent = 'Nenhum curso selecionado — busque acima.';
      raiz.appendChild(vazio);
      return;
    }
    escolhidos.forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-mini';
      b.setAttribute('aria-label', 'Remover ' + c.nome + ' da comparação');
      b.textContent = c.nome + ' ×';
      b.addEventListener('click', function () {
        selCursos.delete(c.slug);
        avisar(c.nome + ' removido da comparação');
        renderCursoChips(); renderTudo();
      });
      raiz.appendChild(b);
    });
  }

  /* ── Seleção de indicadores ────────────────────────────────────────────── */

  function renderKpiChips() {
    var ordem = ['Território', 'Qualidade', 'Capacidade', 'Acesso & equidade', 'Mercado'];
    var raiz = document.getElementById('kpi-chips');
    raiz.innerHTML = '';

    ordem.forEach(function (cat) {
      var itens = CATALOGO.filter(function (g) { return g.cat === cat; });
      if (!itens.length) return;

      var grupo = document.createElement('div');
      grupo.className = 'kpi-grupo';
      grupo.setAttribute('role', 'group');
      grupo.setAttribute('aria-label', 'Indicadores de ' + cat);

      var titulo = document.createElement('div');
      titulo.className = 'kpi-grupo-titulo';
      titulo.textContent = cat;
      grupo.appendChild(titulo);

      var faixa = document.createElement('div');
      faixa.className = 'kpi-grupo-chips';
      itens.forEach(function (g) {
        var on = selKPIs.has(g.key);
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn btn-mini' + (on ? '' : ' outline');
        b.title = g.nome;
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        b.textContent = g.sigla;
        b.addEventListener('click', function () {
          if (selKPIs.has(g.key)) selKPIs.delete(g.key); else selKPIs.add(g.key);
          renderKpiChips(); renderTudo();
        });
        faixa.appendChild(b);
      });
      grupo.appendChild(faixa);
      raiz.appendChild(grupo);
    });

    document.getElementById('kpi-contador').textContent =
      '(' + selKPIs.size + ' selecionados)';
  }

  /* ── Saídas ────────────────────────────────────────────────────────────── */

  function linhasCSV() {
    var keys = Array.from(selKPIs);
    return selecionados().map(function (c) {
      var linha = { curso: c.nome, recorte: recorte };
      keys.forEach(function (k) { linha[k] = valor(c.slug, k); });
      return linha;
    });
  }

  function renderTabela() {
    var cursos = selecionados();
    var keys = Array.from(selKPIs);
    var vazio = !cursos.length || !keys.length;
    document.getElementById('msg-vazio').hidden = !vazio;
    document.getElementById('tabela-comp').hidden = vazio;
    if (vazio) return;

    var thead = document.getElementById('comp-thead');
    thead.innerHTML = '';
    var th0 = document.createElement('th');
    th0.scope = 'col';
    th0.textContent = 'Curso';
    thead.appendChild(th0);
    keys.forEach(function (k) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = rotuloIndicador(k);
      thead.appendChild(th);
    });

    var tbody = document.getElementById('comp-tbody');
    tbody.innerHTML = '';
    cursos.forEach(function (c) {
      var tr = document.createElement('tr');
      var th = document.createElement('th');
      th.scope = 'row';
      var a = document.createElement('a');
      a.href = 'curso/' + c.slug + '/index.html';
      var forte = document.createElement('strong');
      forte.textContent = c.nome;
      a.appendChild(forte);
      th.appendChild(a);
      tr.appendChild(th);

      keys.forEach(function (k) {
        var td = document.createElement('td');
        var v = valor(c.slug, k);
        if (v === null) { td.className = 'sem-dado'; td.textContent = 'sem dados'; }
        else { td.textContent = fmtIndicador(k, v); }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function renderBarras() {
    var cursos = selecionados();
    var keys = Array.from(selKPIs);
    var raiz = document.getElementById('barras-norm');
    raiz.innerHTML = '';
    if (!cursos.length || !keys.length) return;

    keys.forEach(function (k) {
      var valores = cursos.map(function (c) { return valor(c.slug, k); });

      var bloco = document.createElement('div');
      bloco.className = 'barra-bloco';
      var titulo = document.createElement('div');
      titulo.className = 'barra-titulo';
      titulo.textContent = rotuloIndicador(k);
      bloco.appendChild(titulo);

      cursos.forEach(function (c, i) {
        var v = valores[i];
        var n = normalizar(k, v, valores);
        var linha = document.createElement('div');
        linha.className = 'barra-linha';

        var nome = document.createElement('span');
        nome.className = 'barra-nome';
        nome.textContent = c.nome;
        linha.appendChild(nome);

        if (n === null) {
          var nd = document.createElement('span');
          nd.className = 'sem-dado';
          nd.textContent = 'sem dados';
          linha.appendChild(nd);
        } else {
          var trilho = document.createElement('span');
          trilho.className = 'barra-trilho';
          // A barra é decorativa: o valor exato vem logo ao lado, em texto.
          trilho.setAttribute('aria-hidden', 'true');
          var preenche = document.createElement('span');
          preenche.className = 'barra-preenche';
          preenche.style.width = (n * 100).toFixed(1) + '%';
          preenche.style.background = PALETA[i % PALETA.length];
          trilho.appendChild(preenche);
          linha.appendChild(trilho);

          var val = document.createElement('span');
          val.className = 'barra-valor';
          val.textContent = fmtIndicador(k, v);
          linha.appendChild(val);
        }
        bloco.appendChild(linha);
      });
      raiz.appendChild(bloco);
    });
  }

  function renderTudo() {
    renderTabela();
    renderBarras();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var selUF = document.getElementById('sel-uf');
    var brasil = document.createElement('option');
    brasil.value = 'BR';
    brasil.textContent = 'Brasil (todas as UFs)';
    selUF.appendChild(brasil);
    UFS.forEach(function (uf) {
      var op = document.createElement('option');
      op.value = uf;
      op.textContent = uf;
      selUF.appendChild(op);
    });
    selUF.value = recorte;
    selUF.addEventListener('change', function () { recorte = selUF.value; renderTudo(); });

    document.getElementById('busca-curso').addEventListener('input', renderSugestoes);
    document.getElementById('btn-limpar').addEventListener('click', function () {
      selCursos = new Set();
      avisar('Comparação esvaziada');
      renderCursoChips(); renderTudo();
    });
    document.getElementById('btn-maiores').addEventListener('click', function () {
      selCursos = new Set(PADRAO);
      avisar('Comparação com os seis maiores cursos');
      renderCursoChips(); renderTudo();
    });
    document.getElementById('btn-csv-comp').addEventListener('click', function () {
      exportarCSV(linhasCSV(), 'comparacao_cursos.csv');
    });
    document.querySelectorAll('[data-preset]').forEach(function (b) {
      b.addEventListener('click', function () {
        selKPIs = new Set(CATALOGO.filter(function (g) { return g.cat === b.dataset.preset; })
          .map(function (g) { return g.key; }));
        renderKpiChips(); renderTudo();
      });
    });

    renderCursoChips();
    renderKpiChips();
    renderTudo();
  });
})();
