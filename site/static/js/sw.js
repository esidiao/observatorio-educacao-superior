/* Service worker do aplicativo instalável.
 *
 * Só existe depois que alguém instala. A página de privacidade promete que
 * este site não grava nada no navegador, e essa promessa vale para quem
 * apenas visita: o registro acontece no clique de "Instalar aplicativo", nunca
 * no carregamento. Quem nunca clicou não tem cache, não tem worker, não tem
 * nada — exatamente como antes.
 *
 * O que ele guarda: cópias das páginas públicas que a pessoa abriu, para que
 * elas funcionem sem rede. Nada de identificador, nada de comportamento, nada
 * que não estivesse já no HTML que o navegador baixou. Desinstalar o
 * aplicativo apaga tudo.
 *
 * Estratégia. Rede primeiro, cache como reserva. O contrário — cache primeiro —
 * seria mais rápido e mostraria números velhos como se fossem atuais, que num
 * observatório de dados oficiais é o pior tipo de erro: silencioso e plausível.
 * Com rede primeiro, quem está conectado vê sempre a edição publicada; o cache
 * só entra quando não há rede.
 */
var CACHE = 'observatorio-v1';

// O mínimo para a casca abrir offline. O resto entra conforme se navega.
var ESSENCIAIS = [
  './',
  './index.html',
  './static/css/style.css',
  './static/js/indice.js',
  './static/js/busca-global.js',
  './static/img/marca.svg',
  './offline.html',
];

self.addEventListener('install', function (evento) {
  evento.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // addAll falha inteiro se um arquivo faltar; aqui cada um é opcional,
      // porque um 404 numa página secundária não pode impedir a instalação.
      return Promise.all(ESSENCIAIS.map(function (url) {
        return cache.add(url).catch(function () { return null; });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (evento) {
  evento.waitUntil(
    caches.keys().then(function (chaves) {
      return Promise.all(chaves.map(function (k) {
        // Versão anterior sai inteira: cache de site estático não se migra,
        // se refaz.
        return k === CACHE ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (evento) {
  var req = evento.request;
  if (req.method !== 'GET') return;
  // Só o próprio site. Não há recurso de terceiro aqui, e se um dia houver,
  // não é o worker que vai começar a buscá-lo.
  if (new URL(req.url).origin !== self.location.origin) return;

  evento.respondWith(
    fetch(req).then(function (resposta) {
      if (resposta && resposta.status === 200 && resposta.type === 'basic') {
        var copia = resposta.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copia); });
      }
      return resposta;
    }).catch(function () {
      return caches.match(req).then(function (guardada) {
        if (guardada) return guardada;
        // Sem rede e sem cópia: uma página que explica, em vez do erro cru do
        // navegador, que não diz se o site caiu ou se foi a conexão.
        if (req.mode === 'navigate') return caches.match('./offline.html');
        return new Response('', { status: 504, statusText: 'Sem rede' });
      });
    })
  );
});
