"""
Portão de layout: mede o site num navegador de verdade, em três larguras.

    python tests/test_viewport.py

Por que este arquivo existe. Os outros quatro portões leem texto — templates,
HTML publicado, CSS. Isso pega muita coisa, mas não pega nada que só apareça
depois que um motor de layout calcula a página. Os defeitos móveis corrigidos
em julho de 2026 eram todos desse tipo: rótulo de gráfico chegando ao olho com
5px porque o SVG encolhia para 55%, alvo de toque de 19px de altura, menu de
navegação ocupando 161px antes de o conteúdo começar. Nenhum dos quatro
portões podia vê-los; foram achados medindo à mão. Este arquivo existe para
que não seja preciso lembrar de medir.

O que se checa, e onde:

    transbordo horizontal   todas as larguras — página que rola para o lado é
                            defeito em qualquer tela
    piso tipográfico        até 1024px — texto de apoio abaixo de ~13px
    alvo de toque           até 1024px — controle abaixo de 24x24 CSS
                            (WCAG 2.2, 2.5.8), com a isenção de link em frase
    escala da figura        celular — o SVG não pode ser reduzido a ponto de
                            apagar os próprios rótulos
    axe-core                celular, nos temas claro E escuro — regras wcag2a
                            e wcag2aa que só existem no DOM montado: papéis,
                            foco, e o contraste calculado sobre o fundo real

O servidor local é obrigatório: sobre file:// os caminhos absolutos da página
de 404 não resolvem, e o navegador trata cada arquivo como origem distinta, o
que muda o comportamento da CSP e falsearia o teste.
"""
import functools
import http.server
import json
import pathlib
import socket
import sys
import threading

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DIST = RAIZ / "site" / "dist"

PISO_PX = 12.9          # ~0,82rem: o piso tipográfico do celular
ALVO_MIN = 24           # WCAG 2.2, critério 2.5.8 (AA)
ESCALA_MIN = 0.95       # figura reduzida além disso apaga os próprios rótulos

LARGURAS = [
    ("celular", 375, 812),
    ("tablet", 768, 1024),
    ("desktop", 1280, 900),
]

# Um exemplar de cada TIPO de página. Varrer 10 mil arquivos com o mesmo molde
# não acrescenta informação — acrescenta minutos.
AMOSTRA = [
    "index.html",
    "estados.html",
    "regioes.html",
    "redes.html",
    "acesso.html",
    "municipios.html",
    "instituicoes.html",
    "rankings.html",
    "api.html",
    "metodologia.html",
    "privacidade.html",
    "autor.html",
    "aviso-legal.html",
    "comparar-cursos.html",
    "404.html",
    "curso/medicina/index.html",
    "curso/medicina/uf/GO.html",
    "uf/GO.html",
]

# axe é caro: roda no subconjunto que cobre os moldes distintos de conteúdo.
AMOSTRA_AXE = ["index.html", "curso/medicina/index.html", "rankings.html",
               "autor.html", "aviso-legal.html"]

falhas = []


def checar(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


def servir(diretorio):
    """Sobe um servidor estático em porta livre e devolve (url_base, encerrar)."""
    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass

    manipulador = functools.partial(Silencioso, directory=str(diretorio))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", porta), manipulador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{porta}", servidor.shutdown


# O script roda dentro da página. Devolve a lista de problemas medidos; a
# decisão sobre o que é falha fica do lado do Python, não do navegador.
MEDIR = """
(cfg) => {
  const probs = [];
  const vis = e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // 1. Transbordo horizontal, e quem o causa.
  if (document.documentElement.scrollWidth > cfg.largura + 1) {
    const culpados = [...document.querySelectorAll('body *')].filter(e => {
      if (!vis(e)) return false;
      // Elemento dentro de um contêiner que rola de propósito não é culpado.
      for (let a = e; a; a = a.parentElement) {
        const ox = getComputedStyle(a).overflowX;
        if (ox === 'auto' || ox === 'scroll') return false;
      }
      return e.getBoundingClientRect().right > cfg.largura + 1;
    }).slice(0, 3).map(e => e.tagName.toLowerCase() + '.' +
        ((e.className || '') + '').split(' ')[0]);
    probs.push({tipo: 'transbordo',
                detalhe: document.documentElement.scrollWidth + 'px de conteúdo',
                quem: culpados});
  }

  if (cfg.toque) {
    // 2. Piso tipográfico. Só elementos com texto próprio, para não contar o
    //    mesmo texto uma vez por ancestral.
    const pequenos = new Map();
    for (const e of document.querySelectorAll('body *')) {
      if (!e.firstChild || e.firstChild.nodeType !== 3) continue;
      if (!e.textContent.trim() || !vis(e)) continue;
      if (e.namespaceURI && e.namespaceURI.includes('svg')) continue;  // viewBox
      const px = parseFloat(getComputedStyle(e).fontSize);
      if (px < cfg.piso) {
        const chave = e.tagName.toLowerCase() + '.' +
                      ((e.className || '') + '').split(' ')[0] + ' ' + px + 'px';
        pequenos.set(chave, (pequenos.get(chave) || 0) + 1);
      }
    }
    if (pequenos.size) {
      probs.push({tipo: 'texto-pequeno', quem: [...pequenos.keys()].slice(0, 5)});
    }

    // 3. Alvos de toque. A isenção do 2.5.8 vale para link em linha dentro de
    //    um bloco de texto — ali o tamanho é consequência da frase, não
    //    descuido. Link que virou bloco (o desenho o destacou) é cobrado.
    const miudos = new Set();
    for (const e of document.querySelectorAll('a, button, input, select, summary')) {
      if (!vis(e)) continue;
      const r = e.getBoundingClientRect();
      if (r.height >= cfg.alvo && r.width >= cfg.alvo) continue;
      if (e.tagName === 'A' && getComputedStyle(e).display === 'inline') {
        const pai = e.parentElement;
        if (pai && pai.textContent.trim().length > 60) continue;   // em frase
      }
      miudos.add(e.tagName.toLowerCase() + '.' +
                 ((e.className || '') + '').split(' ')[0] + ' ' +
                 Math.round(r.width) + 'x' + Math.round(r.height));
    }
    if (miudos.size) probs.push({tipo: 'alvo-pequeno', quem: [...miudos].slice(0, 5)});
  }

  // 4. Escala das figuras: o texto do SVG é escrito em unidades do viewBox, e
  //    encolhe junto com o desenho.
  if (cfg.figura) {
    for (const tela of document.querySelectorAll('.figura-tela')) {
      const svg = tela.querySelector('svg');
      if (!svg) continue;
      const vb = (svg.getAttribute('viewBox') || '0 0 1 1').split(/\\s+/).map(Number);
      const escala = svg.getBoundingClientRect().width / vb[2];
      if (escala < cfg.escala) {
        probs.push({tipo: 'figura-encolhida',
                    detalhe: 'escala ' + escala.toFixed(2) +
                             ' — os rótulos encolhem junto'});
        break;
      }
    }
  }
  return probs;
}
"""


def medir(pagina, contexto, base):
    from playwright.sync_api import Error as ErroPlaywright

    for nome, largura, altura in LARGURAS:
        pag = contexto.new_page()
        pag.set_viewport_size({"width": largura, "height": altura})
        try:
            pag.goto(f"{base}/{pagina}", wait_until="load", timeout=30000)
            pag.wait_for_timeout(350)     # o JS da página monta tabelas e barras
            problemas = pag.evaluate(MEDIR, {
                "largura": largura,
                "piso": PISO_PX,
                "alvo": ALVO_MIN,
                "escala": ESCALA_MIN,
                "toque": largura <= 1024,
                "figura": nome == "celular",
            })
        except ErroPlaywright as erro:
            falhas.append(f"{pagina} [{nome}]: não carregou — {erro}")
            pag.close()
            continue
        for p in problemas:
            detalhe = p.get("detalhe", "")
            quem = ", ".join(p.get("quem", []))
            falhas.append(f"{pagina} [{nome}] {p['tipo']}: "
                          f"{detalhe}{' · ' if detalhe and quem else ''}{quem}")
        pag.close()


# A lista de sugestoes so existe depois que alguem digita. Fechada, ela e
# invisivel para a varredura — e e por ela que se chega a instituicao,
# municipio e estado, entao e navegacao principal, nao enfeite.
ABRIR_BUSCA = """
(termo) => {
  const input = document.getElementById('curso-busca');
  const lista = document.getElementById('curso-sugestoes');
  if (!input || !lista) return null;
  input.value = termo;
  input.dispatchEvent(new Event('input'));
  const itens = [...lista.querySelectorAll('li')];
  const miudos = itens.map(li => li.querySelector('a')).filter(Boolean)
    .map(a => a.getBoundingClientRect())
    .filter(r => r.width > 0 && (r.height < 24 || r.width < 24));
  return {
    n: itens.length,
    tipos: [...new Set(itens.map(li => {
      const s = li.querySelector('.busca-tipo');
      return s ? s.textContent : '';
    }))],
    semRotulo: itens.filter(li => !li.getAttribute('role')).length,
    miudos: miudos.length,
    transborda: lista.getBoundingClientRect().right > innerWidth + 1,
    expandido: input.getAttribute('aria-expanded'),
  };
}
"""

# Termo -> tipo que ele TEM de trazer. Sem isto a checagem so verificava que
# "algo voltou", e algo sempre volta: numa sabotagem que apagou municipios,
# estados e paginas do indice, a busca por "goias" seguiu achando uma
# faculdade com essa palavra no nome, e o portao passou. Portao que nao falha
# quando o defeito existe nao e portao.
TERMOS = [
    ("goias", "Estado"),
    ("goiania", "Municipio"),
    ("privac", "Pagina"),
    ("medicina", "Curso"),
    ("universidade federal", "Instituicao"),
]


def _sem_acento(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def medir_busca(pagina, contexto, base):
    """A busca do cabecalho, aberta, nas larguras de toque."""
    for nome, largura, altura in LARGURAS:
        pag = contexto.new_page()
        pag.set_viewport_size({"width": largura, "height": altura})
        pag.goto(f"{base}/{pagina}", wait_until="load", timeout=30000)
        pag.wait_for_timeout(350)
        for termo, tipo_esperado in TERMOS:
            r = pag.evaluate(ABRIR_BUSCA, termo)
            if r is None:
                falhas.append(f"{pagina} [{nome}] busca: caixa ausente")
                break
            achados = [_sem_acento(x) for x in r["tipos"]]
            if tipo_esperado not in achados:
                falhas.append(f"{pagina} [{nome}] busca: '{termo}' nao trouxe "
                              f"nenhum resultado do tipo {tipo_esperado} "
                              f"(veio: {', '.join(achados) or 'nada'})")
        if r is None:
            pag.close()
            continue
        else:
            if r["semRotulo"]:
                falhas.append(f"{pagina} [{nome}] busca: {r['semRotulo']} sugestao(oes) "
                              f"sem role=option")
            if r["miudos"] and largura <= 1024:
                falhas.append(f"{pagina} [{nome}] busca: {r['miudos']} sugestao(oes) "
                              f"com alvo abaixo de {ALVO_MIN}px")
            if r["transborda"]:
                falhas.append(f"{pagina} [{nome}] busca: a lista sai da tela")
            if r["expandido"] != "true":
                falhas.append(f"{pagina} [{nome}] busca: aria-expanded nao virou true")
        pag.close()


def rodar_axe(pagina, navegador, base, tema):
    """axe nos dois temas.

    O layout não muda com o tema, então a medição de transbordo e de alvo roda
    uma vez só. O contraste muda inteiro: cada token tem dois valores, e o
    portão de tokens confere a paleta declarada — não o que sobra depois de a
    cor cair sobre o fundo real de cada elemento. Só axe vê isso, e só vê no
    tema que estiver ativo.
    """
    from axe_core_python.sync_playwright import Axe

    contexto = navegador.new_context(color_scheme=tema)
    pag = contexto.new_page()
    pag.set_viewport_size({"width": 375, "height": 812})
    pag.goto(f"{base}/{pagina}", wait_until="load", timeout=30000)
    pag.wait_for_timeout(350)
    resultado = Axe().run(pag, options={
        "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a",
                                              "wcag21aa", "wcag22aa"]}})
    for v in resultado.get("violations", []):
        alvos = "; ".join(a["target"][0] for a in v["nodes"][:2])
        falhas.append(f"{pagina} [axe/{tema}/{v['impact']}] {v['id']}: "
                      f"{v['help']} — {alvos}")
    pag.close()
    contexto.close()


def main():
    if not DIST.exists():
        print("[ERRO] site/dist não existe. Rode python site/build.py antes.")
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERRO] playwright não instalado: pip install playwright "
              "&& python -m playwright install chromium")
        return 1

    ausentes = [p for p in AMOSTRA if not (DIST / p).exists()]
    if ausentes:
        print(f"[ERRO] páginas da amostra ausentes no build: {ausentes}")
        return 1

    base, encerrar = servir(DIST)
    try:
        with sync_playwright() as pw:
            navegador = pw.chromium.launch()
            # Sem deviceScaleFactor nem isMobile: o que se mede aqui é o
            # layout em CSS pixels, que é o que as regras tratam.
            contexto = navegador.new_context()
            for pagina in AMOSTRA:
                medir(pagina, contexto, base)
            medir_busca("index.html", contexto, base)
            for tema in ("light", "dark"):
                for pagina in AMOSTRA_AXE:
                    rodar_axe(pagina, navegador, base, tema)
            navegador.close()
    finally:
        encerrar()

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) de layout ou acessibilidade:\n")
        for f in falhas:
            print(f"  · {f}")
        return 1
    print(f"[PASSOU] {len(AMOSTRA)} tipos de página em {len(LARGURAS)} larguras: "
          f"sem transbordo, sem texto abaixo de {PISO_PX}px, sem alvo abaixo de "
          f"{ALVO_MIN}px, figuras em escala; axe limpo em {len(AMOSTRA_AXE)} "
          f"páginas, nos temas claro e escuro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
