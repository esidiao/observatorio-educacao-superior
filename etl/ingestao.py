"""
Ingestão dos microdados do Censo da Educação Superior (INEP) — cadastro de cursos.

Lê o CSV uma única vez e agrega, para CADA curso do catálogo, os indicadores por UF
e por município.

Uso:
    python etl/ingestao.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2024.CSV \
                           --ies caminho/MICRODADOS_ED_SUP_IES_2024.CSV

Match de curso: EXATO sobre NO_CINE_ROTULO. Nunca substring — "Medicina" por
substring capturaria "Biomedicina" e "Medicina veterinária"; "Direito" capturaria
"Programas interdisciplinares abrangendo negócios, administração e direito".

Estrutura da EaD no Censo (verificada nos microdados 2024): a modalidade a distância
aparece em duas camadas distintas que NÃO podem ser somadas ingenuamente —
  · linhas de SEDE (SG_UF nulo): carregam as VAGAS autorizadas, sem UF própria;
  · linhas de POLO (SG_UF preenchido): carregam as MATRÍCULAS por município, com
    zero vagas.
Por isso as vagas EaD são atribuídas à UF-sede da mantenedora via join com o
cadastro de IES, e o alcance territorial da EaD é medido pelos polos. Os dois
números são reportados separadamente, nunca fundidos com a oferta presencial.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

from referencias import (CAPITAIS, MUN_TOTAL_UF, POPULACAO_UF, REGIAO_UF,
                         normalizar_nome, slug_municipio)
from indices import hhi, razao_concentracao

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# Colunas lidas do Censo (subconjunto — o arquivo completo tem centenas)
COLUNAS = [
    "NU_ANO_CENSO", "SG_UF", "NO_MUNICIPIO", "CO_MUNICIPIO", "IN_CAPITAL",
    "CO_IES", "CO_CURSO", "NO_CURSO", "NO_CINE_ROTULO", "TP_REDE", "TP_MODALIDADE_ENSINO",
    "QT_VG_TOTAL", "QT_VG_TOTAL_DIURNO", "QT_VG_TOTAL_NOTURNO", "QT_CURSO",
    "QT_ING", "QT_ING_FEM", "QT_ING_MASC",
    "QT_ING_PRETA", "QT_ING_PARDA", "QT_ING_INDIGENA",
    "QT_ING_BRANCA", "QT_ING_AMARELA", "QT_ING_CORND",
    "QT_ING_FIES", "QT_ING_PROUNII", "QT_ING_PROUNIP",
    "QT_MAT", "QT_CONC",
]

# TP_MODALIDADE_ENSINO: 1 = presencial, 2 = a distância
MOD_PRESENCIAL, MOD_EAD = "1", "2"
# TP_REDE: 1 = pública, 2 = privada
REDE_PUBLICA = "1"


def _int(serie):
    return pd.to_numeric(serie, errors="coerce").fillna(0).astype(int)


def _pct(parte, todo):
    """Percentual 0–100, ou None quando o denominador é zero (nunca 0 falso)."""
    if not todo:
        return None
    return round(100 * parte / todo, 1)


# Denominadores dos quais os percentuais dependem, auditados um a um contra o
# Censo 2024: sexo e turno FECHAM exatamente; cor/raça NÃO fecha, porque tem a
# categoria "não declarada" — e foi essa diferença que produziu o erro de 6,4
# pontos no pct_ppi, corrigido depois. Se uma edição futura do Censo criar
# categoria não declarada em sexo ou turno, estes contadores avisam antes de o
# número errado chegar ao site.
DISCREPANCIAS = {"sexo": 0, "turno": 0}


def agregar_uf(presencial, ead_sede, ead_polo):
    """Agrega os indicadores de uma UF de um curso.

    presencial — cursos presenciais sediados na UF (vagas + matrículas reais);
    ead_sede   — cursos EaD cuja mantenedora é sediada na UF (vagas autorizadas);
    ead_polo   — polos EaD instalados na UF (matrículas, alcance territorial).
    """
    vagas_presencial = int(presencial["QT_VG_TOTAL"].sum())
    vagas_ead = int(ead_sede["QT_VG_TOTAL"].sum())
    vagas_total = vagas_presencial + vagas_ead
    vagas_capital = int(presencial[presencial["IN_CAPITAL"] == "1"]["QT_VG_TOTAL"].sum())

    # Território presencial: só a oferta presencial ancora um município de fato.
    muns_presencial = presencial["NO_MUNICIPIO"].dropna().unique().tolist()
    mun_oferta = len(muns_presencial)

    # Alcance da EaD: municípios da UF que recebem polo.
    muns_polo = ead_polo["NO_MUNICIPIO"].dropna().unique().tolist()
    muns_polo_norm = {normalizar_nome(m) for m in muns_polo}
    muns_pres_norm = {normalizar_nome(m) for m in muns_presencial}

    ingressos = int(presencial["QT_ING"].sum())
    fem = int(presencial["QT_ING_FEM"].sum())
    if ingressos and fem + int(presencial["QT_ING_MASC"].sum()) != ingressos:
        DISCREPANCIAS["sexo"] += 1
    matriculas_presencial = int(presencial["QT_MAT"].sum())
    matriculas_ead = int(ead_polo["QT_MAT"].sum())
    concluintes = int(presencial["QT_CONC"].sum())

    # Concentração de mercado: sobre a capacidade total (presencial + EaD-sede).
    capacidade = pd.concat([presencial, ead_sede])
    vagas_por_ies = {str(ies): int(sub["QT_VG_TOTAL"].sum())
                     for ies, sub in capacidade.groupby("CO_IES")}
    vagas_por_ies = {k: v for k, v in vagas_por_ies.items() if v > 0}

    noturno = int(presencial["QT_VG_TOTAL_NOTURNO"].sum())
    if (vagas_presencial
            and int(presencial["QT_VG_TOTAL_DIURNO"].sum()) + noturno
            != vagas_presencial):
        DISCREPANCIAS["turno"] += 1

    ppi = int(presencial["QT_ING_PRETA"].sum() + presencial["QT_ING_PARDA"].sum()
              + presencial["QT_ING_INDIGENA"].sum())
    # Cor/raça tem uma quarta resposta além das categorias: não declarada. Dividir
    # o PPI pelo total de ingressantes joga quem não declarou no denominador como
    # se fosse "não PPI", e subestima. Nacionalmente são 14,4% sem declaração, e a
    # diferença entre as duas contas é de 6,4 pontos percentuais — grande demais
    # para deixar implícita. Aqui o percentual é sobre quem DECLAROU, e a fatia sem
    # declaração vai junto, para o leitor saber sobre que base está olhando.
    cor_nao_declarada = int(presencial["QT_ING_CORND"].sum())
    cor_declarada = ingressos - cor_nao_declarada
    financiamento = int(presencial["QT_ING_FIES"].sum() + presencial["QT_ING_PROUNII"].sum()
                        + presencial["QT_ING_PROUNIP"].sum())

    return {
        "vagas_total": vagas_total,
        "vagas_presencial": vagas_presencial,
        "vagas_ead": vagas_ead,
        "vagas_capital": vagas_capital,
        "pct_ead": _pct(vagas_ead, vagas_total),
        "n_cursos_presencial": int(presencial["QT_CURSO"].sum()),
        "n_cursos_ead": int(ead_sede["QT_CURSO"].sum()),
        "n_ies": len(vagas_por_ies),
        "municipios_oferta": mun_oferta,
        "ead_polos_municipios": len(muns_polo_norm),
        "ead_polos_registros": int(len(ead_polo)),
        "mun_ead_only": len(muns_polo_norm - muns_pres_norm),
        "ingressos": ingressos,
        "matriculas": matriculas_presencial,
        "matriculas_ead": matriculas_ead,
        "concluintes": concluintes,
        "taxa_conclusao": _pct(concluintes, matriculas_presencial),
        "pct_mulheres": _pct(fem, ingressos),
        "pct_ppi": _pct(ppi, cor_declarada),
        "pct_cor_nao_declarada": _pct(cor_nao_declarada, ingressos),
        "pct_financiamento": _pct(financiamento, ingressos),
        "pct_noturno": _pct(noturno, vagas_presencial),
        "pct_rede_publica": _pct(
            int(capacidade[capacidade["TP_REDE"] == REDE_PUBLICA]["QT_VG_TOTAL"].sum()),
            vagas_total),
        "HHI": hhi(vagas_por_ies),
        "CR2": razao_concentracao(vagas_por_ies, 2),
        "CR10": razao_concentracao(vagas_por_ies, 10),
        "_municipios_presencial": sorted(muns_presencial),
    }


def agregar_municipios(presencial):
    """Detalha os municípios com oferta presencial de uma UF."""
    saida = []
    for nome, sub in presencial.groupby("NO_MUNICIPIO"):
        vagas = int(sub["QT_VG_TOTAL"].sum())
        if vagas <= 0 and int(sub["QT_MAT"].sum()) <= 0:
            continue
        cods = sub["CO_MUNICIPIO"].dropna().unique().tolist()
        saida.append({
            "nome": nome,
            "slug": slug_municipio(nome),
            "cod_ibge": str(cods[0]) if cods else None,
            "vagas_total": vagas,
            "matriculas": int(sub["QT_MAT"].sum()),
            "ingressos": int(sub["QT_ING"].sum()),
            "concluintes": int(sub["QT_CONC"].sum()),
            "n_cursos": int(sub["QT_CURSO"].sum()),
            "n_ies": sub["CO_IES"].nunique(),
        })
    return sorted(saida, key=lambda m: -m["vagas_total"])


def processar_curso(sub, curso, uf_da_ies):
    """Agrega por UF as linhas já filtradas de um curso (match exato no rótulo CINE)."""
    if sub is None or sub.empty:
        print(f"  [AVISO] Nenhum registro para rótulo CINE "
              f"'{curso['cine_rotulo']}'. Curso ignorado.")
        return None, None

    presencial = sub[sub["TP_MODALIDADE_ENSINO"] == MOD_PRESENCIAL].copy()
    ead = sub[sub["TP_MODALIDADE_ENSINO"] == MOD_EAD].copy()

    # Sede EaD (sem UF na linha) → UF da mantenedora, via cadastro de IES.
    ead_sede = ead[ead["SG_UF"].isna()].copy()
    ead_sede["UF_SEDE"] = ead_sede["CO_IES"].map(uf_da_ies)
    orfas = int(ead_sede["UF_SEDE"].isna().sum())
    if orfas:
        vagas_orfas = int(ead_sede[ead_sede["UF_SEDE"].isna()]["QT_VG_TOTAL"].sum())
        print(f"  [AVISO] {orfas} linhas de sede EaD sem IES no cadastro "
              f"({vagas_orfas} vagas não atribuídas a nenhuma UF).")
    ead_polo = ead[ead["SG_UF"].notna()].copy()

    ufs, municipios = {}, {}
    for uf in sorted(MUN_TOTAL_UF):
        p = presencial[presencial["SG_UF"] == uf]
        s = ead_sede[ead_sede["UF_SEDE"] == uf]
        pl = ead_polo[ead_polo["SG_UF"] == uf]
        if p.empty and s.empty and pl.empty:
            continue

        dados = agregar_uf(p, s, pl)
        dados.pop("_municipios_presencial")
        mun_total = MUN_TOTAL_UF[uf]
        dados.update({
            "municipios_total": mun_total,
            "municipios_deserto": mun_total - dados["municipios_oferta"],
            "populacao": POPULACAO_UF[uf],
            "regiao": REGIAO_UF[uf],
            "capital": CAPITAIS[uf],
            "vagas_por_100k": round(100000 * dados["vagas_total"] / POPULACAO_UF[uf], 1),
        })
        ufs[uf] = dados
        municipios[uf] = agregar_municipios(p)

    tot = sum(u["vagas_total"] for u in ufs.values())
    pres = sum(u["vagas_presencial"] for u in ufs.values())
    ead_v = sum(u["vagas_ead"] for u in ufs.values())
    print(f"  {len(sub):>6} registros · {len(ufs)} UFs · "
          f"{tot:>7} vagas (presencial {pres} + EaD {ead_v})")
    return ufs, municipios


def main():
    parser = argparse.ArgumentParser(description="Ingestão multi-curso do Censo INEP")
    parser.add_argument("--censo", required=True, help="Caminho do MICRODADOS_CADASTRO_CURSOS_AAAA.CSV")
    parser.add_argument("--ies", required=True, help="Caminho do MICRODADOS_ED_SUP_IES_AAAA.CSV")
    parser.add_argument("--cursos", default=str(DATA / "cursos.json"))
    args = parser.parse_args()

    with open(args.cursos, encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    print(f"[INFO] Lendo cadastro de IES {args.ies} ...")
    ies = pd.read_csv(args.ies, sep=";", encoding="latin-1", dtype=str,
                      low_memory=False, usecols=["CO_IES", "SG_UF_IES"])
    uf_da_ies = dict(zip(ies["CO_IES"], ies["SG_UF_IES"]))
    print(f"[INFO] {len(uf_da_ies)} IES no cadastro.")

    print(f"[INFO] Lendo {args.censo} ...")
    df = pd.read_csv(args.censo, sep=";", encoding="latin-1", dtype=str,
                     low_memory=False, usecols=COLUNAS)
    for col in COLUNAS:
        if col.startswith("QT_"):
            df[col] = _int(df[col])
    ano_censo = str(df["NU_ANO_CENSO"].iloc[0])
    print(f"[INFO] {len(df)} linhas · Censo {ano_censo}")

    # Agrupa uma vez só: com centenas de cursos no catálogo, refiltrar o dataframe
    # inteiro por rótulo a cada volta custaria uma varredura de 720 mil linhas por curso.
    grupos = dict(list(df.groupby("NO_CINE_ROTULO")))

    for i, curso in enumerate(catalogo, 1):
        print(f"\n[CURSO {i}/{len(catalogo)}] {curso['nome']} (CINE: {curso['cine_rotulo']})")
        sub = grupos.get(curso["cine_rotulo"])
        ufs, municipios = processar_curso(sub, curso, uf_da_ies)
        if ufs is None:
            continue

        destino = DATA / "cursos" / curso["slug"]
        (destino / "municipios").mkdir(parents=True, exist_ok=True)

        # Vagas por código de curso — permite ao consolidador calcular
        # vagas_avaliadas via join com os cursos que participaram do ENADE.
        vagas_por_curso = (sub.groupby("CO_CURSO")["QT_VG_TOTAL"].sum()
                           .astype(int).to_dict())

        with open(destino / "bruto.json", "w", encoding="utf-8") as f:
            json.dump({"ano_censo": ano_censo, "ufs": ufs,
                       "vagas_por_curso": {str(k): int(v)
                                           for k, v in vagas_por_curso.items()}},
                      f, ensure_ascii=False, indent=2)
        for uf, lista in municipios.items():
            with open(destino / "municipios" / f"{uf}.json", "w", encoding="utf-8") as f:
                json.dump(lista, f, ensure_ascii=False, indent=2)

    for nome, n in DISCREPANCIAS.items():
        if n:
            print(f"[ATENÇÃO] {n} agregações em que o denominador de {nome} não "
                  f"fecha. No Censo 2024 estes fechavam exatamente — se uma edição "
                  f"nova criou categoria 'não declarado', o percentual "
                  f"correspondente precisa dividir por quem declarou, como já se "
                  f"faz com cor/raça.")

    print("\n[OK] Ingestão concluída.")


if __name__ == "__main__":
    main()
