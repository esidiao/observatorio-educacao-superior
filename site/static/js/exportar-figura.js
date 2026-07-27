/* Exportação de mapas e gráficos em SVG e PNG.
 *
 * Sem biblioteca: a Content-Security-Policy proíbe recurso de terceiro, e a
 * conversão cabe em poucas linhas com o que o navegador já oferece —
 * XMLSerializer para o SVG, canvas para o PNG.
 *
 * Um cuidado que não é óbvio: as figuras são geradas no build sem `font-family`,
 * herdando a tipografia da página pelo CSS. Um SVG salvo assim abre com a fonte
 * padrão de quem abrir, e o PNG rasteriza com serifa genérica — os rótulos
 * mudam de largura e passam a colidir. Por isso a cópia exportada recebe fonte e
 * fundo próprios: o arquivo tem de ser legível sozinho, longe deste site.
 */
(function () {
  var FONTE = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';
  var ESCALA_PNG = 2;   // dobra a resolução: gráfico citado costuma ir para slide

  function preparar(svg) {
    var copia = svg.cloneNode(true);
    copia.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    copia.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');

    var caixa = svg.getBoundingClientRect();
    var vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/);
    var largura = Math.round(caixa.width) || Number(vb[2]) || 600;
    var altura = Math.round(caixa.height) || Number(vb[3]) || 400;
    copia.setAttribute('width', largura);
    copia.setAttribute('height', altura);

    // Fundo branco: sem ele o PNG sai transparente e o texto escuro some quando
    // colado sobre fundo escuro.
    var fundo = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    fundo.setAttribute('width', '100%');
    fundo.setAttribute('height', '100%');
    fundo.setAttribute('fill', '#FFFFFF');
    copia.insertBefore(fundo, copia.firstChild);

    var estilo = document.createElementNS('http://www.w3.org/2000/svg', 'style');
    estilo.textContent = 'text{font-family:' + FONTE + '}';
    copia.insertBefore(estilo, copia.firstChild);

    return {
      texto: '<?xml version="1.0" encoding="UTF-8"?>\n'
        + new XMLSerializer().serializeToString(copia),
      largura: largura,
      altura: altura,
    };
  }

  function nomeArquivo(svg, extensao) {
    var titulo = svg.querySelector('title');
    var base = (titulo ? titulo.textContent : 'figura')
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase();
    return (base || 'figura').slice(0, 70) + '.' + extensao;
  }

  function salvar(blob, nome) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function exportarSVG(svg) {
    var p = preparar(svg);
    salvar(new Blob([p.texto], { type: 'image/svg+xml;charset=utf-8' }),
           nomeArquivo(svg, 'svg'));
  }

  function exportarPNG(svg, botao) {
    var p = preparar(svg);
    var img = new Image();
    var rotuloOriginal = botao.textContent;
    botao.disabled = true;
    botao.textContent = 'gerando…';

    img.onload = function () {
      var canvas = document.createElement('canvas');
      canvas.width = p.largura * ESCALA_PNG;
      canvas.height = p.altura * ESCALA_PNG;
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (blob) {
        if (blob) salvar(blob, nomeArquivo(svg, 'png'));
        botao.disabled = false;
        botao.textContent = rotuloOriginal;
      }, 'image/png');
    };
    img.onerror = function () {
      botao.disabled = false;
      botao.textContent = rotuloOriginal;
      var aviso = botao.parentElement.querySelector('.export-erro');
      if (aviso) aviso.textContent = 'Não foi possível gerar o PNG. O SVG funciona.';
    };
    // data: URI em vez de blob: URL — a CSP permite img-src data:, e evita
    // depender de origem para o carregamento da imagem.
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(p.texto);
  }

  function montarBarra(figura, svg) {
    var barra = document.createElement('div');
    barra.className = 'export-barra';

    var rotulo = document.createElement('span');
    rotulo.className = 'export-rotulo';
    rotulo.textContent = 'Baixar figura:';
    barra.appendChild(rotulo);

    [['SVG', exportarSVG], ['PNG', exportarPNG]].forEach(function (par) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn outline btn-mini';
      b.textContent = '↓ ' + par[0];
      b.setAttribute('aria-label', 'Baixar esta figura em ' + par[0]);
      b.addEventListener('click', function () { par[1](svg, b); });
      barra.appendChild(b);
    });

    var erro = document.createElement('span');
    erro.className = 'export-erro';
    erro.setAttribute('role', 'status');
    erro.setAttribute('aria-live', 'polite');
    barra.appendChild(erro);

    figura.appendChild(barra);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.figura').forEach(function (figura) {
      var svg = figura.querySelector('svg');
      if (svg) montarBarra(figura, svg);
    });
  });
})();
