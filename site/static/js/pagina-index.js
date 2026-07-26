/* Filtro do catálogo da home.
 *
 * Com centenas de cartões, esconder no cliente é instantâneo e mantém o site
 * estático — sem índice remoto, sem paginação. A contagem vai para uma região
 * aria-live: quem não vê a tela precisa saber que o filtro surtiu efeito.
 */
(function () {
  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function filtrar() {
    var campoNome = document.getElementById('filtro-curso');
    var campoArea = document.getElementById('filtro-area');
    if (!campoNome || !campoArea) return;

    var termo = sem(campoNome.value.trim());
    var area = campoArea.value;
    var visiveis = 0;

    document.querySelectorAll('.area-bloco').forEach(function (bloco) {
      var mostrarBloco = !area || bloco.dataset.area === area;
      var naArea = 0;
      bloco.querySelectorAll('.curso-card').forEach(function (card) {
        var bate = mostrarBloco && (!termo || sem(card.dataset.nome).indexOf(termo) >= 0);
        card.hidden = !bate;
        if (bate) { naArea++; visiveis++; }
      });
      bloco.hidden = naArea === 0;
    });

    var contador = document.getElementById('filtro-contador');
    if (contador) {
      contador.textContent = visiveis === 1 ? '1 curso' : visiveis + ' cursos';
    }
    var vazio = document.getElementById('catalogo-vazio');
    if (vazio) vazio.hidden = visiveis > 0;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var nome = document.getElementById('filtro-curso');
    var area = document.getElementById('filtro-area');
    if (!nome || !area) return;
    nome.addEventListener('input', filtrar);
    area.addEventListener('change', filtrar);
    filtrar();
  });
})();
