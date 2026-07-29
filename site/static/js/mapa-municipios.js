/* Mapa municipal interativo do painel estadual.
 *
 * Cada círculo do mapa carrega em data-* a população, as matrículas, o número
 * de instituições e o de cursos do município. Este arquivo liga o mapa ao
 * painel de leitura e à tabela abaixo, nos dois sentidos: apontar um município
 * no mapa destaca a linha na tabela, e percorrer a tabela destaca o ponto no
 * mapa.
 *
 * Sobre teclado, e a decisão que isso exigiu. Um estado grande tem mais de cem
 * círculos; torná-los todos focáveis criaria mais de cem paradas de tabulação
 * antes do resto da página, o que atrapalha muito mais gente do que ajuda. O
 * caminho de teclado é a TABELA, que já existe, já tem link por município e já
 * é navegável — e que agora alimenta o mesmo painel. Quem usa mouse ganha o
 * mapa; quem usa teclado ganha a tabela; os dois veem os mesmos quatro números
 * no mesmo lugar.
 *
 * Sem JS a página continua inteira: o <title> de cada círculo traz os quatro
 * números e o navegador o mostra como dica nativa.
 */
(function () {
  function milhar(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function iniciar() {
    var mapa = document.querySelector('.figura svg.mapa');
    var painel = document.getElementById('mapa-painel');
    if (!mapa || !painel) return;

    // Circulo ou area: o que importa e carregar o codigo do municipio.
    var pontos = mapa.querySelectorAll('[data-cod-ibge]');
    if (!pontos.length) return;

    var campos = {
      nome: painel.querySelector('[data-campo="nome"]'),
      populacao: painel.querySelector('[data-campo="populacao"]'),
      matriculas: painel.querySelector('[data-campo="matriculas"]'),
      n_ies: painel.querySelector('[data-campo="n_ies"]'),
      n_cursos: painel.querySelector('[data-campo="n_cursos"]')
    };
    var vazio = painel.querySelector('.mapa-painel-vazio');
    var conteudo = painel.querySelector('.mapa-painel-dados');

    // A tabela indexada por código IBGE: é por ele que mapa e tabela se acham.
    // Nome não serve — o país tem dezenas de municípios homônimos.
    var linhas = {};
    Array.prototype.forEach.call(
      document.querySelectorAll('tr[data-cod]'),
      function (tr) { linhas[tr.getAttribute('data-cod')] = tr; });

    var ativo = null;

    function limparDestaque() {
      Array.prototype.forEach.call(pontos, function (p) {
        p.classList.remove('destacado');
      });
      Object.keys(linhas).forEach(function (c) {
        linhas[c].classList.remove('destacada');
      });
    }

    function mostrar(elemento) {
      var cod = elemento.getAttribute('data-cod-ibge') ||
                elemento.getAttribute('data-cod');
      if (!cod || cod === ativo) return;
      ativo = cod;
      limparDestaque();

      var ponto = mapa.querySelector('[data-cod-ibge="' + cod + '"]');
      if (ponto) ponto.classList.add('destacado');
      if (linhas[cod]) linhas[cod].classList.add('destacada');

      // A fonte do texto é sempre o círculo: um só lugar guarda os números, e
      // o painel não pode discordar do mapa.
      var origem = ponto || elemento;
      var nome = (ponto && ponto.querySelector('title'))
        ? ponto.querySelector('title').textContent.split(':')[0]
        : (linhas[cod] ? linhas[cod].querySelector('th').textContent.trim() : '');
      campos.nome.textContent = nome;

      ['populacao', 'matriculas', 'n-ies', 'n-cursos'].forEach(function (attr) {
        var chave = attr.replace('-', '_');
        var v = origem.getAttribute('data-' + attr);
        // Ausente não vira zero: zero afirmaria que o município não tem
        // nenhuma instituição, o que é diferente de não sabermos o número.
        campos[chave].textContent = (v === null || v === '') ? '—' : milhar(v);
      });

      if (vazio) vazio.hidden = true;
      if (conteudo) conteudo.hidden = false;
    }

    Array.prototype.forEach.call(pontos, function (p) {
      p.addEventListener('mouseenter', function () { mostrar(p); });
      p.addEventListener('click', function () { mostrar(p); });
    });

    Object.keys(linhas).forEach(function (cod) {
      var tr = linhas[cod];
      tr.addEventListener('mouseenter', function () { mostrar(tr); });
      // focusin sobe do link dentro da célula: é como o teclado chega aqui.
      tr.addEventListener('focusin', function () { mostrar(tr); });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
