"""
Gerador do site estático multi-curso.

    python site/build.py

Lê data/cursos/<slug>/nacional.json e produz site/dist/ com:
    index.html                        panorama e vitrine de cursos
    comparar-cursos.html              comparação entre cursos (Brasil ou UF)
    metodologia.html                  fontes, fórmulas e limites de leitura
    curso/<slug>/index.html           panorama do curso
    curso/<slug>/uf/<UF>.html         detalhe por unidade federativa
"""
import json
import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
SITE = REPO / "site"
DIST = SITE / "dist"

import sys
sys.path.insert(0, str(REPO / "etl"))
from referencias import NOME_UF  # noqa: E402

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


def carregar_cursos():
    with open(DATA / "cursos.json", encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    cursos = []
    for c in catalogo:
        caminho = DATA / "cursos" / c["slug"] / "nacional.json"
        if not caminho.exists():
            print(f"[PULADO] {c['nome']}: nacional.json ausente.")
            continue
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        municipios = {}
        dir_mun = DATA / "cursos" / c["slug"] / "municipios"
        if dir_mun.exists():
            for arq in dir_mun.glob("*.json"):
                with open(arq, encoding="utf-8") as f:
                    municipios[arq.stem] = json.load(f)
        cursos.append({**c, "dados": dados, "municipios": municipios,
                       "total": agregar_nacional(dados["ufs"])})
    return cursos


def _fmt(valor, casas):
    if valor is None:
        return None
    return f"{valor:.{casas}f}".replace(".", ",")


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    env = Environment(loader=FileSystemLoader(str(SITE / "templates")),
                      autoescape=select_autoescape(["html", "xml"]))
    env.globals.update(
        fmt1=lambda v: _fmt(v, 1), fmt2=lambda v: _fmt(v, 2),
        fmt3=lambda v: _fmt(v, 3), fmt4=lambda v: _fmt(v, 4),
        milhar=lambda v: None if v is None else f"{v:,}".replace(",", "."),
        pct=lambda v: None if v is None else f"{v * 100:.1f}".replace(".", ",") + "%",
    )

    cursos = carregar_cursos()
    if not cursos:
        raise SystemExit("[ERRO] Nenhum curso com dados. Rode o pipeline do ETL antes.")

    versao_censo = cursos[0]["dados"]["metadados"]["versao_censo"]
    data_extracao = str(date.today())
    lista_cursos = [{"slug": c["slug"], "nome": c["nome"]} for c in cursos]
    ctx_base = {"cursos": lista_cursos, "versao_censo": versao_censo,
                "data_extracao": data_extracao}

    # ── Páginas por curso ────────────────────────────────────────────────────
    for c in cursos:
        meta = c["dados"]["metadados"]
        ufs = c["dados"]["ufs"]
        tem_qualidade = any(u.get("ENADE") is not None for u in ufs.values())

        destino = DIST / "curso" / c["slug"]
        (destino / "uf").mkdir(parents=True, exist_ok=True)

        html = env.get_template("curso.html.j2").render(
            **ctx_base, depth="../../", curso_atual=c["slug"],
            meta=meta, total=c["total"], tem_qualidade=tem_qualidade,
            dados_json=json.dumps(ufs, ensure_ascii=False),
            meta_json=json.dumps(meta, ensure_ascii=False))
        (destino / "index.html").write_text(html, encoding="utf-8")

        for sigla, d in ufs.items():
            html_uf = env.get_template("uf.html.j2").render(
                **ctx_base, depth="../../../", curso_atual=c["slug"],
                meta=meta, sigla=sigla, nome_uf=NOME_UF[sigla], d=d,
                municipios=c["municipios"].get(sigla, []),
                dados_uf_json=json.dumps(d, ensure_ascii=False))
            (destino / "uf" / f"{sigla}.html").write_text(html_uf, encoding="utf-8")

        print(f"[OK] curso/{c['slug']}/ — 1 panorama + {len(ufs)} UFs")

    # ── Comparação entre cursos ──────────────────────────────────────────────
    comparacao = {}
    for c in cursos:
        comparacao[c["slug"]] = {"BR": c["total"], **c["dados"]["ufs"]}
    ufs_disponiveis = sorted({uf for c in cursos for uf in c["dados"]["ufs"]})

    html = env.get_template("comparar-cursos.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        cursos_json=json.dumps(lista_cursos, ensure_ascii=False),
        comparacao_json=json.dumps(comparacao, ensure_ascii=False),
        ufs_json=json.dumps(ufs_disponiveis, ensure_ascii=False))
    (DIST / "comparar-cursos.html").write_text(html, encoding="utf-8")
    print(f"[OK] comparar-cursos.html — {len(cursos)} cursos × {len(ufs_disponiveis) + 1} recortes")

    # ── Home ─────────────────────────────────────────────────────────────────
    resumo = [{
        "slug": c["slug"], "nome": c["nome"], "area_cine": c["area_cine"],
        "vagas_total": c["total"]["vagas_total"],
        "pct_ead": c["total"]["pct_ead"],
        "municipios_oferta": c["total"]["municipios_oferta"],
        "tem_qualidade": any(u.get("ENADE") is not None for u in c["dados"]["ufs"].values()),
    } for c in cursos]

    agregado = {
        "vagas_total": sum(c["total"]["vagas_total"] or 0 for c in cursos),
        "matriculas": sum(c["total"]["matriculas"] or 0 for c in cursos),
        "n_cursos": len(cursos),
    }

    html = env.get_template("index.html.j2").render(
        **ctx_base, depth="", curso_atual=None,
        resumo_cursos=resumo, agregado=agregado)
    (DIST / "index.html").write_text(html, encoding="utf-8")
    print("[OK] index.html")

    # ── Metodologia ──────────────────────────────────────────────────────────
    cursos_meta = [{
        "nome": c["nome"],
        "ciclo_enade": c["dados"]["metadados"].get("ciclo_enade"),
        "tem_qualidade": any(u.get("ENADE") is not None for u in c["dados"]["ufs"].values()),
    } for c in cursos]
    html = env.get_template("metodologia.html.j2").render(
        **ctx_base, depth="", curso_atual=None, cursos_meta=cursos_meta)
    (DIST / "metodologia.html").write_text(html, encoding="utf-8")
    print("[OK] metodologia.html")

    # ── Estáticos ────────────────────────────────────────────────────────────
    shutil.copytree(SITE / "static", DIST / "static")

    paginas = list(DIST.rglob("*.html"))
    print(f"\n[BUILD] {len(paginas)} páginas em {DIST}")


if __name__ == "__main__":
    main()
