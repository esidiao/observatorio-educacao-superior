/* Busca do cabeçalho — todo o site, não só os cursos.
 *
 * Antes daqui, a caixa achava curso e mais nada. Mas o site tem página para
 * 2.561 instituições, 1.119 municípios e 27 unidades federativas, e para chegar
 * a qualquer uma delas era preciso saber DE ANTEMÃO em qual índice procurar.
 * Quem digitava "UFG" ou "Goiânia" não encontrava nada — não porque a página
 * não existisse, mas porque a busca não olhava para lá.
 *
 * O índice vive em window.INDICE (static/js/indice.js), carregado uma vez e
 * reaproveitado do cache em toda navegação. É uma lista de listas, não de
 * objetos: repetir as chaves quatro mil vezes dobraria o arquivo sem
 * acrescentar informação.
 *
 * Compara sem acentos e sem caixa — quem busca "fisica" precisa achar "Física",
 * e quem busca "goiania" precisa achar "Goiânia".
 */
(function () {
  var LIMITE = 14;          // cabe na tela do celular sem virar rolagem
  var LIMITE_POR_TIPO = 5;  // nenhum grupo pode engolir a lista inteira

  // Ordem dos grupos no resultado. Curso primeiro porque é o que o
  // observatório é; página fixa por último porque quem a procura costuma
  // achá-la pelo menu.
  var TIPOS = [
    { k: 'c', rotulo: 'Curso', url: function (r) { return 'curso/' + r[1] + '/index.html'; },
      meta: function (r) { return milhar(r[2]) + ' vagas · ' + r[3]; } },
    { k: 'i', rotulo: 'Instituição', url: function (r) { return 'instituicao/' + r[1] + '.html'; },
      meta: function (r) {
        var p = [];
        if (r[2]) p.push(r[2]);
        if (r[4]) p.push(milhar(r[4]) + ' matrículas');
        return p.join(' · ');
      },
      // A sigla não aparece no nome ("UFG" não está em "Universidade Federal
      // de Goiás"), e é justamente por ela que se busca uma instituição.
      extra: function (r) { return r[3]; } },
    { k: 'u', rotulo: 'Estado', url: function (r) { return 'uf/' + r[1] + '.html'; },
      meta: function (r) { return r[1]; },
      extra: function (r) { return r[1]; } },
    { k: 'm', rotulo: 'Município', url: function (r) { return 'municipio/' + r[1] + '.html'; },
      meta: function (r) { return r[2] + ' · ' + milhar(r[3]) + ' vagas'; } },
    { k: 'p', rotulo: 'Página', url: function (r) { return r[1]; },
      meta: function () { return ''; } }
  ];

  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function milhar(n) {
    return n === null || n === undefined ? '' : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function ranquear(termo, indice) {
    var q = sem(termo).trim();
    var saida = [];

    if (!q) {
      // Busca vazia: uma amostra de cada tipo, para que a caixa mostre do que
      // ela é capaz antes de a pessoa digitar qualquer coisa.
      TIPOS.forEach(function (t) {
        (indice[t.k] || []).slice(0, t.k === 'c' ? 6 : 3).forEach(function (r) {
          saida.push({ t: t, r: r });
        });
      });
      return saida.slice(0, LIMITE);
    }

    TIPOS.forEach(function (t) {
      var linhas = indice[t.k] || [];
      var achados = [];
      for (var i = 0; i < linhas.length; i++) {
        var pos = sem(linhas[i][0]).indexOf(q);
        if (pos < 0 && t.extra) {
          // Casar pela sigla vale como casar pelo começo do nome: quem digita
          // "UFG" quer aquela instituição, não a que por acaso a contenha.
          var sigla = t.extra(linhas[i]);
          if (sigla && sem(sigla).indexOf(q) === 0) pos = 0;
        }
        if (pos < 0) continue;
        // Nome idêntico ao termo vem antes de tudo: quem digita "medicina"
        // quer Medicina, não Medicina veterinária, por maior que ela seja.
        var exato = sem(linhas[i][0]) === q ? -1 : 0;
        achados.push({ t: t, r: linhas[i], pos: pos, exato: exato,
                       peso: linhas[i][2] || 0 });
      }
      // Quem começa com o termo vem antes; entre iguais, o maior vem antes.
      achados.sort(function (a, b) {
        return a.exato - b.exato || a.pos - b.pos || b.peso - a.peso;
      });
      saida = saida.concat(achados.slice(0, LIMITE_POR_TIPO));
    });

    // Entre grupos, quem casa no começo do nome sobe. A ordenação é estável em
    // todo motor moderno, então a ordem dos TIPOS decide o empate.
    saida.sort(function (a, b) { return (a.exato || 0) - (b.exato || 0) || a.pos - b.pos; });
    return saida.slice(0, LIMITE);
  }

  function iniciar() {
    var input = document.getElementById('curso-busca');
    var lista = document.getElementById('curso-sugestoes');
    var chip = document.getElementById('curso-atual-chip');
    var indice = window.INDICE || {};
    // depth e curso atual vêm de data-* no <body>: um <script> inline aqui
    // obrigaria a CSP a liberar 'unsafe-inline' em script-src.
    var depth = document.body.dataset.depth || '';
    var cursoAtual = document.body.dataset.cursoAtual || '';
    var aviso = document.getElementById('curso-busca-resultado');
    if (!input || !lista || !indice.c) return;

    var total = 0;
    TIPOS.forEach(function (t) { total += (indice[t.k] || []).length; });
    input.placeholder = 'Buscar entre ' + milhar(total) +
      ' cursos, instituições, municípios e estados…';

    if (cursoAtual) {
      var atual = (indice.c || []).filter(function (r) { return r[1] === cursoAtual; })[0];
      if (atual && chip) { chip.textContent = atual[0]; chip.hidden = false; }
    }

    var visiveis = [];
    var foco = -1;

    function fechar() {
      lista.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      foco = -1;
    }

    function desenhar() {
      visiveis = ranquear(input.value, indice);
      if (!visiveis.length) {
        lista.innerHTML = '<li class="vazio">Nada encontrado com esse termo</li>';
        lista.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        if (aviso) aviso.textContent = 'Nenhum resultado';
        return;
      }
      lista.innerHTML = visiveis.map(function (v, i) {
        return '<li role="option" aria-selected="false" data-i="' + i + '" id="curso-op-' + i + '">' +
          '<a href="' + depth + v.t.url(v.r) + '">' +
          '<span class="busca-tipo"></span>' +
          '<span class="nome"></span><span class="meta"></span></a></li>';
      }).join('');
      // Texto por textContent: nome de curso, de instituição e de município
      // vem do Censo e do IBGE — dado, não marcação.
      var itens = lista.querySelectorAll('li');
      for (var i = 0; i < visiveis.length; i++) {
        itens[i].querySelector('.busca-tipo').textContent = visiveis[i].t.rotulo;
        itens[i].querySelector('.nome').textContent = visiveis[i].r[0];
        itens[i].querySelector('.meta').textContent = visiveis[i].t.meta(visiveis[i].r);
      }
      lista.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      if (aviso) {
        aviso.textContent = visiveis.length === 1
          ? '1 resultado, use as setas para navegar'
          : visiveis.length + ' resultados, use as setas para navegar';
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
        window.location.href = depth + visiveis[foco].t.url(visiveis[foco].r);
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
