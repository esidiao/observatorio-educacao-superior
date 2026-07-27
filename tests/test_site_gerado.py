"""
Confere o site depois de gerado.

    python site/build.py && python tests/test_site_gerado.py

Um build parcial é o pior tipo de falha: as páginas que existem parecem certas, e
só quem procurar o curso ausente descobre. Aqui a ausência trava.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
DIST = REPO / "site" / "dist"

# Domínios cuja citação no texto é legítima (links de fonte para o dado oficial).
FONTES_PERMITIDAS = ("www.gov.br",)

falhas = []


def checar(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


def test_paginas_obrigatorias():
    for nome in ("index.html", "comparar-cursos.html", "metodologia.html",
                 "privacidade.html", "404.html",
                 "static/js/cursos.js", "static/js/comparacao.js"):
        checar((DIST / nome).exists(), f"{nome} não foi gerado")


def test_uma_pagina_por_curso():
    catalogo = json.loads((DATA / "cursos.json").read_text(encoding="utf-8"))["cursos"]
    faltando = [c["slug"] for c in catalogo
                if not (DIST / "curso" / c["slug"] / "index.html").exists()]
    checar(not faltando,
           f"{len(faltando)} de {len(catalogo)} cursos sem página "
           f"(ex.: {', '.join(faltando[:5])})")

    # E cada UF com dado precisa da própria página, senão a tabela linka para o vazio.
    sem_uf = []
    for c in catalogo[:40]:                       # amostra: 6 mil arquivos é caro
        nacional = DATA / "cursos" / c["slug"] / "nacional.json"
        if not nacional.exists():
            continue
        ufs = json.loads(nacional.read_text(encoding="utf-8"))["ufs"]
        for uf in ufs:
            if not (DIST / "curso" / c["slug"] / "uf" / f"{uf}.html").exists():
                sem_uf.append(f"{c['slug']}/{uf}")
    checar(not sem_uf, f"páginas de UF ausentes: {sem_uf[:5]}")


def test_sem_recursos_externos():
    """A promessa da página de privacidade tem que valer no HTML publicado."""
    padrao = re.compile(r'(?:src|href)\s*=\s*"(?:https?:)?//([^/"]+)', re.I)
    infratores = {}
    for pagina in DIST.rglob("*.html"):
        for host in padrao.findall(pagina.read_text(encoding="utf-8")):
            if host not in FONTES_PERMITIDAS:
                infratores.setdefault(host, pagina.relative_to(DIST).as_posix())
    checar(not infratores,
           f"páginas carregam recursos de fora: {infratores}")


def test_csp_publicada():
    amostras = [DIST / "index.html", DIST / "comparar-cursos.html"]
    amostras += list((DIST / "curso").glob("*/index.html"))[:3]
    for pagina in amostras:
        if not pagina.exists():
            continue
        texto = pagina.read_text(encoding="utf-8")
        csp = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', texto)
        rel = pagina.relative_to(DIST).as_posix()
        if not checar(csp is not None, f"{rel}: sem CSP"):
            continue
        script_src = re.search(r"script-src([^;]*)", csp.group(1))
        checar(script_src and "'unsafe-inline'" not in script_src.group(1),
               f"{rel}: script-src com 'unsafe-inline'")


def test_dados_embutidos_nao_fecham_script():
    """`</script>` dentro do JSON encerraria a tag e o resto viraria HTML."""
    amostras = list((DIST / "curso").glob("*/index.html"))[:20]
    amostras += list((DIST / "curso").glob("*/uf/*.html"))[:20]
    for pagina in amostras:
        texto = pagina.read_text(encoding="utf-8")
        for bloco in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>',
                                texto, re.S):
            rel = pagina.relative_to(DIST).as_posix()
            checar("<" not in bloco and ">" not in bloco,
                   f"{rel}: JSON embutido contém < ou > sem escape")
            try:
                json.loads(bloco)
            except json.JSONDecodeError as e:
                falhas.append(f"{rel}: JSON embutido inválido ({e})")


def test_paineis_territoriais_e_institucionais():
    """Painel de UF, município e IES: a ausência de um é silenciosa sem checagem."""
    for nome in ("estados.html", "instituicoes.html", "rankings.html", "api.html",
                 "api/v1/cursos.json", "api/v1/estados.json",
                 "api/v1/municipios.json", "api/v1/instituicoes.json"):
        checar((DIST / nome).exists(), f"{nome} não foi gerado")

    caminho = DATA / "instituicoes.json"
    if caminho.exists():
        ies = json.loads(caminho.read_text(encoding="utf-8"))["instituicoes"]
        faltando = [co for co in list(ies)[:60]
                    if not (DIST / "instituicao" / f"{co}.html").exists()]
        checar(not faltando, f"painéis institucionais ausentes: {faltando[:5]}")

    ufs = {p.stem for p in (DIST / "uf").glob("*.html")} if (DIST / "uf").exists() else set()
    checar(len(ufs) == 27, f"{len(ufs)} painéis estaduais (esperados 27)")


def test_comparacoes_e_indices():
    """As três comparações e os índices navegáveis."""
    for nome in ("comparar-cursos.html", "comparar-estados.html",
                 "comparar-instituicoes.html", "municipios.html",
                 "static/js/comparaveis-estados.js",
                 "static/js/comparaveis-instituicoes.js"):
        checar((DIST / nome).exists(), f"{nome} não foi gerado")

    # Todo município listado no índice precisa ter página — senão o índice
    # oferece links para o vazio, que é pior que não listar.
    indice = DIST / "municipios.html"
    if indice.exists():
        alvos = re.findall(r'href="municipio/([^"]+)"', indice.read_text(encoding="utf-8"))
        faltando = [a for a in alvos if not (DIST / "municipio" / a).exists()]
        checar(not faltando,
               f"{len(faltando)} municípios listados sem página: {faltando[:5]}")


def test_exportacao_de_figuras():
    """Página com figura precisa carregar o exportador.

    A barra de download é montada por JS. Se o script deixar de ser incluído, as
    figuras continuam aparecendo e ninguém nota que o download sumiu — falha
    silenciosa, que é a pior espécie.
    """
    checar((DIST / "static" / "js" / "exportar-figura.js").exists(),
           "exportar-figura.js não foi gerado")
    amostras = [DIST / "regioes.html", DIST / "index.html", DIST / "estados.html"]
    amostras += list((DIST / "curso").glob("*/index.html"))[:3]
    for pagina in amostras:
        if not pagina.exists():
            continue
        texto = pagina.read_text(encoding="utf-8")
        if 'class="figura"' not in texto:
            continue
        rel = pagina.relative_to(DIST).as_posix()
        checar("exportar-figura.js" in texto,
               f"{rel}: tem figura mas não carrega o exportador")


# Um exemplar de cada TIPO de página. Varrer 10 mil arquivos iguais não acrescenta;
# o que importa é que nenhum tipo novo entre sem passar pelas mesmas regras.
TIPOS_DE_PAGINA = [
    "index.html", "estados.html", "regioes.html", "redes.html", "acesso.html",
    "municipios.html", "instituicoes.html", "rankings.html", "api.html",
    "metodologia.html", "privacidade.html", "comparar-cursos.html",
    "comparar-estados.html", "comparar-instituicoes.html", "404.html",
]


def test_acessibilidade_das_paginas():
    """Varredura de acessibilidade sobre o HTML publicado.

    A auditoria manual foi feita quando o site tinha seis tipos de página; hoje
    tem vinte. Sem este teste, cada tipo novo pode reintroduzir um salto de
    título, uma tabela sem escopo ou um ícone que o leitor de tela anuncia como
    gráfico anônimo — e ninguém percebe, porque a tela continua bonita.
    """
    alvos = [DIST / n for n in TIPOS_DE_PAGINA]
    alvos += list((DIST / "curso").glob("*/index.html"))[:1]
    alvos += list((DIST / "curso").glob("*/uf/*.html"))[:1]
    alvos += list((DIST / "uf").glob("*.html"))[:1]
    alvos += list((DIST / "municipio").glob("*.html"))[:1]
    alvos += list((DIST / "instituicao").glob("*.html"))[:1]

    for pagina in alvos:
        if not pagina.exists():
            continue
        rel = pagina.relative_to(DIST).as_posix()
        html = pagina.read_text(encoding="utf-8")
        m = re.search(r"<main[^>]*>(.*)</main>", html, re.S)
        main = m.group(1) if m else html

        niveis = [int(n) for n in re.findall(r"<h([1-6])[\s>]", main)]
        checar(bool(niveis), f"{rel}: nenhum título no conteúdo")
        if niveis:
            checar(niveis[0] == 1, f"{rel}: primeiro título é h{niveis[0]}, não h1")
            checar(niveis.count(1) == 1,
                   f"{rel}: {niveis.count(1)} elementos h1 — deve haver exatamente um")
            saltos = [f"h{a}->h{b}" for a, b in zip(niveis, niveis[1:]) if b - a > 1]
            checar(not saltos, f"{rel}: salto de nível de título ({saltos[:2]})")

        for i, tabela in enumerate(re.findall(r"<table[^>]*>.*?</table>", main, re.S), 1):
            checar("<caption" in tabela, f"{rel}: tabela {i} sem <caption>")
            cabecalhos = re.findall(r"<th\b([^>]*)>", tabela)
            sem_scope = [c for c in cabecalhos if "scope=" not in c]
            checar(not sem_scope,
                   f"{rel}: tabela {i} com {len(sem_scope)} th sem scope")

        for campo in re.findall(r"<(?:input|select|textarea)\b([^>]*)>", main):
            tem_id = re.search(r'id="([^"]+)"', campo)
            rotulado = ("aria-label=" in campo or "aria-labelledby=" in campo
                        or (tem_id and f'for="{tem_id.group(1)}"' in main))
            checar(rotulado or 'type="hidden"' in campo,
                   f"{rel}: controle sem rótulo — {campo.strip()[:50]}")

        # SVG é conteúdo (precisa de <title>) ou decoração (precisa de
        # aria-hidden). O que não é nenhum dos dois vira "gráfico" anônimo.
        for svg in re.findall(r"<svg\b[^>]*>.*?</svg>", main, re.S):
            checar('aria-hidden="true"' in svg[:200] or "<title" in svg,
                   f"{rel}: svg sem <title> e sem aria-hidden")


def test_404_com_caminhos_absolutos():
    """O 404 é servido para qualquer endereço, inclusive profundo.

    Um href relativo nele resolve contra o caminho inexistente que o usuário
    digitou — CSS, JS e botões apontam para o vazio. Todo caminho da página
    precisa partir da raiz pública.
    """
    pagina = DIST / "404.html"
    if not pagina.exists():
        return
    texto = pagina.read_text(encoding="utf-8")
    relativos = []
    for atributo, valor in re.findall(r'(href|src)="([^"]+)"', texto):
        if valor.startswith(("/", "#", "http://", "https://", "data:", "mailto:")):
            continue
        relativos.append(f"{atributo}=\"{valor}\"")
    checar(not relativos,
           f"404.html tem caminhos relativos, que quebram em URLs profundas: "
           f"{relativos[:5]}")


def main():
    if not DIST.exists():
        sys.exit("[ERRO] site/dist não existe — rode python site/build.py antes.")
    test_paginas_obrigatorias()
    test_uma_pagina_por_curso()
    test_sem_recursos_externos()
    test_csp_publicada()
    test_dados_embutidos_nao_fecham_script()
    test_paineis_territoriais_e_institucionais()
    test_comparacoes_e_indices()
    test_exportacao_de_figuras()
    test_acessibilidade_das_paginas()
    test_404_com_caminhos_absolutos()

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) no site gerado:\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)

    total = sum(1 for _ in DIST.rglob("*.html"))
    print(f"[PASSOU] {total} páginas: catálogo completo, CSP sem unsafe-inline, "
          f"nenhum recurso externo, JSON embutido íntegro.")


if __name__ == "__main__":
    main()
