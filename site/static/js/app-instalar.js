/* Botão de instalar o observatório como aplicativo.
 *
 * A decisão que governa este arquivo: NADA é gravado no navegador antes do
 * clique. A página de privacidade promete que este site não guarda nada, e
 * quem só visita continua sem cache, sem worker e sem registro — o service
 * worker é registrado aqui, na função do clique, e não no carregamento.
 *
 * Isso custa uma volta a mais. O Chrome só dispara `beforeinstallprompt`
 * depois que existe um service worker registrado, então a ordem natural
 * — esperar o evento para então mostrar o botão — exigiria registrar antes de
 * o visitante pedir. Aqui é ao contrário: o botão aparece, o clique registra,
 * e o convite do navegador vem em seguida. Se não vier em alguns segundos
 * (Safari e Firefox não têm essa API), mostram-se as instruções manuais, que
 * é como se instala nesses navegadores de qualquer jeito.
 */
(function () {
  var ESPERA_CONVITE = 3500;   // margem para o navegador reavaliar o site

  var convite = null;          // o beforeinstallprompt, quando existir
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    convite = e;
  });

  function jaInstalado() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
      || window.navigator.standalone === true;
  }

  function ehApple() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function instrucoes(caixa) {
    caixa.hidden = false;
    caixa.textContent = ehApple()
      ? 'No iPhone e no iPad: toque em Compartilhar e depois em "Adicionar à Tela de Início".'
      : 'Neste navegador, use o menu (⋮) e procure "Instalar" ou "Adicionar à tela inicial".';
  }

  function iniciar() {
    var botao = document.getElementById('instalar-app');
    var caixa = document.getElementById('instalar-aviso');
    if (!botao) return;

    // Sem suporte a service worker não há aplicativo a instalar, e um botão
    // que não faz nada é pior que botão nenhum.
    if (!('serviceWorker' in navigator) || jaInstalado()) {
      botao.hidden = true;
      return;
    }
    botao.hidden = false;

    botao.addEventListener('click', function () {
      botao.disabled = true;
      var rotulo = botao.textContent;
      botao.textContent = 'preparando…';

      // É aqui, e só aqui, que algo passa a ser gravado no navegador.
      navigator.serviceWorker.register('./sw.js').then(function () {
        return new Promise(function (resolve) {
          if (convite) return resolve(convite);
          var t = setTimeout(function () { resolve(null); }, ESPERA_CONVITE);
          window.addEventListener('beforeinstallprompt', function (e) {
            e.preventDefault();
            convite = e;
            clearTimeout(t);
            resolve(e);
          }, { once: true });
        });
      }).then(function (evento) {
        botao.textContent = rotulo;
        botao.disabled = false;
        if (!evento) { instrucoes(caixa); return; }
        evento.prompt();
        return evento.userChoice.then(function (escolha) {
          if (escolha && escolha.outcome === 'accepted') {
            botao.hidden = true;
            if (caixa) {
              caixa.hidden = false;
              caixa.textContent = 'Aplicativo instalado. As páginas visitadas '
                + 'passam a funcionar sem conexão.';
            }
          }
        });
      }).catch(function () {
        botao.textContent = rotulo;
        botao.disabled = false;
        instrucoes(caixa);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
