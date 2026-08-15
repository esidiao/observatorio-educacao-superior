"""
Gerador do site estático multi-curso.

    python site/build.py

Lê data/cursos/<slug>/nacional.json e produz site/dist/ com:
    index.html                        panorama e vitrine de cursos
    comparar-cursos.html              comparação entre cursos (Brasil ou UF)
    metodologia.html                  fontes, fórmulas e limites de leitura
    curso/<slug>/index.html           panorama do curso
    curso/<slug>/uf/<UF>.html         detalhe por unidade federativa
    static/js/indice.js               índice de busca do site (window.INDICE)
    static/js/comparacao.js           matriz curso × recorte (window.COMPARACAO)

Com centenas de cursos no catálogo, duas coisas deixam de caber na forma ingênua:

  · o índice de busca do cabeçalho — 353 cursos, 2.561 instituições, 1.119
    municípios e 27 estados. Repetido em cada uma das ~10 mil páginas, ele
    sozinho pesaria mais que todo o resto do site. Vai para
    `static/js/indice.js`, um arquivo só, carregado por <script> (funciona em
    file://, ao contrário de fetch) e reaproveitado do cache em toda navegação.
    Cada destino é uma lista, não um objeto: repetir as chaves quatro mil vezes
    dobraria o arquivo sem acrescentar informação.
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

from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape
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
import marca  # noqa: E402
from graficos import (CAMPOS_CURSO, barras, base_municipal,  # noqa: E402
                      coropletico,
                      coropletico_municipal,
                      pontos_municipais, serie_temporal)

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
    "pct_mulheres", "pct_ppi", "pct_cor_nao_declarada", "pct_financiamento",
    "pct_noturno", "taxa_conclusao",
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


def carregar_limites_municipais(sigla):
    """Limites dos municipios de UMA unidade federativa.

    Carregado por estado, e nao de uma vez: os 27 arquivos somam 2,5 MB, e
    manter tudo na memoria para desenhar um estado de cada vez seria carregar
    26 estados a toa. Ausente, o painel cai para o mapa de pontos.
    """
    caminho = DATA / "geo" / "municipios_uf" / f"{sigla}.json"
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)["municipios"]


def carregar_instituicoes():
    """Camada do Censo, enriquecida com o IGC quando este já foi ingerido.

    Os dois vêm de fontes e calendários distintos e por isso moram em arquivos
    separados — ver etl/igc.py. A fusão acontece aqui, na leitura, para que
    reingerir o Censo nunca apague dado de avaliação.
    """
    caminho = DATA / "instituicoes.json"
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        instituicoes = json.load(f)["instituicoes"]

    # Campos de avaliação existem em TODA instituição, com None quando ausentes.
    # Sem isso, quem não tem IGC chega ao template como Undefined, e `is not none`
    # é verdadeiro para Undefined — o painel entraria no ramo "tem avaliação" para
    # justamente quem não tem.
    CAMPOS_IGC = ("igc_continuo", "igc_faixa", "cursos_com_cpc",
                  "conceito_graduacao", "conceito_mestrado", "conceito_doutorado",
                  "igc_ano")

    # Pós-graduação: ausência aqui é FATO (não tem programa), não dado faltante.
    CAMPOS_CAPES = ("pos_programas", "pos_conceito_medio", "pos_conceito_maximo",
                    "pos_por_grau", "pos_areas", "pos_ano")
    for ies in instituicoes.values():
        ies.update({c: None for c in CAMPOS_CAPES})
    caminho_capes = DATA / "capes.json"
    if caminho_capes.exists():
        with open(caminho_capes, encoding="utf-8") as f:
            bruto = json.load(f)
        capes, ano_capes = bruto["instituicoes"], bruto.get("ano_base")
        com_pos = 0
        for co, ies in instituicoes.items():
            d = capes.get(co)
            if not d:
                continue
            ies.update({
                "pos_programas": d["programas"],
                "pos_conceito_medio": d["conceito_medio"],
                "pos_conceito_maximo": d["conceito_maximo"],
                "pos_por_grau": d["por_grau"],
                "pos_areas": d["areas"],
                "pos_ano": ano_capes,
            })
            com_pos += 1
        print(f"[INFO] Pós-graduação stricto sensu em {com_pos} instituições "
              f"(as demais não têm programa — fato, não lacuna).")

    caminho_igc = DATA / "igc.json"
    if not caminho_igc.exists():
        for ies in instituicoes.values():
            ies.update({c: None for c in CAMPOS_IGC})
        return instituicoes
    with open(caminho_igc, encoding="utf-8") as f:
        igc = json.load(f)["instituicoes"]
    casadas = 0
    for co, ies in instituicoes.items():
        ies.update({c: None for c in CAMPOS_IGC})
        dados = igc.get(co)
        if dados:
            ies.update({k: v for k, v in dados.items() if k != "ano"})
            ies["igc_ano"] = dados.get("ano")
            casadas += 1
    print(f"[INFO] IGC casado em {casadas} de {len(instituicoes)} instituições "
          f"({100 * casadas / len(instituicoes):.0f}%) — o resto não teve curso "
          f"avaliado no triênio.")
    return instituicoes


def carregar_fluxo():
    """Taxas de coorte do INEP, por UF. Ausente → painéis sem a seção."""
    caminho = DATA / "fluxo.json"
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def carregar_serie(slug):
    caminho = DATA / "cursos" / slug / "serie.json"
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def carregar_perfil_municipal():
    """População do IBGE e contagem exata de instituições, por código IBGE.

    Duas camadas opcionais que respondem o que o pipeline principal não
    consegue. A população não está no Censo — é outra fonte, de outro ano, e o
    ano viaja junto com o número até a página. A contagem de instituições exige
    ler o microdado, porque agregar por curso e somar contaria a mesma
    universidade uma vez por curso que ela oferta.
    """
    perfil = {}
    caminho = DATA / "populacao_municipios.json"
    ano_pop = None
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            bruto = json.load(f)
        ano_pop = bruto.get("ano")
        for codigo, habitantes in bruto["municipios"].items():
            perfil.setdefault(codigo, {})["populacao"] = habitantes

    caminho = DATA / "municipios_ies.json"
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            bruto = json.load(f)
        for codigo, d in bruto["municipios"].items():
            alvo = perfil.setdefault(codigo, {})
            alvo["n_ies"] = d["n_ies"]
            alvo["n_cursos_distintos"] = d["n_cursos_distintos"]
            alvo["n_ofertas"] = d["n_ofertas"]
    return perfil, ano_pop


def carregar_serie_agregada(nome):
    """Série de UF ou de instituição, produzida por etl/serie_agregada.py.

    Camada opcional, como as demais: sem o arquivo, a página sai sem o gráfico
    de evolução em vez de o build parar. Quem nunca rodou o ETL de série tem um
    site completo, só sem história.
    """
    caminho = DATA / "series" / f"{nome}.json"
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        return json.load(f).get("series", {})


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


def _numero(valor):
    """None para qualquer coisa que não seja número.

    Inclui o Undefined do Jinja: campo ausente num dicionário não é None, é
    Undefined, e formatá-lo levanta TypeError no meio do build. Tratar aqui, uma
    vez, evita ter que lembrar disso em cada template.
    """
    if valor is None or isinstance(valor, bool) or isinstance(valor, Undefined):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _fmt(valor, casas):
    numero = _numero(valor)
    if numero is None:
        return None
    return f"{numero:.{casas}f}".replace(".", ",")


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
        milhar=lambda v: (None if _numero(v) is None
                          else f"{round(_numero(v)):,}".replace(",", ".")),
        pct=lambda v: (None if _numero(v) is None
                       else f"{_numero(v) * 100:.1f}".replace(".", ",") + "%"),
    )

    with open(DATA / "cursos.json", encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    acumulado = agregados.Acumulador()
    fluxo = carregar_fluxo()
    malha_ufs, centroides = carregar_geo()
    instituicoes = carregar_instituicoes()
    perfil_municipal, ano_populacao = carregar_perfil_municipal()
    if perfil_municipal:
        com_pop = sum(1 for v in perfil_municipal.values() if "populacao" in v)
        com_ies = sum(1 for v in perfil_municipal.values() if "n_ies" in v)
        print(f"[INFO] Perfil municipal: {com_pop} com populacao "
              f"({ano_populacao}), {com_ies} com contagem exata de IES")
    else:
        print("[AVISO] data/populacao_municipios.json e municipios_ies.json "
              "ausentes — o mapa municipal sai sem populacao e sem contagem "
              "de instituicoes. Rode etl/populacao_municipal.py e "
              "etl/municipios_ies.py.")
    series_uf = carregar_serie_agregada("ufs")
    series_ies = carregar_serie_agregada("ies")
    if series_uf:
        anos_disp = sorted({a for v in series_uf.values() for a in v})
        print(f"[INFO] Série territorial: {len(series_uf)} recortes, "
              f"{anos_disp[0]}–{anos_disp[-1]}")
    else:
        print("[AVISO] data/series/ufs.json ausente — os painéis estaduais "
              "usarão a série somada dos cursos, sem contagem de IES. "
              "Rode python etl/baixar_censo.py --anos ...")
    if series_ies:
        print(f"[INFO] Série institucional: {len(series_ies)} instituições")
    if not malha_ufs:
        print("[AVISO] data/geo/ufs.json ausente — páginas sairão sem mapa. "
              "Rode python etl/malha.py.")
    if not instituicoes:
        print("[AVISO] data/instituicoes.json ausente — sem camada institucional. "
              "Rode python etl/instituicoes.py.")

    data_extracao = str(date.today())
    ano_corrente = date.today().year
    versao_censo = None
    # Acumuladores enxutos: só o que as páginas-índice precisam, nunca os dados
    # completos de todos os cursos ao mesmo tempo.
    resumo, cursos_meta, comparacao, campos = [], [], {}, None
    # Série nacional: soma dos cursos, ano a ano. Feita na passagem pelo laço,
    # que já lê cada serie.json — evita uma segunda varredura de 353 arquivos.
    serie_brasil = {}
    # Mesma soma, quebrada por UF: alimenta a série dos painéis estaduais.
    serie_por_uf = {}
    ufs_disponiveis, agregado = set(), {"vagas_total": 0, "matriculas": 0, "n_cursos": 0}
    pulados = []

    # ── Base dos mapas municipais, uma por UF ────────────────────────────────
    # A mesma imagem serve a todas as paginas de um estado: a de cada curso e a
    # do painel territorial. Servida a parte, o navegador a busca uma vez;
    # embutida em cada pagina, custaria os 218 KB de Minas multiplicados por
    # 353 cursos.
    base_geo = SITE / "static" / "geo"
    base_geo.mkdir(parents=True, exist_ok=True)
    bases_municipais = {}
    for sigla in sorted(malha_ufs):
        limites_base = carregar_limites_municipais(sigla)
        if not limites_base:
            continue
        (base_geo / f"{sigla}.svg").write_text(
            base_municipal(limites_base, contorno_uf=malha_ufs.get(sigla)),
            encoding="utf-8")
        bases_municipais[sigla] = f"static/geo/{sigla}.svg"
    if bases_municipais:
        kb = sum((base_geo / f"{s}.svg").stat().st_size for s in bases_municipais) / 1024
        print(f"[OK] static/geo/ — {len(bases_municipais)} bases municipais, "
              f"{kb / 1024:.1f} MB no total")

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
        ctx_base = {"versao_censo": versao_censo, "data_extracao": data_extracao,
                    "ano_corrente": ano_corrente}

        destino = DIST / "curso" / c["slug"]
        (destino / "uf").mkdir(parents=True, exist_ok=True)

        serie = carregar_serie(c["slug"])
        if serie:
            for ano, dados in serie.get("anos", {}).items():
                alvo = serie_brasil.setdefault(
                    ano, {"vagas_total": 0, "vagas_presencial": 0,
                          "vagas_ead": 0, "matriculas": 0, "vagas_publicas": 0})
                for campo in alvo:
                    alvo[campo] += dados["BR"].get(campo) or 0
                for sigla, d in (dados.get("ufs") or {}).items():
                    alvo_uf = serie_por_uf.setdefault(sigla, {}).setdefault(
                        ano, {"vagas_total": 0, "vagas_presencial": 0,
                              "vagas_ead": 0, "matriculas": 0, "vagas_publicas": 0})
                    for campo in alvo_uf:
                        alvo_uf[campo] += d.get(campo) or 0
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
            # Mapa do curso no estado, com o limite de cada município. A troca
            # de círculos por áreas muda o que se lê: o mapa de pontos só
            # desenhava município COM oferta, e um curso presente em quatorze
            # cidades parecia um estado de quatorze cidades. Com os limites, os
            # 246 municípios de Goiás aparecem, e os 232 sem este curso
            # aparecem *como não tendo* — que é a pergunta de quem procura onde
            # estudar.
            mapa_uf = ""
            por_codigo_curso = {}
            for m in municipios_uf:
                cod = str(m.get("cod_ibge") or "")
                if not cod:
                    continue
                pop = (perfil_municipal.get(cod) or {}).get("populacao")
                por_codigo_curso[cod] = {
                    "cod_ibge": cod, "nome": m["nome"], "populacao": pop,
                    "matriculas": m.get("matriculas"),
                    "vagas": m.get("vagas_total"),
                    # n_ies aqui é exato sem esforço: o Censo informa quantas
                    # instituições ofertam ESTE curso naquele município, e não
                    # há o problema de dupla contagem do painel territorial.
                    "n_ies": m.get("n_ies"),
                    "taxa": (round(100000 * (m.get("matriculas") or 0) / pop, 1)
                             if pop else None),
                }
            limites_uf = carregar_limites_municipais(sigla)
            if limites_uf and por_codigo_curso:
                mapa_uf = Markup(coropletico_municipal(
                    limites_uf, por_codigo_curso,
                    titulo=(f"Matrículas em {c['nome']} por 100 mil habitantes "
                            f"em {NOME_UF[sigla]}"),
                    descricao=(f"Cada município do estado, colorido pela taxa de "
                               f"matrículas em {c['nome']} por 100 mil habitantes. "
                               f"Municípios sem o curso aparecem em cinza."),
                    contorno_uf=malha_ufs.get(sigla),
                    campos=CAMPOS_CURSO,
                    base_href="../../../" + bases_municipais[sigla]
                    if sigla in bases_municipais else None))
            elif centroides and municipios_uf:
                # Reserva: sem a malha municipal, o mapa de pontos ainda diz
                # onde há oferta — só não mostra quem ficou de fora.
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
            "ingressos": c["total"].get("ingressos"),
            "pct_mulheres": c["total"].get("pct_mulheres"),
            "pct_ppi": c["total"].get("pct_ppi"),
            "pct_cor_nao_declarada": c["total"].get("pct_cor_nao_declarada"),
            "pct_financiamento": c["total"].get("pct_financiamento"),
            "pct_noturno": c["total"].get("pct_noturno"),
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

    ctx_base = {"versao_censo": versao_censo, "data_extracao": data_extracao,
                "ano_corrente": ano_corrente}
    resumo.sort(key=lambda r: -(r["vagas_total"] or 0))
    ufs_disponiveis = sorted(ufs_disponiveis)

    # ── Estáticos ────────────────────────────────────────────────────────────
    # A marca sai daqui, e não de um arquivo mantido à mão: o mapa dentro da
    # lupa é a malha de data/geo/ufs.json amostrada em pontos. Gerando no
    # build, marca e mapas do site nunca divergem — se o IBGE revisar a malha,
    # as duas mudam na mesma execução.
    img = SITE / "static" / "img"
    img.mkdir(parents=True, exist_ok=True)
    (img / "marca.svg").write_text(marca.simbolo(tamanho=96), encoding="utf-8")
    (img / "marca-completa.svg").write_text(marca.marca_completa(), encoding="utf-8")
    (img / "icone.svg").write_text(
        marca.simbolo(32, "icone", passo=3.0, ponto=2.6), encoding="utf-8")
    print(f"[OK] static/img/ — marca, assinatura e ícone gerados da malha")

    shutil.copytree(SITE / "static", DIST / "static")


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

    anos_br = sorted(serie_brasil)
    grafico_modalidade = ""
    if len(anos_br) >= 2:
        grafico_modalidade = Markup(serie_temporal(
            anos_br,
            [{"nome": "Vagas presenciais",
              "valores": [serie_brasil[a]["vagas_presencial"] for a in anos_br]},
             {"nome": "Vagas a distância",
              "valores": [serie_brasil[a]["vagas_ead"] for a in anos_br]}],
            titulo="Capacidade presencial e a distância no Brasil",
            descricao=("Duas linhas comparando a evolucao das vagas presenciais e "
                       "a distância, somando todos os cursos do catálogo.")))

    fluxo_br = fluxo.get("brasil") or {}
    grafico_evasao = ""
    if len(fluxo_br) >= 2:
        coortes_br = sorted(fluxo_br)
        series_fluxo = []
        for chave, rotulo in (("evasao", "Evasão"), ("conclusao", "Conclusao")):
            valores = [fluxo_br[c].get(chave) for c in coortes_br]
            if any(v is not None for v in valores):
                series_fluxo.append({"nome": rotulo, "valores": valores})
        if series_fluxo:
            grafico_evasao = Markup(serie_temporal(
                coortes_br, series_fluxo,
                titulo="Evasão e conclusão de coortes no Brasil",
                descricao=("Percentual de ingressantes que evadiram e que concluiram, "
                           "por coorte acompanhada pelo INEP."),
                casas=1))

    ultimo_ano = anos_br[-1] if anos_br else None
    pct_ead_br = None
    if ultimo_ano and serie_brasil[ultimo_ano]["vagas_total"]:
        pct_ead_br = round(100 * serie_brasil[ultimo_ano]["vagas_ead"]
                           / serie_brasil[ultimo_ano]["vagas_total"], 1)

    painel = {
        "vagas": agregado["vagas_total"],
        "matriculas": agregado["matriculas"],
        "cursos": agregado["n_cursos"],
        "ies": len(instituicoes),
        "municipios": len(acumulado.municipios),
        "pct_ead": pct_ead_br,
        "evasao": fluxo_br[sorted(fluxo_br)[-1]].get("evasao") if fluxo_br else None,
        "conclusao": next(
            (fluxo_br[c].get("conclusao") for c in sorted(fluxo_br, reverse=True)
             if fluxo_br[c].get("conclusao") is not None), None) if fluxo_br else None,
        "coorte": sorted(fluxo_br)[-1] if fluxo_br else None,
        "ies_com_pos": sum(1 for i in instituicoes.values() if i.get("pos_programas")),
        "ies_com_igc": sum(1 for i in instituicoes.values()
                           if i.get("igc_faixa") is not None),
    }

    html = env.get_template("index.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        resumo_cursos=resumo, areas=areas, agregado=agregado,
        painel=painel, anos_br=anos_br,
        grafico_modalidade=grafico_modalidade, grafico_evasao=grafico_evasao,
        leituras=insights.do_brasil(painel, serie_brasil, fluxo_br))
    (DIST / "index.html").write_text(html, encoding="utf-8")
    print("[OK] index.html")

    # ── Metodologia ──────────────────────────────────────────────────────────
    html = env.get_template("metodologia.html.j2").render(
        **ctx_base, depth="", curso_atual=None, cursos_meta=cursos_meta)
    (DIST / "metodologia.html").write_text(html, encoding="utf-8")
    print("[OK] metodologia.html")

    # ── Autoria e direitos ───────────────────────────────────────────────────
    html = env.get_template("autor.html.j2").render(
        **ctx_base, depth="", curso_atual=None)
    (DIST / "autor.html").write_text(html, encoding="utf-8")
    print("[OK] autor.html")

    # O registro de anterioridade é gerado por etl/registro_autoral.py e apenas
    # lido aqui. Ausente, a página sai sem a seção de integridade em vez de
    # inventar um hash — que seria o oposto do que a seção prova.
    registro = None
    caminho_registro = DATA / "registro_autoral.json"
    if caminho_registro.exists():
        with open(caminho_registro, encoding="utf-8") as f:
            registro = json.load(f)
        shutil.copyfile(caminho_registro, DIST / "registro_autoral.json")
    else:
        print("[AVISO] data/registro_autoral.json ausente — a página de direitos "
              "sairá sem a seção de integridade. Rode python etl/registro_autoral.py.")

    html = env.get_template("aviso-legal.html.j2").render(
        **ctx_base, depth="", curso_atual=None, registro=registro)
    (DIST / "aviso-legal.html").write_text(html, encoding="utf-8")
    print("[OK] aviso-legal.html")

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
    acumulado.fechar(perfil_municipal)
    for sigla, u in acumulado.ufs.items():
        u["regiao"] = REGIAO_UF.get(sigla)
        u["capital"] = CAPITAIS.get(sigla)

    (DIST / "uf").mkdir(parents=True, exist_ok=True)
    tpl_uf_perfil = env.get_template("uf-perfil.html.j2")
    for sigla, u in sorted(acumulado.ufs.items()):
        muns = sorted((m for (s, _), m in acumulado.municipios.items() if s == sigla),
                      key=lambda m: -m["vagas_total"])
        # Os quatro números que o mapa e o painel mostram, indexados pelo código
        # IBGE — a chave que a malha do IBGE também usa.
        por_codigo = {}
        for m in muns:
            if not m.get("cod_ibge"):
                continue
            pop = m.get("populacao")
            por_codigo[str(m["cod_ibge"])] = {
                "cod_ibge": m["cod_ibge"], "nome": m["nome"],
                "populacao": pop, "matriculas": m.get("matriculas"),
                "n_ies": m.get("n_ies"),
                "n_cursos": m.get("n_cursos_distintos") or m.get("n_cursos"),
                # A taxa é o que colore o mapa. Sem população não há taxa, e sem
                # taxa o município fica fora da escala em vez de entrar com um
                # valor inventado.
                "taxa": (round(100000 * (m.get("matriculas") or 0) / pop, 1)
                         if pop else None),
            }

        mapa = ""
        limites = carregar_limites_municipais(sigla)
        if limites and por_codigo:
            mapa = Markup(coropletico_municipal(
                limites, por_codigo,
                titulo=f"Matrículas por 100 mil habitantes em {NOME_UF[sigla]}",
                descricao=("Cada município do estado, colorido pela taxa de "
                           "matrículas presenciais por 100 mil habitantes. "
                           "Municípios sem oferta aparecem em cinza."),
                contorno_uf=malha_ufs.get(sigla),
                # O painel estadual mora em /uf/GO.html: sem o "../" o
                # navegador procura a base em /uf/static/ e recebe 404 —
                # e o mapa perde justamente os municipios sem oferta.
                base_href=("../" + bases_municipais[sigla]
                           if sigla in bases_municipais else None)))
        elif centroides and muns and sigla in malha_ufs:
            # Reserva: sem a malha municipal, o mapa de pontos ainda responde
            # "onde existe oferta" — só não mostra quem ficou de fora.
            mapa = Markup(pontos_municipais(
                centroides,
                [{**d, "valor": next(m["vagas_total"] for m in muns
                                     if str(m.get("cod_ibge")) == cod)}
                 for cod, d in por_codigo.items()],
                titulo=f"Municípios de {NOME_UF[sigla]} com oferta presencial",
                descricao=("Círculos proporcionais às vagas presenciais. Cada "
                           "ponto traz população, matrículas, instituições e "
                           "cursos do município."),
                contorno_ufs={sigla: malha_ufs[sigla]}))
        # A série exata, quando existe, vence a somada. As duas dão o mesmo
        # número para vagas e matrículas — mas só a exata sabe contar
        # instituições e municípios distintos, porque contagem de distintos não
        # se soma: a mesma universidade oferta vinte cursos, e somá-los a
        # contaria vinte vezes.
        serie_uf = series_uf.get(sigla) or serie_por_uf.get(sigla, {})
        exata = sigla in series_uf
        grafico_serie_uf = grafico_rede_uf = ""
        anos_uf = sorted(serie_uf)
        if len(serie_uf) >= 2:
            grafico_serie_uf = Markup(serie_temporal(
                anos_uf,
                [{"nome": "Vagas presenciais",
                  "valores": [serie_uf[a].get("vagas_presencial") for a in anos_uf]},
                 {"nome": "Vagas a distância",
                  "valores": [serie_uf[a].get("vagas_ead") for a in anos_uf]}],
                titulo=f"Capacidade presencial e a distância em {NOME_UF[sigla]}",
                descricao=("Vagas de todos os cursos do catálogo no estado, "
                           "por edição do Censo.")))
            if exata:
                grafico_rede_uf = Markup(serie_temporal(
                    anos_uf,
                    [{"nome": "Instituições com oferta",
                      "valores": [serie_uf[a].get("n_ies") for a in anos_uf]},
                     {"nome": "Municípios com oferta",
                      "valores": [serie_uf[a].get("municipios_oferta")
                                  for a in anos_uf]},
                     {"nome": "Cursos distintos",
                      "valores": [serie_uf[a].get("n_cursos") for a in anos_uf]}],
                    titulo=f"Rede de oferta em {NOME_UF[sigla]}",
                    descricao=("Contagens de distintos por edição do Censo: "
                               "instituicoes com vaga, municipios com oferta "
                               "presencial e rótulos CINE ofertados.")))

        fluxo_uf = (fluxo.get("ufs") or {}).get(sigla, {})
        grafico_fluxo = ""
        if fluxo_uf:
            # Cada indicador tem sua própria janela de coortes: evasão começa em
            # 2010, os demais em 2016. Desenhar tudo no mesmo eixo com buracos é
            # mais honesto que recortar todos ao menor denominador comum.
            coortes = sorted(fluxo_uf)
            series = []
            for chave, rotulo in (("evasao", "Evasão"), ("conclusao", "Conclusão"),
                                  ("retencao", "Retenção")):
                valores = [fluxo_uf.get(c, {}).get(chave, {}).get("total")
                           for c in coortes]
                if any(v is not None for v in valores):
                    series.append({"nome": rotulo, "valores": valores})
            if series:
                grafico_fluxo = Markup(serie_temporal(
                    coortes, series,
                    titulo=f"Taxas de coorte em {NOME_UF[sigla]}",
                    descricao=("Evasão, conclusão e retenção de ingressantes "
                               "acompanhados ao longo do tempo pelo INEP."),
                    casas=1))

        html = tpl_uf_perfil.render(
            **ctx_base, depth="../", curso_atual=None, sigla=sigla,
            fluxo=fluxo_uf, grafico_fluxo=grafico_fluxo,
            grafico_serie_uf=grafico_serie_uf,
            grafico_rede_uf=grafico_rede_uf,
            ano_populacao=ano_populacao,
            serie_uf_exata=exata,
            anos_serie_uf=anos_uf,
            coortes_fluxo=sorted(fluxo_uf),
            nome_uf=NOME_UF[sigla], u=u, municipios=muns, mapa=mapa,
            n_cursos_uf=len(u["cursos"]),
            grafico_areas=Markup(barras(
                [{"nome": a, "valor": v} for a, v in u["areas"].items()],
                titulo=f"Vagas por área do conhecimento em {NOME_UF[sigla]}",
                descricao="Áreas gerais da classificação CINE.", unidade=" vagas")),
            leituras=insights.da_uf(NOME_UF[sigla], u, serie_uf),
            leituras_fluxo=insights.do_fluxo(NOME_UF[sigla], fluxo_uf))
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
            nome_uf=NOME_UF[sigla], ano_populacao=ano_populacao,
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
        serie_ies = series_ies.get(str(co), {})
        anos_ies = sorted(serie_ies)
        grafico_serie_ies = grafico_cursos_ies = ""
        if len(anos_ies) >= 2:
            grafico_serie_ies = Markup(serie_temporal(
                anos_ies,
                [{"nome": "Vagas", "valores": [serie_ies[a].get("vagas_total")
                                               for a in anos_ies]},
                 {"nome": "Matrículas presenciais",
                  "valores": [serie_ies[a].get("matriculas") for a in anos_ies]},
                 {"nome": "Matrículas a distância",
                  "valores": [serie_ies[a].get("matriculas_ead") for a in anos_ies]}],
                titulo=f"Capacidade e matrículas de {ies['nome']}",
                descricao="Por edição do Censo da Educação Superior."))
            grafico_cursos_ies = Markup(serie_temporal(
                anos_ies,
                [{"nome": "Cursos distintos",
                  "valores": [serie_ies[a].get("n_cursos") for a in anos_ies]},
                 {"nome": "Municípios com oferta",
                  "valores": [serie_ies[a].get("municipios_oferta")
                              for a in anos_ies]}],
                titulo=f"Amplitude da oferta de {ies['nome']}",
                descricao=("Rótulos CINE distintos e municípios com oferta "
                           "presencial, por edição do Censo.")))

        html = tpl_ies.render(
            **ctx_base, depth="../", curso_atual=None, ies=ies, oferta=oferta,
            grafico_serie_ies=grafico_serie_ies,
            grafico_cursos_ies=grafico_cursos_ies,
            anos_serie_ies=anos_ies,
            grafico=Markup(barras(
                [{"nome": o["nome"], "valor": o["matriculas"]} for o in oferta],
                titulo=f"Cursos de {ies['nome']} por matrículas",
                descricao="Barras horizontais por matrículas.",
                unidade=" matrículas")),
            leituras=insights.da_instituicao(ies, serie_ies))
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

    # ── Índice de busca do site inteiro ──────────────────────────────────────
    # Até aqui a caixa do cabeçalho só achava curso. Mas existe página para
    # 2.561 instituições, 1.119 municípios e 27 unidades federativas, e para
    # chegar a qualquer uma delas era preciso saber DE ANTEMÃO em qual índice
    # procurar: quem digitava "UFG" ou "Goiânia" não encontrava nada.
    #
    # O índice é uma lista de listas, não de objetos: repetir as chaves 4.000
    # vezes dobraria o arquivo sem acrescentar informação. A ordem de cada
    # grupo é a de relevância — vagas, matrículas, população atendida — para
    # que a busca vazia já mostre algo útil.
    indice = {
        "c": [[r["nome"], r["slug"], r["vagas_total"] or 0, r["area_cine"]]
              for r in resumo],
        "i": [[i["nome"], i["co_ies"], i.get("uf_sede") or "",
               i.get("sigla") or "", i.get("matriculas") or 0]
              for i in lista_ies],
        "m": [[m["nome"], f"{sigla}-{slug}", sigla, m.get("vagas_total") or 0]
              for (sigla, slug), m in sorted(
                  acumulado.municipios.items(),
                  key=lambda kv: -(kv[1].get("vagas_total") or 0))],
        "u": [[NOME_UF[s], s] for s in ufs_disponiveis],
        "p": [
            ["Painel executivo", "index.html"],
            ["Estados", "estados.html"],
            ["Regiões", "regioes.html"],
            ["Redes de ensino", "redes.html"],
            ["Acesso e equidade", "acesso.html"],
            ["Municípios", "municipios.html"],
            ["Instituições", "instituicoes.html"],
            ["Rankings", "rankings.html"],
            ["Comparar cursos", "comparar-cursos.html"],
            ["Dados abertos e API", "api.html"],
            ["Metodologia", "metodologia.html"],
            ["Sobre o Autor", "autor.html"],
            ["Direitos autorais", "aviso-legal.html"],
            ["Privacidade", "privacidade.html"],
        ],
    }
    bruto = json.dumps(indice, ensure_ascii=False, separators=(",", ":"))
    (DIST / "static" / "js" / "indice.js").write_text(
        "window.INDICE=" + bruto + ";", encoding="utf-8")
    print(f"[OK] static/js/indice.js — {sum(len(v) for v in indice.values())} "
          f"destinos, {len(bruto) / 1024:.0f} KB")

    # A participação pública por UF é média ponderada por vagas, já calculada
    # por curso. Aqui se usa a do maior curso de cada UF como referência? Não:
    # recalcula-se pelo próprio agregado, para não depender de um curso só.
    ufs_para_rede = {}
    for sigla, u in acumulado.ufs.items():
        ultimo = sorted(serie_por_uf.get(sigla, {}))
        if ultimo:
            u["vagas_publicas"] = serie_por_uf[sigla][ultimo[-1]].get("vagas_publicas")
        if u.get('vagas_total'):
            ufs_para_rede[sigla] = {
                'pct_rede_publica': round(
                    100 * (u.get('vagas_publicas') or 0) / u['vagas_total'], 1)
                if u.get('vagas_publicas') is not None else None}

    # ── Acesso e equidade ────────────────────────────────────────────────────
    # Curso pequeno faz percentual oscilar demais para significar algo: 40 mulheres
    # entre 60 ingressantes vira "66,7%" e lidera qualquer ranking. O piso vale
    # para os dois gráficos e está declarado na página.
    MINIMO_INGRESSOS = 5000

    com_perfil = [r for r in resumo
                  if (r.get("ingressos") or 0) >= MINIMO_INGRESSOS
                  and r.get("pct_mulheres") is not None]

    def extremos(campo, n=10):
        base = [r for r in com_perfil if r.get(campo) is not None]
        base.sort(key=lambda r: -r[campo])
        return base[:n], base[-n:][::-1]

    def acumular_ponderado(campo):
        """Média nacional ponderada pelos ingressantes de cada curso."""
        num = den = 0.0
        for r in resumo:
            v, p = r.get(campo), r.get("ingressos")
            if v is None or not p:
                continue
            num += v * p
            den += p
        return round(num / den, 1) if den else None

    painel_acesso = {
        "ingressos": sum(r.get("ingressos") or 0 for r in resumo),
        "pct_mulheres": acumular_ponderado("pct_mulheres"),
        "pct_ppi": acumular_ponderado("pct_ppi"),
        "pct_cor_nao_declarada": acumular_ponderado("pct_cor_nao_declarada"),
        "pct_financiamento": acumular_ponderado("pct_financiamento"),
        "pct_noturno": acumular_ponderado("pct_noturno"),
    }

    # Perfil por UF: média ponderada pelos ingressantes, somando os cursos.
    perfil_uf = {}
    for entrada in catalogo:
        caminho_nac = DATA / "cursos" / entrada["slug"] / "nacional.json"
        if not caminho_nac.exists():
            continue
        with open(caminho_nac, encoding="utf-8") as f:
            for sigla, d in json.load(f)["ufs"].items():
                ing = d.get("ingressos") or 0
                if not ing:
                    continue
                alvo = perfil_uf.setdefault(sigla, {"ing": 0, "ppi": 0.0, "nd": 0.0,
                                                    "mul": 0.0})
                alvo["ing"] += ing
                for chave, campo in (("ppi", "pct_ppi"), ("nd", "pct_cor_nao_declarada"),
                                     ("mul", "pct_mulheres")):
                    if d.get(campo) is not None:
                        alvo[chave] += d[campo] * ing
    for sigla, a in perfil_uf.items():
        for chave in ("ppi", "nd", "mul"):
            a[chave] = round(a[chave] / a["ing"], 1) if a["ing"] else None

    mapa_ppi = mapa_nd = ""
    if malha_ufs and perfil_uf:
        mapa_ppi = Markup(coropletico(
            malha_ufs, {s: a["ppi"] for s, a in perfil_uf.items()},
            titulo="Ingressantes pretos, pardos e indígenas, por UF",
            descricao=("Mapa do Brasil colorido pelo percentual de ingressantes "
                       "presenciais que se declararam pretos, pardos ou indígenas."),
            unidade="%", casas=1, nomes_uf=NOME_UF))
        mapa_nd = Markup(coropletico(
            malha_ufs, {s: a["nd"] for s, a in perfil_uf.items()},
            titulo="Ingressantes sem declaração de cor, por UF",
            descricao=("Mapa do Brasil colorido pela fatia de ingressantes que não "
                       "declarou cor ou raça — medida da incerteza do mapa anterior."),
            unidade="%", casas=1, divergente=True, nomes_uf=NOME_UF))

    maior_mul, menor_mul = extremos("pct_mulheres")
    maior_ppi, menor_ppi = extremos("pct_ppi")

    def barras_extremos(maiores, menores, campo, titulo, descricao):
        itens = ([{"nome": r["nome"], "valor": r[campo]} for r in maiores]
                 + [{"nome": r["nome"], "valor": r[campo]} for r in menores])
        return Markup(barras(itens, titulo=titulo, descricao=descricao,
                             unidade="%", casas=1, maximo_itens=len(itens)))

    grafico_mulheres = barras_extremos(
        maior_mul, menor_mul, "pct_mulheres",
        "Participação feminina entre ingressantes, por curso",
        "Dez cursos com maior e dez com menor participação feminina.")
    grafico_ppi = barras_extremos(
        maior_ppi, menor_ppi, "pct_ppi",
        "Ingressantes pretos, pardos e indígenas, por curso",
        "Dez cursos com maior e dez com menor percentual.")

    maiores_cursos = sorted([r for r in resumo if r.get("ingressos")],
                            key=lambda r: -(r["ingressos"] or 0))[:30]

    html = env.get_template("acesso.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        painel=painel_acesso, cursos=maiores_cursos,
        minimo_ingressos=MINIMO_INGRESSOS,
        mapa_ppi=mapa_ppi, mapa_nd=mapa_nd,
        grafico_mulheres=grafico_mulheres, grafico_ppi=grafico_ppi,
        leituras=insights.do_acesso(painel_acesso, maior_mul, menor_mul,
                                    maior_ppi, menor_ppi, perfil_uf))
    (DIST / "acesso.html").write_text(html, encoding="utf-8")
    print(f"[OK] acesso.html — {len(com_perfil)} cursos acima do piso de ingressantes")

    # ── Redes: pública contra privada ────────────────────────────────────────
    def media(valores):
        """Média simples, ignorando ausentes. Simples de propósito: ponderar por
        matrículas faria uma única universidade gigante definir o número da rede
        inteira, que é o oposto do que a comparação quer mostrar."""
        limpos = [v for v in valores if v is not None]
        return round(sum(limpos) / len(limpos), 1) if limpos else None

    lista_todas = list(instituicoes.values())
    publicas = [i for i in lista_todas if i.get("rede") == "Pública"]
    privadas = [i for i in lista_todas if i.get("rede") == "Privada"]

    def soma(grupo, campo):
        return sum(i.get(campo) or 0 for i in grupo)

    def linha(rotulo, valor_pub, valor_priv, sufixo="", casas=0):
        total = (valor_pub or 0) + (valor_priv or 0)
        def formatar(v):
            if v is None:
                return None
            if casas:
                return f"{v:.{casas}f}".replace(".", ",") + sufixo
            return f"{round(v):,}".replace(",", ".") + sufixo
        return {
            "rotulo": rotulo, "publica": valor_pub, "privada": valor_priv,
            "fmt_publica": formatar(valor_pub), "fmt_privada": formatar(valor_priv),
            "pct": round(100 * valor_pub / total, 1) if total and not casas else None,
        }

    comparativo = [
        linha("Instituições", len(publicas), len(privadas)),
        linha("Matrículas", soma(publicas, "matriculas"), soma(privadas, "matriculas")),
        linha("Vagas", soma(publicas, "vagas"), soma(privadas, "vagas")),
        linha("Vagas presenciais", soma(publicas, "vagas_presencial"),
              soma(privadas, "vagas_presencial")),
        linha("Vagas a distância", soma(publicas, "vagas_ead"),
              soma(privadas, "vagas_ead")),
        linha("Docentes", soma(publicas, "docentes"), soma(privadas, "docentes")),
        linha("% Doutores (média entre IES)", media([i.get("pct_doutores") for i in publicas]),
              media([i.get("pct_doutores") for i in privadas]), "%", 1),
        linha("% Regime integral (média)", media([i.get("pct_regime_integral") for i in publicas]),
              media([i.get("pct_regime_integral") for i in privadas]), "%", 1),
        linha("IGC médio", media([i.get("igc_continuo") for i in publicas]),
              media([i.get("igc_continuo") for i in privadas]), "", 2),
        linha("Instituições com pós stricto sensu",
              sum(1 for i in publicas if i.get("pos_programas")),
              sum(1 for i in privadas if i.get("pos_programas"))),
        linha("Programas de pós", soma(publicas, "pos_programas"),
              soma(privadas, "pos_programas")),
    ]

    por_categoria = {}
    for i in lista_todas:
        c = i.get("categoria") or "Não declarada"
        alvo = por_categoria.setdefault(c, {"nome": c, "n": 0, "matriculas": 0,
                                            "vagas": 0, "com_pos": 0, "_dout": []})
        alvo["n"] += 1
        alvo["matriculas"] += i.get("matriculas") or 0
        alvo["vagas"] += i.get("vagas") or 0
        if i.get("pos_programas"):
            alvo["com_pos"] += 1
        alvo["_dout"].append(i.get("pct_doutores"))
    categorias = []
    for c in sorted(por_categoria.values(), key=lambda x: -x["matriculas"]):
        c["pct_doutores"] = media(c.pop("_dout"))
        categorias.append(c)

    por_org = {}
    for i in lista_todas:
        o = i.get("organizacao") or "Não declarada"
        alvo = por_org.setdefault(o, {"nome": o, "n": 0, "publicas": 0,
                                      "privadas": 0, "matriculas": 0})
        alvo["n"] += 1
        alvo["matriculas"] += i.get("matriculas") or 0
        if i.get("rede") == "Pública":
            alvo["publicas"] += 1
        else:
            alvo["privadas"] += 1
    organizacoes = sorted(por_org.values(), key=lambda x: -x["matriculas"])

    grafico_serie_rede = ""
    if len(anos_br) >= 2 and any(serie_brasil[a].get("vagas_publicas") for a in anos_br):
        grafico_serie_rede = Markup(serie_temporal(
            anos_br,
            [{"nome": "Rede pública",
              "valores": [serie_brasil[a].get("vagas_publicas") for a in anos_br]},
             {"nome": "Rede privada",
              "valores": [serie_brasil[a]["vagas_total"]
                          - (serie_brasil[a].get("vagas_publicas") or 0)
                          for a in anos_br]}],
            titulo="Capacidade por rede no Brasil",
            descricao=("Duas linhas comparando as vagas da rede pública e da rede "
                       "privada ao longo das edições do Censo.")))

    grafico_org = Markup(barras(
        [{"nome": o["nome"], "valor": o["matriculas"]} for o in organizacoes],
        titulo="Matrículas por organização acadêmica",
        descricao="Barras horizontais por tipo de instituição.",
        unidade=" matrículas")) if organizacoes else ""

    mapa_rede = ""
    if malha_ufs:
        pct_por_uf = {s: (u.get("pct_rede_publica")) for s, u in ufs_para_rede.items()}
        if any(v is not None for v in pct_por_uf.values()):
            mapa_rede = Markup(coropletico(
                malha_ufs, pct_por_uf,
                titulo="Participação da rede pública na capacidade, por UF",
                descricao=("Mapa do Brasil colorido pelo percentual da capacidade "
                           "que pertence à rede pública."),
                unidade="%", casas=1, divergente=True, nomes_uf=NOME_UF))

    html = env.get_template("redes.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        comparativo=comparativo, categorias=categorias, organizacoes=organizacoes,
        anos_br=anos_br, grafico_serie=grafico_serie_rede,
        grafico_organizacao=grafico_org, mapa=mapa_rede,
        leituras=insights.das_redes(comparativo, serie_brasil, anos_br, categorias))
    (DIST / "redes.html").write_text(html, encoding="utf-8")
    print(f"[OK] redes.html — {len(categorias)} categorias, {len(organizacoes)} organizações")

    # ── Regiões ──────────────────────────────────────────────────────────────
    # A desigualdade regional é a moldura de quase toda discussão sobre acesso ao
    # ensino superior, e até aqui só dava para montá-la de cabeça a partir das 27
    # UFs. Soma-se o que soma; nº de IES e municípios já vêm contados por UF sem
    # duplicidade entre elas, então aqui a soma é legítima.
    ORDEM_REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]
    por_regiao = {}
    for sigla, u in acumulado.ufs.items():
        nome = REGIAO_UF.get(sigla)
        if not nome:
            continue
        alvo = por_regiao.setdefault(nome, {
            "nome": nome, "ufs": [],
            "vagas_total": 0, "vagas_presencial": 0, "vagas_ead": 0,
            "matriculas": 0, "n_ies": 0, "municipios_oferta": 0,
            "municipios_total": 0, "populacao": 0,
        })
        alvo["ufs"].append(sigla)
        for campo in ("vagas_total", "vagas_presencial", "vagas_ead", "matriculas",
                      "n_ies", "municipios_oferta", "municipios_total", "populacao"):
            alvo[campo] += u.get(campo) or 0

    for r in por_regiao.values():
        r["ufs"].sort()
        if r["populacao"]:
            r["vagas_por_100k"] = round(100000 * r["vagas_total"] / r["populacao"], 1)
            # Densidade presencial: a régua honesta para acesso local, porque a
            # vaga EaD é contada onde está a mantenedora, não o estudante.
            r["presencial_por_100k"] = round(
                100000 * r["vagas_presencial"] / r["populacao"], 1)
        if r["municipios_total"]:
            r["pct_cobertura"] = round(
                100 * r["municipios_oferta"] / r["municipios_total"], 1)

    regioes = [por_regiao[n] for n in ORDEM_REGIOES if n in por_regiao]

    mapa_regiao = ""
    if malha_ufs and regioes:
        # Cada UF pintada com o valor da REGIÃO dela: o mapa mostra o bloco, não o
        # estado. A nota da figura diz isso, para ninguém ler como dado estadual.
        valor_por_uf = {}
        for r in regioes:
            for sigla in r["ufs"]:
                valor_por_uf[sigla] = r.get("presencial_por_100k")
        mapa_regiao = Markup(coropletico(
            malha_ufs, valor_por_uf,
            titulo="Vagas presenciais por 100 mil habitantes, por região",
            descricao=("Mapa do Brasil com cada unidade federativa pintada pelo "
                       "valor da sua região, não pelo próprio."),
            unidade=" vagas/100 mil", casas=1, nomes_uf=NOME_UF))

    grafico_densidade = Markup(barras(
        [{"nome": r["nome"], "valor": r.get("presencial_por_100k")} for r in regioes],
        titulo="Vagas presenciais por 100 mil habitantes",
        descricao=("Barras horizontais das cinco regiões por densidade de oferta "
                   "presencial — a régua de acesso local."),
        unidade=" / 100 mil", casas=1)) if regioes else ""

    fluxo_regioes = fluxo.get("regioes") or {}
    grafico_evasao_regiao = ""
    coorte_inicial = ""
    if fluxo_regioes:
        coortes_r = sorted({c for v in fluxo_regioes.values() for c in v})
        coorte_inicial = coortes_r[0] if coortes_r else ""
        series_r = []
        for nome in ORDEM_REGIOES:
            v = fluxo_regioes.get(nome)
            if not v:
                continue
            valores = [(v.get(c, {}).get("evasao") or {}).get("total") for c in coortes_r]
            if any(x is not None for x in valores):
                series_r.append({"nome": nome, "valores": valores})
        if series_r:
            grafico_evasao_regiao = Markup(serie_temporal(
                coortes_r, series_r,
                titulo="Evasão por região, por coorte",
                descricao=("Cinco linhas, uma por região, do percentual de "
                           "ingressantes que evadiram."),
                casas=1))

    html = env.get_template("regioes.html.j2").render(
        **ctx_base, depth="", curso_atual=None, regioes=regioes,
        n_cursos=len(resumo), mapa=mapa_regiao,
        grafico_densidade=grafico_densidade,
        grafico_evasao=grafico_evasao_regiao,
        coorte_inicial=coorte_inicial,
        leituras=insights.das_regioes(regioes, fluxo_regioes))
    (DIST / "regioes.html").write_text(html, encoding="utf-8")
    print(f"[OK] regioes.html — {len(regioes)} regiões")

    # ── Comparação entre estados e entre instituições ────────────────────────
    # Um script genérico serve os dois: a necessidade é a mesma (escolher itens,
    # escolher campos, ver tabela e barras), e duas cópias divergiriam.
    def publicar_comparaveis(nome_arquivo, tipo, rotulo, campos, itens):
        conteudo = {"tipo": tipo, "rotulo_entidade": rotulo,
                    "campos": campos, "itens": itens}
        (DIST / "static" / "js" / nome_arquivo).write_text(
            "window.COMPARAVEIS=" + json.dumps(conteudo, ensure_ascii=False,
                                               separators=(",", ":")) + ";",
            encoding="utf-8")

    campos_uf = [
        {"k": "vagas_total", "rotulo": "Vagas"},
        {"k": "vagas_presencial", "rotulo": "Vagas presenciais"},
        {"k": "vagas_ead", "rotulo": "Vagas EaD"},
        {"k": "matriculas", "rotulo": "Matrículas presenciais"},
        {"k": "n_ies", "rotulo": "Instituições"},
        {"k": "municipios_oferta", "rotulo": "Municípios com oferta"},
        {"k": "municipios_deserto", "rotulo": "Municípios sem oferta"},
        {"k": "vagas_por_100k", "rotulo": "Vagas / 100 mil hab.", "casas": 1},
        {"k": "pct_ead", "rotulo": "% EaD", "casas": 1, "unidade": "%"},
        {"k": "evasao", "rotulo": "Evasão (coorte)", "casas": 1, "unidade": "%"},
        {"k": "conclusao", "rotulo": "Conclusão (coorte)", "casas": 1, "unidade": "%"},
        {"k": "retencao", "rotulo": "Retenção (coorte)", "casas": 1, "unidade": "%"},
    ]
    itens_uf = []
    for u in lista_ufs:
        sigla = u["sigla"]
        do_fluxo = (fluxo.get("ufs") or {}).get(sigla, {})
        ultima = sorted(do_fluxo)[-1] if do_fluxo else None
        linha = []
        for c in campos_uf:
            if c["k"] in ("evasao", "conclusao", "retencao"):
                reg = (do_fluxo.get(ultima) or {}).get(c["k"]) if ultima else None
                linha.append(reg.get("total") if reg else None)
            else:
                linha.append(u.get(c["k"]))
        itens_uf.append({"id": sigla, "nome": u["nome"], "sub": u.get("regiao"),
                         "url": f"uf/{sigla}.html", "v": linha})
    publicar_comparaveis("comparaveis-estados.js", "estados", "Estado",
                         campos_uf, itens_uf)
    html = env.get_template("comparar-entidades.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        titulo="Comparar estados",
        descricao=("Confronte unidades federativas em capacidade, alcance "
                   "territorial e trajetória dos estudantes."),
        ressalva=("Índices por curso — ICT, IAF, HHI — não entram: são definidos "
                  "curso a curso, e a média deles entre cursos diferentes não "
                  "significa nada. As taxas de coorte são da última publicada."),
        rotulo_entidade="Estados", arquivo_dados="comparaveis-estados.js")
    (DIST / "comparar-estados.html").write_text(html, encoding="utf-8")
    print(f"[OK] comparar-estados.html — {len(itens_uf)} estados")

    campos_ies = [
        {"k": "matriculas", "rotulo": "Matrículas"},
        {"k": "vagas", "rotulo": "Vagas"},
        {"k": "vagas_presencial", "rotulo": "Vagas presenciais"},
        {"k": "vagas_ead", "rotulo": "Vagas EaD"},
        {"k": "n_cursos_catalogo", "rotulo": "Cursos acompanhados"},
        {"k": "municipios", "rotulo": "Municípios com oferta"},
        {"k": "docentes", "rotulo": "Docentes"},
        {"k": "pct_doutores", "rotulo": "% Doutores", "casas": 1, "unidade": "%"},
        {"k": "pct_regime_integral", "rotulo": "% Regime integral", "casas": 1,
         "unidade": "%"},
        {"k": "alunos_por_docente", "rotulo": "Alunos por docente", "casas": 1},
        {"k": "igc_continuo", "rotulo": "IGC (1–5)", "casas": 2},
        {"k": "pos_programas", "rotulo": "Programas de pós"},
        {"k": "pos_conceito_medio", "rotulo": "Conceito CAPES (1–7)", "casas": 2},
    ]
    itens_ies = []
    for i in lista_ies:
        sub = " · ".join(x for x in (i.get("organizacao"), i.get("rede"),
                                     i.get("uf_sede")) if x)
        itens_ies.append({
            "id": i["co_ies"], "nome": i["nome"], "sub": sub,
            "url": f"instituicao/{i['co_ies']}.html",
            "v": [i.get(c["k"]) for c in campos_ies],
        })
    publicar_comparaveis("comparaveis-instituicoes.js", "instituicoes",
                         "Instituição", campos_ies, itens_ies)
    html = env.get_template("comparar-entidades.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        titulo="Comparar instituições",
        descricao=("Confronte instituições em capacidade, corpo docente, avaliação "
                   "e pós-graduação."),
        ressalva=("Escalas não se misturam: o IGC vai de 1 a 5 e o conceito CAPES "
                  "de 1 a 7, sobre objetos diferentes. Corpo docente e IGC são da "
                  "instituição inteira, nunca de um curso. Ausência de IGC significa "
                  "não avaliada; ausência de pós significa que não há programa."),
        rotulo_entidade="Instituições", arquivo_dados="comparaveis-instituicoes.js")
    (DIST / "comparar-instituicoes.html").write_text(html, encoding="utf-8")
    print(f"[OK] comparar-instituicoes.html — {len(itens_ies)} instituições")

    # ── Índice de municípios ─────────────────────────────────────────────────
    lista_mun = sorted(acumulado.municipios.values(),
                       key=lambda m: -m["vagas_total"])
    html = env.get_template("municipios.html.j2").render(
        **ctx_base, depth="", curso_atual=None, municipios=lista_mun,
        total=len(lista_mun),
        ufs=sorted({m["uf"] for m in lista_mun}))
    (DIST / "municipios.html").write_text(html, encoding="utf-8")
    print(f"[OK] municipios.html — {len(lista_mun)} municípios")

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
    if series_uf:
        anos_serie = sorted({a for v in series_uf.values() for a in v})
        publicar("series/territorial.json",
                 {"metadados": {"extracao": data_extracao, "anos": anos_serie,
                                "aviso": ("contagens de distintos — n_ies, n_cursos, "
                                          "municipios_oferta — não se somam entre "
                                          "UFs; o total nacional já vem calculado "
                                          "sobre as linhas, no recorte BR")},
                  "series": series_uf},
                 "Série histórica por unidade federativa e Brasil, por edição do Censo")
    if series_ies:
        publicar("series/instituicoes.json",
                 {"metadados": {"extracao": data_extracao,
                                "aviso": ("ano em que a instituição não teve oferta "
                                          "fica ausente da série, nunca zerado")},
                  "series": series_ies},
                 "Série histórica por instituição, por edição do Censo")

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
