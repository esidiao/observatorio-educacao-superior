"""
Série histórica por unidade federativa e por instituição.

Uso (uma vez por edição do Censo, normalmente via etl/baixar_censo.py):
    python etl/serie_agregada.py --censo .../MICRODADOS_CADASTRO_CURSOS_2023.CSV \
                                 --ies   .../MICRODADOS_ED_SUP_IES_2023.CSV

Produz e acumula:
    data/series/ufs.json    27 unidades federativas + Brasil, por ano
    data/series/ies.json    uma linha por instituição, por ano

Por que não derivar isto da série por curso, que já existe. Os campos aditivos
— vagas, matrículas, ingressos, concluintes — até se somariam. Mas `n_ies` e
`municipios_oferta` não: a mesma universidade oferta vinte cursos, e o mesmo
município recebe dezenas. Somar contaria cada um vinte vezes. A contagem de
distintos só é possível com as linhas na mão, e é por isso que este arquivo lê o
microdado em vez de reaproveitar o agregado.

E a série por instituição não existe em lugar nenhum: a série por curso guarda
o recorte CINE, sem CO_IES. Sem reler as edições, não há como dizer se uma
universidade cresceu ou encolheu.

As mesmas regras do resto do projeto valem aqui, e não são detalhe:

  · EaD tem duas camadas. A linha de sede tem SG_UF nulo e carrega as vagas; a
    linha de polo tem UF e vaga zero, e carrega matrícula. Contar as duas como
    se fossem a mesma coisa infla o país inteiro.
  · Vaga de EaD pertence à UF da SEDE da mantenedora, não ao polo. É o que o
    Censo registra; atribuir ao polo criaria capacidade onde não há.
  · Instituição sem vaga em nenhuma modalidade não entra na contagem de IES
    ativas daquele ano — cadastro existente não é oferta existente.

Idempotente por ano: rodar de novo para 2023 substitui 2023 e preserva o resto.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

from referencias import MUN_TOTAL_UF

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
DESTINO = DATA / "series"

COLUNAS = [
    "NU_ANO_CENSO", "SG_UF", "NO_MUNICIPIO", "CO_IES", "NO_CINE_ROTULO",
    "TP_MODALIDADE_ENSINO", "TP_REDE", "QT_VG_TOTAL", "QT_CURSO",
    "QT_ING", "QT_MAT", "QT_CONC",
]
MOD_PRESENCIAL, MOD_EAD = "1", "2"
REDE_PUBLICA = "1"

CAMPOS_UF = ["vagas_total", "vagas_presencial", "vagas_ead", "matriculas",
             "matriculas_ead", "ingressos", "concluintes", "n_ies",
             "n_cursos", "municipios_oferta", "vagas_publicas"]


def _int(serie):
    return int(serie.sum()) if len(serie) else 0


def agregar_territorio(presencial, ead_sede, ead_polo):
    """Um recorte territorial: tudo o que se oferta ali, somado."""
    capacidade = pd.concat([presencial, ead_sede])
    ies_com_oferta = {
        str(i) for i, sub in capacidade.groupby("CO_IES")
        if _int(sub["QT_VG_TOTAL"]) > 0
    }
    return {
        "vagas_total": _int(presencial["QT_VG_TOTAL"]) + _int(ead_sede["QT_VG_TOTAL"]),
        "vagas_presencial": _int(presencial["QT_VG_TOTAL"]),
        "vagas_ead": _int(ead_sede["QT_VG_TOTAL"]),
        "matriculas": _int(presencial["QT_MAT"]),
        "matriculas_ead": _int(ead_polo["QT_MAT"]),
        "ingressos": _int(presencial["QT_ING"]),
        "concluintes": _int(presencial["QT_CONC"]),
        "n_ies": len(ies_com_oferta),
        # Rótulo CINE distinto, não linha: a mesma graduação aparece uma vez por
        # município e por turno, e contá-las diria "cursos" para significar
        # "ofertas".
        "n_cursos": int(capacidade["NO_CINE_ROTULO"].nunique()),
        "municipios_oferta": int(presencial["NO_MUNICIPIO"].dropna().nunique()),
        "vagas_publicas": _int(
            capacidade[capacidade["TP_REDE"] == REDE_PUBLICA]["QT_VG_TOTAL"]),
    }


def agregar_instituicao(presencial, ead_sede, ead_polo):
    """Uma instituição: capacidade e alunos, sem as contagens de rede."""
    capacidade = pd.concat([presencial, ead_sede])
    return {
        "vagas_total": _int(presencial["QT_VG_TOTAL"]) + _int(ead_sede["QT_VG_TOTAL"]),
        "vagas_presencial": _int(presencial["QT_VG_TOTAL"]),
        "vagas_ead": _int(ead_sede["QT_VG_TOTAL"]),
        "matriculas": _int(presencial["QT_MAT"]),
        "matriculas_ead": _int(ead_polo["QT_MAT"]),
        "ingressos": _int(presencial["QT_ING"]),
        "concluintes": _int(presencial["QT_CONC"]),
        "n_cursos": int(capacidade["NO_CINE_ROTULO"].nunique()),
        "municipios_oferta": int(presencial["NO_MUNICIPIO"].dropna().nunique()),
    }


def ler(caminho_censo, caminho_ies):
    print(f"[INFO] Cadastro de IES: {caminho_ies}")
    ies = pd.read_csv(caminho_ies, sep=";", encoding="latin-1", dtype=str,
                      low_memory=False, usecols=["CO_IES", "SG_UF_IES"])
    uf_da_ies = dict(zip(ies["CO_IES"], ies["SG_UF_IES"]))

    print(f"[INFO] Lendo {caminho_censo} ...")
    df = pd.read_csv(caminho_censo, sep=";", encoding="latin-1", dtype=str,
                     low_memory=False, usecols=COLUNAS)
    for col in COLUNAS:
        if col.startswith("QT_"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df, uf_da_ies


def separar(df, uf_da_ies):
    presencial = df[df["TP_MODALIDADE_ENSINO"] == MOD_PRESENCIAL]
    ead = df[df["TP_MODALIDADE_ENSINO"] == MOD_EAD]
    ead_sede = ead[ead["SG_UF"].isna()].copy()
    ead_sede["UF_SEDE"] = ead_sede["CO_IES"].map(uf_da_ies)
    ead_polo = ead[ead["SG_UF"].notna()]
    return presencial, ead_sede, ead_polo


def acumular(caminho, ano, novos, rotulo):
    """Grava preservando os outros anos. Ano ausente do dado some da série."""
    DESTINO.mkdir(parents=True, exist_ok=True)
    anterior = {}
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            anterior = json.load(f).get("series", {})

    for chave, valores in novos.items():
        anterior.setdefault(chave, {})[ano] = valores
    # Chave que existia e sumiu nesta edição perde o ponto, não ganha zero:
    # zero significaria "existia e não ofertou nada", e a diferença importa.
    for chave in list(anterior):
        if chave not in novos:
            anterior[chave].pop(ano, None)
            if not anterior[chave]:
                del anterior[chave]

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"series": anterior}, f, ensure_ascii=False, separators=(",", ":"))
    anos = sorted({a for v in anterior.values() for a in v})
    print(f"[OK] {caminho.relative_to(REPO)} — {len(anterior)} {rotulo}, "
          f"anos {anos[0]}–{anos[-1]}")


def main():
    parser = argparse.ArgumentParser(
        description="Acumula um ano do Censo nas séries de UF e de instituição")
    parser.add_argument("--censo", required=True)
    parser.add_argument("--ies", required=True)
    args = parser.parse_args()

    df, uf_da_ies = ler(args.censo, args.ies)
    ano = str(df["NU_ANO_CENSO"].iloc[0])
    print(f"[INFO] {len(df)} linhas · Censo {ano}")

    presencial, ead_sede, ead_polo = separar(df, uf_da_ies)

    # ── Unidades federativas ─────────────────────────────────────────────────
    por_uf = {}
    for uf in sorted(MUN_TOTAL_UF):
        p = presencial[presencial["SG_UF"] == uf]
        s = ead_sede[ead_sede["UF_SEDE"] == uf]
        pl = ead_polo[ead_polo["SG_UF"] == uf]
        if p.empty and s.empty and pl.empty:
            continue
        por_uf[uf] = agregar_territorio(p, s, pl)

    # O Brasil é calculado sobre as linhas, não somando as UFs: `n_ies`,
    # `n_cursos` e `municipios_oferta` são contagens de distintos, e somá-las
    # contaria a mesma universidade uma vez por estado em que ela atua.
    por_uf["BR"] = agregar_territorio(presencial, ead_sede, ead_polo)
    acumular(DESTINO / "ufs.json", ano, por_uf, "recortes territoriais")

    # ── Instituições ─────────────────────────────────────────────────────────
    por_ies = {}
    grupos_p = dict(list(presencial.groupby("CO_IES")))
    grupos_s = dict(list(ead_sede.groupby("CO_IES")))
    grupos_pl = dict(list(ead_polo.groupby("CO_IES")))
    vazio = presencial.iloc[0:0]
    for co in sorted(set(grupos_p) | set(grupos_s) | set(grupos_pl)):
        linha = agregar_instituicao(grupos_p.get(co, vazio),
                                    grupos_s.get(co, vazio),
                                    grupos_pl.get(co, vazio))
        # Instituição cadastrada sem nenhuma oferta naquele ano não vira ponto:
        # a série mostraria uma queda a zero que nunca aconteceu.
        if any(linha[c] for c in ("vagas_total", "matriculas", "matriculas_ead")):
            por_ies[str(co)] = linha
    acumular(DESTINO / "ies.json", ano, por_ies, "instituições")


if __name__ == "__main__":
    main()
