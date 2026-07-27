/* Filtros da lista de instituições — mesma técnica do catálogo de cursos:
 * esconder no cliente é instantâneo e mantém o site estático. */
(function () {
  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function filtrar() {
    var termo = sem(document.getElementById('filtro-ies').value.trim());
    var rede = document.getElementById('filtro-rede').value;
    var org = document.getElementById('filtro-org').value;
    var uf = document.getElementById('filtro-uf-ies').value;
    var igc = document.getElementById('filtro-igc').value;
    var visiveis = 0;

    document.querySelectorAll('#tabela-ies tbody tr').forEach(function (tr) {
      var bate = (!termo || sem(tr.dataset.nome).indexOf(termo) >= 0)
        && (!rede || tr.dataset.rede === rede)
        && (!org || tr.dataset.org === org)
        && (!uf || tr.dataset.uf === uf)
        && (!igc || tr.dataset.igc === igc);
      tr.hidden = !bate;
      if (bate) visiveis++;
    });

    document.getElementById('contador-ies').textContent =
      visiveis === 1 ? '1 instituição' : visiveis + ' instituições';
    document.getElementById('ies-vazio').hidden = visiveis > 0;
    document.getElementById('tabela-ies').hidden = visiveis === 0;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var campos = ['filtro-ies', 'filtro-rede', 'filtro-org', 'filtro-uf-ies',
                  'filtro-igc']
      .map(function (id) { return document.getElementById(id); });
    if (campos.some(function (c) { return !c; })) return;
    campos[0].addEventListener('input', filtrar);
    campos.slice(1).forEach(function (c) { c.addEventListener('change', filtrar); });
    filtrar();
  });
})();
