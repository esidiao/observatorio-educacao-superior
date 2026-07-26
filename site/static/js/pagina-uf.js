/* Página de uma UF dentro de um curso — só o botão de exportar precisa de JS. */
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('btn-json-uf');
    if (!btn) return;
    var el = document.getElementById('dados-uf');
    if (!el) return;
    var dados;
    try { dados = JSON.parse(el.textContent); } catch (e) { return; }
    btn.addEventListener('click', function () {
      exportarJSON(dados, btn.dataset.arquivo || 'uf.json');
    });
  });
})();
