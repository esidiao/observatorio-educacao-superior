/* Comparação genérica entre entidades — serve estados e instituições.
 *
 * A página de comparar cursos nasceu antes e tem lógica própria (recorte
 * territorial, presets de indicador). Aqui a necessidade é mais simples e igual
 * para os dois casos: escolher entidades, escolher campos, ver tabela e barras.
 * Um script parametrizado evita manter duas cópias quase idênticas.
 *
 * Espera em window.COMPARAVEIS:
 *   { tipo: 'estados'|'instituicoes',
 *     campos: [{k, rotulo, casas, unidade, maiorMelhor}],
 *     itens: [{id, nome, sub, url, v: [valores na ordem de campos]}] }
 */
(function () {
  var C = window.COMPARAVEIS;
  if (!C || !C.itens || !C.itens.length) return;

  var PALETA = ['#2E5496', '#B07D22', '#3F6B2E', '#B23A2E', '#6B21A8', '#0E7490'];
  var PADRAO_ITENS = 5;

  var porId = {};
  C.itens.forEach(function (i) { porId[i.id] = i; });

  var selecionados = C.itens.slice(0, PADRAO_ITENS).map(function (i) { return i.id; });
  var selCampos = C.campos.slice(0, 6).map(function (c) { return c.k; });

  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function valor(id, k) {
    var item = porId[id];
    var i = C.campos.findIndex(function (c) { return c.k === k; });
    if (!item || i < 0) return null;
    var v = item.v[i];
    return v === undefined ? null : v;
  }

  function campoDe(k) {
    return C.campos.filter(function (c) { return c.k === k; })[0] || {};
  }

  function fmt(k, v) {
    if (v === null || v === undefined) return null;
    var c = campoDe(k);
    if (c.casas) return v.toFixed(c.casas).replace('.', ',') + (c.unidade || '');
    return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (c.unidade || '');
  }

  function avisar(t) {
    var el = document.getElementById('comp-aviso');
    if (el) el.textContent = t;
  }

  /* ── seleção de entidades ─────────────────────────────────────────────── */

  function renderSugestoes() {
    var caixa = document.getElementById('sugestoes');
    var busca = document.getElementById('busca-entidade');
    var termo = sem(busca.value.trim());
    caixa.innerHTML = '';
    if (!termo) { caixa.hidden = true; return; }

    var achados = C.itens.filter(function (i) {
      return selecionados.indexOf(i.id) < 0 && sem(i.nome).indexOf(termo) >= 0;
    }).slice(0, 10);

    if (!achados.length) {
      caixa.textContent = 'Nada encontrado com esse termo';
      caixa.hidden = false;
      return;
    }
    achados.forEach(function (i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn outline btn-mini';
      b.textContent = i.nome;
      b.addEventListener('click', function () {
        selecionados.push(i.id);
        busca.value = '';
        avisar(i.nome + ' adicionado');
        renderSugestoes(); renderChips(); renderTudo();
        busca.focus();
      });
      caixa.appendChild(b);
    });
    caixa.hidden = false;
  }

  function renderChips() {
    var raiz = document.getElementById('chips');
    raiz.innerHTML = '';
    if (!selecionados.length) {
      var vazio = document.createElement('span');
      vazio.className = 'chips-vazio';
      vazio.textContent = 'Nada selecionado — busque acima.';
      raiz.appendChild(vazio);
      return;
    }
    selecionados.forEach(function (id) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-mini';
      b.setAttribute('aria-label', 'Remover ' + porId[id].nome + ' da comparação');
      b.textContent = porId[id].nome + ' ×';
      b.addEventListener('click', function () {
        selecionados = selecionados.filter(function (x) { return x !== id; });
        avisar(porId[id].nome + ' removido');
        renderChips(); renderTudo();
      });
      raiz.appendChild(b);
    });
  }

  function renderCampos() {
    var raiz = document.getElementById('campos');
    raiz.innerHTML = '';
    C.campos.forEach(function (c) {
      var on = selCampos.indexOf(c.k) >= 0;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-mini' + (on ? '' : ' outline');
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.textContent = c.rotulo;
      b.addEventListener('click', function () {
        selCampos = on ? selCampos.filter(function (x) { return x !== c.k; })
                       : selCampos.concat([c.k]);
        renderCampos(); renderTudo();
      });
      raiz.appendChild(b);
    });
  }

  /* ── saídas ───────────────────────────────────────────────────────────── */

  function linhasCSV() {
    return selecionados.map(function (id) {
      var linha = { nome: porId[id].nome };
      selCampos.forEach(function (k) { linha[k] = valor(id, k); });
      return linha;
    });
  }

  function renderTabela() {
    var vazio = !selecionados.length || !selCampos.length;
    document.getElementById('msg-vazio').hidden = !vazio;
    document.getElementById('tabela').hidden = vazio;
    if (vazio) return;

    var thead = document.getElementById('thead');
    thead.innerHTML = '';
    var th0 = document.createElement('th');
    th0.scope = 'col';
    th0.textContent = C.rotulo_entidade || 'Entidade';
    thead.appendChild(th0);
    selCampos.forEach(function (k) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = campoDe(k).rotulo;
      thead.appendChild(th);
    });

    var tbody = document.getElementById('tbody');
    tbody.innerHTML = '';
    selecionados.forEach(function (id) {
      var item = porId[id];
      var tr = document.createElement('tr');
      var th = document.createElement('th');
      th.scope = 'row';
      if (item.url) {
        var a = document.createElement('a');
        a.href = item.url;
        a.textContent = item.nome;
        th.appendChild(a);
      } else {
        th.textContent = item.nome;
      }
      if (item.sub) {
        var s = document.createElement('span');
        s.className = 'comp-sub';
        s.textContent = item.sub;
        th.appendChild(s);
      }
      tr.appendChild(th);
      selCampos.forEach(function (k) {
        var td = document.createElement('td');
        var texto = fmt(k, valor(id, k));
        if (texto === null) { td.className = 'sem-dado'; td.textContent = 'sem dados'; }
        else { td.textContent = texto; }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function renderBarras() {
    var raiz = document.getElementById('barras');
    raiz.innerHTML = '';
    if (!selecionados.length || !selCampos.length) return;

    selCampos.forEach(function (k) {
      var valores = selecionados.map(function (id) { return valor(id, k); });
      var validos = valores.filter(function (v) { return v !== null; });
      if (!validos.length) return;
      var maior = Math.max.apply(null, validos.map(Math.abs)) || 1;

      var bloco = document.createElement('div');
      bloco.className = 'barra-bloco';
      var titulo = document.createElement('div');
      titulo.className = 'barra-titulo';
      titulo.textContent = campoDe(k).rotulo;
      bloco.appendChild(titulo);

      selecionados.forEach(function (id, i) {
        var v = valores[i];
        var linha = document.createElement('div');
        linha.className = 'barra-linha';
        var nome = document.createElement('span');
        nome.className = 'barra-nome';
        nome.textContent = porId[id].nome;
        linha.appendChild(nome);

        if (v === null) {
          var nd = document.createElement('span');
          nd.className = 'sem-dado';
          nd.textContent = 'sem dados';
          linha.appendChild(nd);
        } else {
          var trilho = document.createElement('span');
          trilho.className = 'barra-trilho';
          trilho.setAttribute('aria-hidden', 'true');
          var preenche = document.createElement('span');
          preenche.className = 'barra-preenche';
          preenche.style.width = (Math.abs(v) / maior * 100).toFixed(1) + '%';
          preenche.style.background = PALETA[i % PALETA.length];
          trilho.appendChild(preenche);
          linha.appendChild(trilho);
          var val = document.createElement('span');
          val.className = 'barra-valor';
          val.textContent = fmt(k, v);
          linha.appendChild(val);
        }
        bloco.appendChild(linha);
      });
      raiz.appendChild(bloco);
    });
  }

  function renderTudo() { renderTabela(); renderBarras(); }

  document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('busca-entidade').addEventListener('input', renderSugestoes);
    document.getElementById('btn-limpar').addEventListener('click', function () {
      selecionados = [];
      avisar('Comparação esvaziada');
      renderChips(); renderTudo();
    });
    document.getElementById('btn-padrao').addEventListener('click', function () {
      selecionados = C.itens.slice(0, PADRAO_ITENS).map(function (i) { return i.id; });
      avisar('Comparação redefinida');
      renderChips(); renderTudo();
    });
    var btnCSV = document.getElementById('btn-csv');
    if (btnCSV) {
      btnCSV.addEventListener('click', function () {
        exportarCSV(linhasCSV(), 'comparacao_' + C.tipo + '.csv');
      });
    }
    renderChips();
    renderCampos();
    renderTudo();
  });
})();
