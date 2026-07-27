"""
Camada institucional: quem oferta, com que corpo docente, sob qual organização.

Uso:
    python etl/instituicoes.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2024.CSV \
                               --ies   caminho/MICRODADOS_ED_SUP_IES_2024.CSV

Produz data/instituicoes.json com uma entrada por IES que oferta algum curso do
catálogo: identificação, organização acadêmica, categoria administrativa, corpo
docente e o que ela oferta (vagas, matrículas, cursos, UFs, municípios).

Limite importante do que dá para dizer com isto. O corpo docente vem do cadastro
de IES e é da INSTITUIÇÃO INTEIRA, não do curso: uma universidade com 3 mil
docentes não tem 3 mil docentes em Farmácia. Por isso a relação aluno/docente e
os percentuais de titulação são reportados no nível da IES e jamais atribuídos a
um curso — atribuí-los seria inventar um rateio que o Censo não autoriza.

O que NÃO está aqui, e por quê: IGC, Conceito Institucional, recredenciamento e
data da última avaliação não são do Censo. Vêm do e-MEC e dos Indicadores de
Qualidade do INEP, bases distintas. Enquanto não forem ingeridas, esses campos
não existem — em vez de aparecerem vazios sugerindo falha de coleta.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

COLUNAS_CURSOS = [
    "SG_UF", "NO_MUNICIPIO", "CO_IES", "NO_CINE_ROTULO", "TP_MODALIDADE_ENSINO",
    "QT_VG_TOTAL", "QT_CURSO", "QT_MAT", "QT_ING", "QT_CONC",
]
COLUNAS_IES = [
    "NU_ANO_CENSO", "CO_IES", "NO_IES", "SG_IES", "SG_UF_IES", "NO_MUNICIPIO_IES",
    "TP_ORGANIZACAO_ACADEMICA", "TP_CATEGORIA_ADMINISTRATIVA",
    "QT_DOC_TOTAL", "QT_DOC_EX_MEST", "QT_DOC_EX_DOUT", "QT_DOC_EX_INT",
    "QT_TEC_TOTAL",
]

ORGANIZACAO = {
    "1": "Universidade",
    "2": "Centro Universitário",
    "3": "Faculdade",
    "4": "Instituto Federal / CEFET",
    "5": "Instituto Federal / CEFET",
}
CATEGORIA = {
    "1": "Pública Federal",
    "2": "Pública Estadual",
    "3": "Pública Municipal",
    "4": "Privada com fins lucrativos",
    "5": "Privada sem fins lucrativos",
    "6": "Privada confessional/comunitária/filantrópica",
    "7": "Especial",
}
# Agrupamento grosso, para o recorte que todo mundo quer primeiro.
def rede(codigo):
    return "Pública" if codigo in {"1", "2", "3"} else "Privada"


def _int(serie):
    return pd.to_numeric(serie, errors="coerce").fillna(0).astype(int)


def _pct(parte, todo):
    """Percentual 0–100, ou None quando não há denominador — nunca zero falso."""
    if not todo:
        return None
    return round(100 * parte / todo, 1)


def main():
    parser = argparse.ArgumentParser(description="Camada institucional do observatório")
    parser.add_argument("--censo", required=True)
    parser.add_argument("--ies", required=True)
    parser.add_argument("--cursos", default=str(DATA / "cursos.json"))
    args = parser.parse_args()

    with open(args.cursos, encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]
    slug_do_rotulo = {c["cine_rotulo"]: c["slug"] for c in catalogo}

    print(f"[INFO] Lendo cadastro de IES {args.ies} ...")
    ies = pd.read_csv(args.ies, sep=";", encoding="latin-1", dtype=str,
                      low_memory=False, usecols=COLUNAS_IES)
    for col in COLUNAS_IES:
        if col.startswith("QT_"):
            ies[col] = _int(ies[col])
    ano = str(ies["NU_ANO_CENSO"].iloc[0])
    print(f"[INFO] {len(ies)} instituições no cadastro · Censo {ano}")

    print(f"[INFO] Lendo {args.censo} ...")
    cursos = pd.read_csv(args.censo, sep=";", encoding="latin-1", dtype=str,
                         low_memory=False, usecols=COLUNAS_CURSOS)
    for col in COLUNAS_CURSOS:
        if col.startswith("QT_"):
            cursos[col] = _int(cursos[col])

    # Só interessa o que está no catálogo — o Censo tem rótulos que não viraram curso.
    cursos = cursos[cursos["NO_CINE_ROTULO"].isin(slug_do_rotulo)]
    print(f"[INFO] {len(cursos)} linhas de curso no catálogo.")

    saida = {}
    por_ies = dict(list(cursos.groupby("CO_IES")))

    for _, linha in ies.iterrows():
        co = linha["CO_IES"]
        sub = por_ies.get(co)
        if sub is None or sub.empty:
            continue  # instituição sem oferta dos cursos do catálogo

        presencial = sub[sub["TP_MODALIDADE_ENSINO"] == "1"]
        ead = sub[sub["TP_MODALIDADE_ENSINO"] == "2"]

        vagas = int(sub["QT_VG_TOTAL"].sum())
        matriculas = int(sub["QT_MAT"].sum())
        docentes = int(linha["QT_DOC_TOTAL"])

        # Oferta por curso do catálogo, para os rankings por curso.
        oferta = {}
        for rotulo, g in sub.groupby("NO_CINE_ROTULO"):
            oferta[slug_do_rotulo[rotulo]] = {
                "vagas": int(g["QT_VG_TOTAL"].sum()),
                "matriculas": int(g["QT_MAT"].sum()),
                "concluintes": int(g["QT_CONC"].sum()),
                "cursos": int(g["QT_CURSO"].sum()),
            }

        cat = linha["TP_CATEGORIA_ADMINISTRATIVA"]
        saida[co] = {
            "co_ies": co,
            "nome": linha["NO_IES"],
            "sigla": linha["SG_IES"] if pd.notna(linha["SG_IES"]) else None,
            "uf_sede": linha["SG_UF_IES"],
            "municipio_sede": linha["NO_MUNICIPIO_IES"],
            "organizacao": ORGANIZACAO.get(linha["TP_ORGANIZACAO_ACADEMICA"]),
            "categoria": CATEGORIA.get(cat),
            "rede": rede(cat),
            # Corpo docente da INSTITUIÇÃO inteira — nunca rateado por curso.
            "docentes": docentes or None,
            "docentes_doutores": int(linha["QT_DOC_EX_DOUT"]) or None,
            "docentes_mestres": int(linha["QT_DOC_EX_MEST"]) or None,
            "docentes_regime_integral": int(linha["QT_DOC_EX_INT"]) or None,
            "pct_doutores": _pct(int(linha["QT_DOC_EX_DOUT"]), docentes),
            "pct_mestres": _pct(int(linha["QT_DOC_EX_MEST"]), docentes),
            "pct_regime_integral": _pct(int(linha["QT_DOC_EX_INT"]), docentes),
            "tecnicos": int(linha["QT_TEC_TOTAL"]) or None,
            # Matrículas da instituição nos cursos do catálogo sobre o corpo docente
            # TOTAL dela: é uma referência de porte, não a relação do curso.
            "alunos_por_docente": round(matriculas / docentes, 1) if docentes else None,
            "vagas": vagas,
            "vagas_presencial": int(presencial["QT_VG_TOTAL"].sum()),
            "vagas_ead": int(ead["QT_VG_TOTAL"].sum()),
            "matriculas": matriculas,
            "ingressos": int(sub["QT_ING"].sum()),
            "concluintes": int(sub["QT_CONC"].sum()),
            "n_cursos": int(sub["QT_CURSO"].sum()),
            "n_cursos_catalogo": len(oferta),
            "ufs": sorted(presencial["SG_UF"].dropna().unique().tolist()),
            "municipios": int(presencial["NO_MUNICIPIO"].dropna().nunique()),
            "oferta": oferta,
        }

    caminho = DATA / "instituicoes.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({
            "_nota": ("Corpo docente é da instituição inteira, não do curso — o Censo "
                      "não permite rateio por curso. IGC, Conceito Institucional e "
                      "recredenciamento não estão aqui: são do e-MEC, base distinta."),
            "ano_censo": ano,
            "instituicoes": dict(sorted(saida.items(),
                                        key=lambda kv: -kv[1]["matriculas"])),
        }, f, ensure_ascii=False, indent=1)

    publicas = sum(1 for i in saida.values() if i["rede"] == "Pública")
    com_docente = sum(1 for i in saida.values() if i["docentes"])
    print(f"\n[OK] {len(saida)} instituições em {caminho.name}")
    print(f"     {publicas} públicas · {len(saida) - publicas} privadas")
    print(f"     {com_docente} com corpo docente declarado "
          f"({len(saida) - com_docente} sem — ficam sem os indicadores de titulação)")


if __name__ == "__main__":
    main()
