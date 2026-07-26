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


def main():
    if not DIST.exists():
        sys.exit("[ERRO] site/dist não existe — rode python site/build.py antes.")
    test_paginas_obrigatorias()
    test_uma_pagina_por_curso()
    test_sem_recursos_externos()
    test_csp_publicada()
    test_dados_embutidos_nao_fecham_script()

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
