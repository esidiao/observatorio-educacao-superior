/* Filtro do índice de municípios.
 *
 * A numeração da primeira coluna é recalculada a cada filtro: deixar o número
 * original faria a lista filtrada começar em "37", como se faltassem itens. */
(function () {
  function sem(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function filtrar() {
    var termo = sem(document.getElementById('filtro-municipio').value.trim());
    var uf = document.getElementById('filtro-uf-mun').value;
    var visiveis = 0;

    document.querySelectorAll('#tabela-municipios tbody tr').forEach(function (tr) {
      var bate = (!termo || sem(tr.dataset.nome).indexOf(termo) >= 0)
        && (!uf || tr.dataset.uf === uf);
      tr.hidden = !bate;
      if (bate) {
        visiveis++;
        var celula = tr.querySelector('.rank');
        if (celula) celula.textContent = visiveis;
      }
    });

    document.getElementById('contador-municipios').textContent =
      visiveis === 1 ? '1 município' : visiveis + ' municípios';
    document.getElementById('municipios-vazio').hidden = visiveis > 0;
    document.getElementById('tabela-municipios').hidden = visiveis === 0;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var nome = document.getElementById('filtro-municipio');
    var uf = document.getElementById('filtro-uf-mun');
    if (!nome || !uf) return;
    nome.addEventListener('input', filtrar);
    uf.addEventListener('change', filtrar);
    filtrar();
  });
})();
