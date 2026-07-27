"""
Gerador do site estático multi-curso.

    python site/build.py

Lê data/cursos/<slug>/nacional.json e produz site/dist/ com:
    index.html                        panorama e vitrine de cursos
    comparar-cursos.html              comparação entre cursos (Brasil ou UF)
    metodologia.html                  fontes, fórmulas e limites de leitura
    curso/<slug>/index.html           panorama do curso
    curso/<slug>/uf/<UF>.html         detalhe por unidade federativa
    static/js/cursos.js               catálogo de navegação (window.CURSOS)
    static/js/comparacao.js           matriz curso × recorte (window.COMPARACAO)

Com centenas de cursos no catálogo, duas coisas deixam de caber na forma ingênua:

  · a lista de cursos no cabeçalho. Repetida em cada uma das ~10 mil páginas, ela
    sozinha pesaria mais que todo o resto do site. Vai para `static/js/cursos.js`,
    um arquivo só, carregado por <script> (funciona em file://, ao contrário de
    fetch) e reaproveitado do cache em toda navegação.
  · a matriz de comparação. Em JSON de objetos, os nomes dos campos se repetiriam
    uma vez por curso e por UF. Vai colunar: uma lista de campos e, por recorte,
    um vetor de valores na mesma ordem.

O build também processa um curso por vez: manter todos os `nacional.json` e os
municípios de 353 cursos em memória ao mesmo tempo custaria centenas de MB sem
necessidade.
"""
import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
SITE = REPO / "site"
DIST = SITE / "dist"

import sys
sys.path.insert(0, str(REPO / "etl"))
from referencias import CAPITAIS, NOME_UF, REGIAO_UF  # noqa: E402

import agregados  # noqa: E402
import insights  # noqa: E402
from graficos import barras, coropletico, pontos_municipais, serie_temporal  # noqa: E402

# Somáveis no agregado nacional; os demais são recalculados ou omitidos.
SOMAVEIS = [
    "vagas_total", "vagas_presencial", "vagas_ead", "vagas_capital",
    "municipios_oferta", "municipios_deserto", "municipios_total",
    "ead_polos_municipios", "ead_polos_registros", "mun_ead_only",
    "n_ies", "n_cursos_presencial", "n_cursos_ead",
    "matriculas", "matriculas_ead", "ingressos", "concluintes",
    "populacao", "vagas_avaliadas", "n_cursos_avaliados", "concluintes_avaliados",
]
# Médias ponderadas pela capacidade da UF (não média simples entre UFs).
PONDERADOS_POR_VAGAS = [
    "ICT", "E", "IAF", "pct_ead", "pct_rede_publica", "HHI", "CR2", "CR10",
]
# Médias ponderadas pelos concluintes avaliados (indicadores de qualidade).
PONDERADOS_POR_AVALIADOS = [
    "ENADE", "CC", "IDD", "CPC_cont", "pct_doc_doutores", "pct_doc_mestres",
    "pct_doc_regime", "cpc_org_didatico", "cpc_infraestrutura", "cpc_oportunidade",
]
# Médias ponderadas pelos ingressantes (perfil de acesso).
PONDERADOS_POR_INGRESSOS = [
    "pct_mulheres", "pct_ppi", "pct_financiamento", "pct_noturno", "taxa_conclusao",
]


def media_ponderada(ufs, campo, peso):
    num = den = 0.0
    for u in ufs.values():
        v, p = u.get(campo), u.get(peso)
        if v is None or not p:
            continue
        num += v * p
        den += p
    return round(num / den, 4) if den else None


def agregar_nacional(ufs):
    """Agrega as UFs num registro Brasil, respeitando a natureza de cada indicador."""
    total = {}
    for campo in SOMAVEIS:
        valores = [u.get(campo) for u in ufs.values() if u.get(campo) is not None]
        total[campo] = sum(valores) if valores else None

    for campo in PONDERADOS_POR_VAGAS:
        total[campo] = media_ponderada(ufs, campo, "vagas_total")
    for campo in PONDERADOS_POR_AVALIADOS:
        total[campo] = media_ponderada(ufs, campo, "concluintes_avaliados")
    for campo in PONDERADOS_POR_INGRESSOS:
        total[campo] = media_ponderada(ufs, campo, "ingressos")

    # Recalculados a partir dos totais — não faz sentido "somar" ou "mediar".
    if total.get("vagas_total") and total.get("populacao"):
        total["vagas_por_100k"] = round(100000 * total["vagas_total"] / total["populacao"], 1)
    if total.get("vagas_total"):
        total["pct_ead"] = round(100 * (total["vagas_ead"] or 0) / total["vagas_total"], 1)
    if total.get("matriculas"):
        total["taxa_conclusao"] = round(100 * (total["concluintes"] or 0) / total["matriculas"], 1)
    return total


def carregar_geo():
    """Malha do IBGE, versionada por etl/malha.py. Ausente → site sem mapas,
    nunca mapa incompleto: um mapa com UFs faltando se lê como ausência de dado."""
    ufs, pontos = {}, {}
    caminho = DATA / "geo" / "ufs.json"
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            ufs = json.load(f)["ufs"]
    caminho = DATA / "geo" / "municipios.json"
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            pontos = json.load(f)["pontos"]
    return ufs, pontos


def carregar_instituicoes():
    caminho = DATA / "instituicoes.json"
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)["instituicoes"]


def carregar_serie(slug):
    caminho = DATA / "cursos" / slug / "serie.json"
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def ies_do_curso(instituicoes, slug, limite=10):
    """Instituições que ofertam o curso, da maior para a menor em matrículas."""
    lista = []
    for co, ies in instituicoes.items():
        oferta = ies.get("oferta", {}).get(slug)
        if not oferta or not oferta.get("matriculas"):
            continue
        lista.append({
            "co_ies": co,
            "nome": ies["nome"],
            "sigla": ies.get("sigla"),
            "rede": ies.get("rede"),
            "organizacao": ies.get("organizacao"),
            "uf_sede": ies.get("uf_sede"),
            "pct_doutores": ies.get("pct_doutores"),
            "matriculas": oferta["matriculas"],
            "vagas": oferta.get("vagas"),
            "concluintes": oferta.get("concluintes"),
            "cursos": oferta.get("cursos"),
        })
    lista.sort(key=lambda x: -x["matriculas"])
    return lista[:limite] if limite else lista


def carregar_curso(c):
    """Carrega dados + municípios de um curso. None se o ETL ainda não o produziu."""
    caminho = DATA / "cursos" / c["slug"] / "nacional.json"
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    municipios = {}
    dir_mun = DATA / "cursos" / c["slug"] / "municipios"
    if dir_mun.exists():
        for arq in dir_mun.glob("*.json"):
            with open(arq, encoding="utf-8") as f:
                municipios[arq.stem] = json.load(f)
    return {**c, "dados": dados, "municipios": municipios,
            "total": agregar_nacional(dados["ufs"])}


def campos_comparaveis(registro):
    """Campos escalares de um registro de UF — o que a comparação sabe confrontar."""
    return [k for k, v in registro.items()
            if not k.startswith("_") and not isinstance(v, (dict, list))]


def json_seguro(dados):
    """JSON para embutir em <script>, neutralizando o que fecharia a tag.

    `</script>` dentro de uma string de dado encerraria o bloco e o resto do JSON
    viraria HTML. Os separadores de linha U+2028/U+2029 são válidos em JSON e
    quebram o parser de JavaScript, então também saem escapados.
    """
    bruto = json.dumps(dados, ensure_ascii=False)
    fugas = {
        "<": "\\u003c",
        ">": "\\u003e",
        "&": "\\u0026",
        "\u2028": "\\u2028",
        "\u2029": "\\u2029",
    }
    for ch, fuga in fugas.items():
        bruto = bruto.replace(ch, fuga)
    return Markup(bruto)


def _fmt(valor, casas):
    if valor is None:
        return None
    return f"{valor:.{casas}f}".replace(".", ",")


def main():
    parser = argparse.ArgumentParser(description="Gera o site estático")
    parser.add_argument(
        "--base-url",
        help="URL pública do site (ex.: https://usuario.github.io/repo). Sem ela, "
             "sitemap.xml e robots.txt não são gerados — um sitemap com URL "
             "inventada é pior que sitemap nenhum.")
    args = parser.parse_args()
    base_url = (args.base_url or "").rstrip("/")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    # ATENÇÃO: select_autoescape casa pelo SUFIXO do arquivo. Como todo template
    # aqui termina em ".j2", uma lista sem "j2" desliga o escape em 100% das
    # páginas — parece protegido e não está. "j2" precisa estar na lista.
    env = Environment(
        loader=FileSystemLoader(str(SITE / "templates")),
        autoescape=select_autoescape(enabled_extensions=("html", "xml", "j2"),
                                     default_for_string=True, default=True))
    env.globals.update(
        fmt1=lambda v: _fmt(v, 1), fmt2=lambda v: _fmt(v, 2),
        fmt3=lambda v: _fmt(v, 3), fmt4=lambda v: _fmt(v, 4),
        milhar=lambda v: None if v is None else f"{v:,}".replace(",", "."),
        pct=lambda v: None if v is None else f"{v * 100:.1f}".replace(".", ",") + "%",
    )

    with open(DATA / "cursos.json", encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    acumulado = agregados.Acumulador()
    malha_ufs, centroides = carregar_geo()
    instituicoes = carregar_instituicoes()
    if not malha_ufs:
        print("[AVISO] data/geo/ufs.json ausente — páginas sairão sem mapa. "
              "Rode python etl/malha.py.")
    if not instituicoes:
        print("[AVISO] data/instituicoes.json ausente — sem camada institucional. "
              "Rode python etl/instituicoes.py.")

    data_extracao = str(date.today())
    versao_censo = None
    # Acumuladores enxutos: só o que as páginas-índice precisam, nunca os dados
    # completos de todos os cursos ao mesmo tempo.
    resumo, cursos_meta, comparacao, campos = [], [], {}, None
    ufs_disponiveis, agregado = set(), {"vagas_total": 0, "matriculas": 0, "n_cursos": 0}
    pulados = []

    tpl_curso = env.get_template("curso.html.j2")
    tpl_uf = env.get_template("uf.html.j2")

    # ── Páginas por curso ────────────────────────────────────────────────────
    for i, entrada in enumerate(catalogo, 1):
        c = carregar_curso(entrada)
        if c is None:
            pulados.append(entrada["slug"])
            continue

        meta = c["dados"]["metadados"]
        ufs = c["dados"]["ufs"]
        tem_qualidade = any(u.get("ENADE") is not None for u in ufs.values())
        if versao_censo is None:
            versao_censo = meta["versao_censo"]
        ctx_base = {"versao_censo": versao_censo, "data_extracao": data_extracao}

        destino = DIST / "curso" / c["slug"]
        (destino / "uf").mkdir(parents=True, exist_ok=True)

        serie = carregar_serie(c["slug"])
        top_todas_ies = ies_do_curso(instituicoes, c["slug"], limite=None)
        top_ies = top_todas_ies[:10]

        mapa = ""
        if malha_ufs:
            mapa = Markup(coropletico(
                malha_ufs,
                {uf: d.get("vagas_total") for uf, d in ufs.items()},
                titulo=f"Vagas de {c['nome']} por unidade federativa",
                descricao=(f"Mapa do Brasil com as 27 unidades federativas coloridas "
                           f"pelo total de vagas de {c['nome']}. Os valores exatos "
                           f"estão na tabela abaixo."),
                unidade=" vagas", nomes_uf=NOME_UF))

        grafico_serie = ""
        if serie and len(serie.get("anos", {})) >= 2:
            anos = sorted(serie["anos"])
            grafico_serie = Markup(serie_temporal(
                anos,
                [{"nome": "Vagas totais",
                  "valores": [serie["anos"][a]["BR"].get("vagas_total") for a in anos]},
                 {"nome": "Matrículas presenciais",
                  "valores": [serie["anos"][a]["BR"].get("matriculas") for a in anos]}],
                titulo=f"Evolução de {c['nome']} no Brasil",
                descricao=("Linhas de vagas totais e matrículas presenciais ao longo "
                           "das edições do Censo disponíveis.")))

        grafico_ies = ""
        if top_ies:
            grafico_ies = Markup(barras(
                [{"nome": i["sigla"] or i["nome"], "valor": i["matriculas"]}
                 for i in top_ies],
                titulo=f"Instituições com mais matrículas em {c['nome']}",
                descricao="Barras horizontais das dez maiores em matrículas.",
                unidade=" matrículas"))

        leituras = insights.do_curso(c["nome"], c["total"], ufs, serie, top_ies)

        html = tpl_curso.render(
            **ctx_base, depth="../../", curso_atual=c["slug"],
            meta=meta, total=c["total"], tem_qualidade=tem_qualidade, n_ufs=len(ufs),
            mapa=mapa, grafico_serie=grafico_serie, grafico_ies=grafico_ies,
            top_ies=top_ies, leituras=leituras,
            anos_serie=sorted(serie["anos"]) if serie else [],
            dados_json=json_seguro(ufs),
            meta_json=json_seguro(meta))
        (destino / "index.html").write_text(html, encoding="utf-8")

        siglas = sorted(ufs)
        for sigla, d in ufs.items():
            municipios_uf = c["municipios"].get(sigla, [])
            # Acumula para os painéis territoriais, que somam através dos cursos.
            acumulado.somar_uf(sigla, c, d, municipios_uf,
                               {i["co_ies"] for i in top_todas_ies
                                if sigla in (instituicoes[i["co_ies"]].get("ufs") or [])})
            for m in municipios_uf:
                acumulado.somar_municipio(sigla, c, m)
            mapa_uf = ""
            if centroides and municipios_uf:
                mapa_uf = Markup(pontos_municipais(
                    centroides,
                    [{"nome": m["nome"], "cod_ibge": m.get("cod_ibge"),
                      "valor": m.get("vagas_total")} for m in municipios_uf],
                    titulo=f"Municípios de {NOME_UF[sigla]} com oferta de {c['nome']}",
                    descricao=("Cada círculo é um município com oferta presencial; a "
                               "área é proporcional ao número de vagas."),
                    contorno_ufs={sigla: malha_ufs[sigla]} if sigla in malha_ufs else None))

            serie_uf = None
            if serie:
                serie_uf = {a: v["ufs"][sigla] for a, v in serie["anos"].items()
                            if sigla in v.get("ufs", {})}

            html_uf = tpl_uf.render(
                **ctx_base, depth="../../../", curso_atual=c["slug"],
                meta=meta, sigla=sigla, nome_uf=NOME_UF[sigla], d=d,
                ufs_curso=siglas, mapa_uf=mapa_uf,
                leituras=insights.da_uf(NOME_UF[sigla], d, serie_uf),
                municipios=municipios_uf,
                dados_uf_json=json_seguro(d))
            (destino / "uf" / f"{sigla}.html").write_text(html_uf, encoding="utf-8")

        # Matriz de comparação, colunar. Os campos vêm do primeiro curso lido e
        # valem para todos: o consolidador grava o mesmo conjunto em toda UF.
        if campos is None:
            campos = campos_comparaveis(c["total"])
        recortes = {"BR": c["total"], **ufs}
        comparacao[c["slug"]] = {r: [d.get(k) for k in campos]
                                 for r, d in recortes.items()}
        ufs_disponiveis.update(ufs)

        resumo.append({
            "slug": c["slug"], "nome": c["nome"], "area_cine": c["area_cine"],
            "area_especifica": c.get("area_especifica"), "graus": c.get("graus") or [],
            "vagas_total": c["total"]["vagas_total"],
            "pct_ead": c["total"]["pct_ead"],
            "municipios_oferta": c["total"]["municipios_oferta"],
            "n_ufs": len(ufs),
            "tem_qualidade": tem_qualidade,
        })
        cursos_meta.append({"nome": c["nome"], "ciclo_enade": meta.get("ciclo_enade"),
                            "tem_qualidade": tem_qualidade})
        agregado["vagas_total"] += c["total"]["vagas_total"] or 0
        agregado["matriculas"] += c["total"]["matriculas"] or 0
        agregado["n_cursos"] += 1

        if i % 25 == 0 or i == len(catalogo):
            print(f"[CURSO] {i}/{len(catalogo)} — última: {c['slug']} ({len(ufs)} UFs)")

    if not resumo:
        raise SystemExit("[ERRO] Nenhum curso com dados. Rode o pipeline do ETL antes.")
    if pulados:
        print(f"[PULADOS] {len(pulados)} cursos sem nacional.json: "
              f"{', '.join(pulados[:8])}{' …' if len(pulados) > 8 else ''}")

    ctx_base = {"versao_censo": versao_censo, "data_extracao": data_extracao}
    resumo.sort(key=lambda r: -(r["vagas_total"] or 0))
    ufs_disponiveis = sorted(ufs_disponiveis)

    # ── Estáticos ────────────────────────────────────────────────────────────
    shutil.copytree(SITE / "static", DIST / "static")

    # Catálogo de navegação: um arquivo para todo o site, em vez de repetir a
    # lista de cursos no cabeçalho de cada página.
    nav = [{"s": r["slug"], "n": r["nome"], "a": r["area_cine"], "v": r["vagas_total"]}
           for r in resumo]
    (DIST / "static" / "js" / "cursos.js").write_text(
        "window.CURSOS=" + json.dumps(nav, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8")
    print(f"[OK] static/js/cursos.js — {len(nav)} cursos")

    # ── Comparação entre cursos ──────────────────────────────────────────────
    (DIST / "static" / "js" / "comparacao.js").write_text(
        "window.COMPARACAO=" + json.dumps(
            {"campos": campos, "dados": comparacao},
            ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8")
    html = env.get_template("comparar-cursos.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        ufs_json=json_seguro(ufs_disponiveis))
    (DIST / "comparar-cursos.html").write_text(html, encoding="utf-8")
    tam = (DIST / "static" / "js" / "comparacao.js").stat().st_size / 1024 / 1024
    print(f"[OK] comparar-cursos.html — {len(comparacao)} cursos × "
          f"{len(ufs_disponiveis) + 1} recortes × {len(campos)} campos "
          f"({tam:.1f} MB em static/js/comparacao.js)")

    # ── Home ─────────────────────────────────────────────────────────────────
    por_area = {}
    for r in resumo:
        por_area.setdefault(r["area_cine"] or "Sem área declarada", []).append(r)
    areas = sorted(por_area.items(),
                   key=lambda kv: -sum(x["vagas_total"] or 0 for x in kv[1]))

    html = env.get_template("index.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        resumo_cursos=resumo, areas=areas, agregado=agregado)
    (DIST / "index.html").write_text(html, encoding="utf-8")
    print("[OK] index.html")

    # ── Metodologia ──────────────────────────────────────────────────────────
    html = env.get_template("metodologia.html.j2").render(
        **ctx_base, depth="", curso_atual=None, cursos_meta=cursos_meta)
    (DIST / "metodologia.html").write_text(html, encoding="utf-8")
    print("[OK] metodologia.html")

    # ── Privacidade (LGPD) ───────────────────────────────────────────────────
    html = env.get_template("privacidade.html.j2").render(
        **ctx_base, depth="", curso_atual=None)
    (DIST / "privacidade.html").write_text(html, encoding="utf-8")
    print("[OK] privacidade.html")

    # ── 404 ──────────────────────────────────────────────────────────────────
    # O 404 é servido para QUALQUER caminho inexistente, inclusive profundos como
    # /curso/xxx/uf/ZZ.html. Links relativos quebrariam ali, então esta página usa
    # caminhos a partir da raiz pública — que só se conhece com --base-url.
    raiz_publica = "/"
    if base_url:
        from urllib.parse import urlparse
        caminho = urlparse(base_url).path.rstrip("/")
        raiz_publica = (caminho + "/") if caminho else "/"
    html = env.get_template("404.html.j2").render(
        **ctx_base, depth=raiz_publica, curso_atual=None, n_cursos=len(resumo))
    (DIST / "404.html").write_text(html, encoding="utf-8")
    print(f"[OK] 404.html (raiz pública {raiz_publica})")

    # ── Painéis territoriais e institucionais ────────────────────────────────
    acumulado.fechar()
    for sigla, u in acumulado.ufs.items():
        u["regiao"] = REGIAO_UF.get(sigla)
        u["capital"] = CAPITAIS.get(sigla)

    (DIST / "uf").mkdir(parents=True, exist_ok=True)
    tpl_uf_perfil = env.get_template("uf-perfil.html.j2")
    for sigla, u in sorted(acumulado.ufs.items()):
        muns = sorted((m for (s, _), m in acumulado.municipios.items() if s == sigla),
                      key=lambda m: -m["vagas_total"])
        mapa = ""
        if centroides and muns and sigla in malha_ufs:
            mapa = Markup(pontos_municipais(
                centroides,
                [{"nome": m["nome"], "cod_ibge": m.get("cod_ibge"),
                  "valor": m["vagas_total"]} for m in muns],
                titulo=f"Municípios de {NOME_UF[sigla]} com oferta presencial",
                descricao="Círculos proporcionais às vagas presenciais somadas.",
                contorno_ufs={sigla: malha_ufs[sigla]}))
        html = tpl_uf_perfil.render(
            **ctx_base, depth="../", curso_atual=None, sigla=sigla,
            nome_uf=NOME_UF[sigla], u=u, municipios=muns, mapa=mapa,
            n_cursos_uf=len(u["cursos"]),
            grafico_areas=Markup(barras(
                [{"nome": a, "valor": v} for a, v in u["areas"].items()],
                titulo=f"Vagas por área do conhecimento em {NOME_UF[sigla]}",
                descricao="Áreas gerais da classificação CINE.", unidade=" vagas")),
            leituras=insights.da_uf(NOME_UF[sigla], u))
        (DIST / "uf" / f"{sigla}.html").write_text(html, encoding="utf-8")
    print(f"[OK] uf/ — {len(acumulado.ufs)} painéis estaduais")

    lista_ufs = [{**u, "sigla": s, "nome": NOME_UF[s]}
                 for s, u in acumulado.ufs.items()]
    lista_ufs.sort(key=lambda u: -u["vagas_total"])
    mapa_br = ""
    if malha_ufs:
        mapa_br = Markup(coropletico(
            malha_ufs, {s: u["vagas_total"] for s, u in acumulado.ufs.items()},
            titulo="Vagas por unidade federativa, somando todos os cursos",
            descricao="Mapa do Brasil colorido pelo total de vagas de cada UF.",
            unidade=" vagas", nomes_uf=NOME_UF))
    html = env.get_template("estados.html.j2").render(
        **ctx_base, depth="", curso_atual=None, ufs=lista_ufs, mapa=mapa_br,
        n_cursos=len(resumo))
    (DIST / "estados.html").write_text(html, encoding="utf-8")
    print("[OK] estados.html")

    (DIST / "municipio").mkdir(parents=True, exist_ok=True)
    tpl_mun = env.get_template("municipio.html.j2")
    for (sigla, slug), m in acumulado.municipios.items():
        html = tpl_mun.render(
            **ctx_base, depth="../", curso_atual=None, m=m,
            nome_uf=NOME_UF[sigla],
            grafico=Markup(barras(
                [{"nome": c["nome"], "valor": c["vagas"]} for c in m["cursos"]],
                titulo=f"Cursos com mais vagas em {m['nome']}",
                descricao="Barras horizontais por vagas presenciais.",
                unidade=" vagas")),
            leituras=insights.do_municipio(m["nome"], sigla, m))
        (DIST / "municipio" / f"{sigla}-{slug}.html").write_text(html, encoding="utf-8")
    print(f"[OK] municipio/ — {len(acumulado.municipios)} municípios")

    (DIST / "instituicao").mkdir(parents=True, exist_ok=True)
    tpl_ies = env.get_template("instituicao.html.j2")
    nome_do_slug = {c["slug"]: c["nome"] for c in catalogo}
    for co, ies in instituicoes.items():
        oferta = sorted(
            ({"slug": s, "nome": nome_do_slug.get(s, s), **v}
             for s, v in ies.get("oferta", {}).items()),
            key=lambda x: -(x.get("matriculas") or 0))
        html = tpl_ies.render(
            **ctx_base, depth="../", curso_atual=None, ies=ies, oferta=oferta,
            grafico=Markup(barras(
                [{"nome": o["nome"], "valor": o["matriculas"]} for o in oferta],
                titulo=f"Cursos de {ies['nome']} por matrículas",
                descricao="Barras horizontais por matrículas.",
                unidade=" matrículas")),
            leituras=insights.da_instituicao(ies))
        (DIST / "instituicao" / f"{co}.html").write_text(html, encoding="utf-8")
    print(f"[OK] instituicao/ — {len(instituicoes)} painéis institucionais")

    lista_ies = sorted(instituicoes.values(), key=lambda i: -(i["matriculas"] or 0))
    html = env.get_template("instituicoes.html.j2").render(
        **ctx_base, depth="", curso_atual=None, instituicoes=lista_ies,
        total=len(lista_ies),
        organizacoes=sorted({i["organizacao"] for i in lista_ies if i.get("organizacao")}),
        ufs=sorted({i["uf_sede"] for i in lista_ies if i.get("uf_sede")}))
    (DIST / "instituicoes.html").write_text(html, encoding="utf-8")
    print("[OK] instituicoes.html")

    # ── Rankings ─────────────────────────────────────────────────────────────
    por_slug = {r["slug"]: r for r in resumo}
    listas = agregados.rankings(instituicoes, acumulado.ufs, acumulado.municipios,
                                por_slug)
    for r in listas:
        r["rotulo_item"] = {"ies": "Instituição", "uf": "Estado",
                            "municipio": "Município", "curso": "Curso"}[r["tipo"]]
        itens = []
        for i in r["itens"]:
            if r["tipo"] == "ies":
                item = {"rotulo": i["nome"], "url": f"instituicao/{i['co_ies']}.html",
                        "rede": i.get("rede"), "uf_sede": i.get("uf_sede")}
            elif r["tipo"] == "uf":
                item = {"rotulo": NOME_UF[i["sigla"]], "url": f"uf/{i['sigla']}.html"}
            elif r["tipo"] == "municipio":
                item = {"rotulo": i["nome"], "uf": i["uf"],
                        "url": f"municipio/{i['uf']}-{i['slug']}.html"}
            else:
                item = {"rotulo": i["nome"], "url": f"curso/{i['slug']}/index.html",
                        "area_cine": i.get("area_cine")}
            item["valor"] = i.get(r["campo"])
            itens.append(item)
        r["itens"] = itens
    html = env.get_template("rankings.html.j2").render(
        **ctx_base, depth="", curso_atual=None, listas=listas, n_cursos=len(resumo))
    (DIST / "rankings.html").write_text(html, encoding="utf-8")
    print(f"[OK] rankings.html — {len(listas)} listas")

    # ── API de dados abertos ─────────────────────────────────────────────────
    api = DIST / "api" / "v1"
    (api / "curso").mkdir(parents=True, exist_ok=True)
    endpoints = []

    def publicar(caminho, dados, descricao):
        destino = api / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        kb = destino.stat().st_size / 1024
        endpoints.append({
            "caminho": f"api/v1/{caminho}",
            "descricao": descricao,
            "tamanho": f"{kb / 1024:.1f} MB" if kb > 1024 else f"{kb:.0f} KB",
        })

    publicar("cursos.json",
             {"metadados": {"censo": versao_censo, "extracao": data_extracao,
                            "total": len(resumo)}, "cursos": resumo},
             "Catálogo com os totais nacionais de cada curso")
    publicar("estados.json",
             {"metadados": {"censo": versao_censo, "extracao": data_extracao},
              "ufs": {s: {k: v for k, v in u.items() if k != "cursos"}
                      for s, u in acumulado.ufs.items()}},
             "Totais por unidade federativa, somando todos os cursos")
    publicar("municipios.json",
             {"metadados": {"censo": versao_censo, "extracao": data_extracao},
              "municipios": [{k: v for k, v in m.items() if k != "cursos"}
                             for m in acumulado.municipios.values()]},
             "Totais por município com oferta presencial")
    publicar("instituicoes.json",
             {"metadados": {"censo": versao_censo, "extracao": data_extracao,
                            "aviso": ("corpo docente é da instituição inteira, "
                                      "nunca rateado por curso")},
              "instituicoes": [{k: v for k, v in i.items() if k != "oferta"}
                               for i in instituicoes.values()]},
             "Instituições com organização, categoria e corpo docente")
    endpoints.append({
        "caminho": "api/v1/curso/&lt;slug&gt;.json",
        "descricao": "Indicadores completos de um curso, por UF",
        "tamanho": "varia",
    })
    endpoints.append({
        "caminho": "api/v1/curso/&lt;slug&gt;/serie.json",
        "descricao": "Série histórica do curso, por edição do Censo",
        "tamanho": "varia",
    })
    for entrada in catalogo:
        origem = DATA / "cursos" / entrada["slug"] / "nacional.json"
        if origem.exists():
            shutil.copyfile(origem, api / "curso" / f"{entrada['slug']}.json")
        origem = DATA / "cursos" / entrada["slug"] / "serie.json"
        if origem.exists():
            destino = api / "curso" / entrada["slug"] / "serie.json"
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origem, destino)
    print(f"[OK] api/v1/ — {len(endpoints)} endpoints documentados")

    html = env.get_template("api.html.j2").render(
        **ctx_base, depth="", curso_atual=None, endpoints=endpoints,
        base_exemplo=base_url or "https://exemplo.org")
    (DIST / "api.html").write_text(html, encoding="utf-8")
    print("[OK] api.html")

    # ── Sitemap e robots ─────────────────────────────────────────────────────
    if base_url:
        urls = sorted(
            base_url + "/" + p.relative_to(DIST).as_posix()
            for p in DIST.rglob("*.html") if p.name != "404.html")
        linhas = ['<?xml version="1.0" encoding="UTF-8"?>',
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for u in urls:
            linhas.append("  <url><loc>" + quote(u, safe=":/") + "</loc>"
                          "<lastmod>" + data_extracao + "</lastmod></url>")
        linhas.append("</urlset>")
        (DIST / "sitemap.xml").write_text("\n".join(linhas) + "\n", encoding="utf-8")
        (DIST / "robots.txt").write_text(
            "User-agent: *\nAllow: /\nSitemap: " + base_url + "/sitemap.xml\n",
            encoding="utf-8")
        print("[OK] sitemap.xml — " + str(len(urls)) + " URLs · robots.txt")
    else:
        print("[INFO] Sem --base-url: sitemap.xml e robots.txt não gerados.")

    paginas = list(DIST.rglob("*.html"))
    peso = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file()) / 1024 / 1024
    print(f"\n[BUILD] {len(paginas)} páginas · {peso:.1f} MB em {DIST}")


if __name__ == "__main__":
    main()
