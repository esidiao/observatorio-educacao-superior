/* Seletor de curso do cabeçalho.
 *
 * O catálogo tem centenas de cursos, então a navegação é busca, não lista: repetir
 * todos os rótulos no HTML de cada página custaria mais bytes que todo o resto do
 * site somado. A lista vive em window.CURSOS (static/js/cursos.js), carregada uma
 * vez e reaproveitada do cache em toda navegação.
 *
 * Compara sem acentos e sem caixa — quem busca "fisica" precisa achar "Física", e
 * quem busca "gestao" precisa achar as dezenas de "Gestão de …".
 */
(function () {
  var LIMITE = 12;

  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function milhar(n) {
    return n === null || n === undefined ? '' : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function ranquear(termo, cursos) {
    var q = sem(termo).trim();
    if (!q) {
      return cursos.slice(0, LIMITE); // já vem ordenado por vagas
    }
    var pontuados = [];
    for (var i = 0; i < cursos.length; i++) {
      var pos = sem(cursos[i].n).indexOf(q);
      if (pos < 0) continue;
      // Quem começa com o termo vem antes; entre iguais, o curso maior vem antes.
      pontuados.push({ c: cursos[i], pos: pos });
    }
    pontuados.sort(function (a, b) { return a.pos - b.pos || (b.c.v || 0) - (a.c.v || 0); });
    return pontuados.slice(0, LIMITE).map(function (p) { return p.c; });
  }

  function iniciar() {
    var input = document.getElementById('curso-busca');
    var lista = document.getElementById('curso-sugestoes');
    var chip = document.getElementById('curso-atual-chip');
    var cursos = window.CURSOS || [];
    // depth e curso atual vêm de data-* no <body>: um <script> inline aqui
    // obrigaria a CSP a liberar 'unsafe-inline' em script-src.
    var depth = document.body.dataset.depth || '';
    var cursoAtual = document.body.dataset.cursoAtual || '';
    var aviso = document.getElementById('curso-busca-resultado');
    if (!input || !lista || !cursos.length) return;

    input.placeholder = 'Buscar entre ' + cursos.length + ' cursos do Censo…';

    if (cursoAtual) {
      var atual = cursos.filter(function (c) { return c.s === cursoAtual; })[0];
      if (atual) { chip.textContent = atual.n; chip.hidden = false; }
    }

    var visiveis = [];
    var foco = -1;

    function fechar() {
      lista.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      foco = -1;
    }

    function desenhar() {
      visiveis = ranquear(input.value, cursos);
      if (!visiveis.length) {
        lista.innerHTML = '<li class="vazio">Nenhum curso com esse termo</li>';
        lista.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        if (aviso) aviso.textContent = 'Nenhum curso encontrado';
        return;
      }
      lista.innerHTML = visiveis.map(function (c, i) {
        return '<li role="option" aria-selected="false" data-i="' + i + '" id="curso-op-' + i + '">' +
          '<a href="' + depth + 'curso/' + c.s + '/index.html">' +
          '<span class="nome"></span><span class="meta"></span></a></li>';
      }).join('');
      // Texto por textContent: nome de curso vem do Censo, não vira HTML.
      var itens = lista.querySelectorAll('li');
      for (var i = 0; i < visiveis.length; i++) {
        itens[i].querySelector('.nome').textContent = visiveis[i].n;
        itens[i].querySelector('.meta').textContent =
          milhar(visiveis[i].v) + ' vagas · ' + visiveis[i].a;
      }
      lista.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      if (aviso) {
        aviso.textContent = visiveis.length === 1
          ? '1 curso encontrado, use as setas para navegar'
          : visiveis.length + ' cursos encontrados, use as setas para navegar';
      }
    }

    function marcar() {
      var itens = lista.querySelectorAll('li');
      for (var i = 0; i < itens.length; i++) {
        itens[i].classList.toggle('foco', i === foco);
        itens[i].setAttribute('aria-selected', i === foco ? 'true' : 'false');
      }
      input.setAttribute('aria-activedescendant', foco >= 0 ? 'curso-op-' + foco : '');
    }

    input.addEventListener('input', function () { foco = -1; desenhar(); });
    input.addEventListener('focus', desenhar);

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { fechar(); input.blur(); return; }
      if (lista.hidden || !visiveis.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); foco = (foco + 1) % visiveis.length; marcar(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); foco = (foco <= 0 ? visiveis.length : foco) - 1; marcar(); }
      else if (e.key === 'Enter' && foco >= 0) {
        e.preventDefault();
        window.location.href = depth + 'curso/' + visiveis[foco].s + '/index.html';
      }
    });

    document.addEventListener('click', function (e) {
      if (!lista.contains(e.target) && e.target !== input) fechar();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
