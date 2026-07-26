"""
Consolida ingestão (bruto.json) + qualidade (qualidade.json) por curso,
calcula os índices e grava data/cursos/<slug>/nacional.json.

Uso:
    python etl/consolidar.py

Relata, ao final, quais indicadores ficaram nulos e por qual fonte ausente —
transparência é parte do produto: um null explicado vale mais que um número
inventado.
"""
import argparse
import json
from datetime import date
from pathlib import Path

from indices import ict, equidade, iaf, cobertura_correlata

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# Campos de qualidade copiados diretamente para o registro da UF.
CAMPOS_QUALIDADE = [
    "CC", "ENADE", "IDD", "CPC_cont", "vagas_avaliadas",
    "cpc_org_didatico", "cpc_infraestrutura", "cpc_oportunidade",
    "pct_doc_mestres", "pct_doc_doutores", "pct_doc_regime",
    "n_cursos_avaliados", "concluintes_avaliados",
]


def consolidar_curso(curso):
    destino = DATA / "cursos" / curso["slug"]
    bruto_path = destino / "bruto.json"
    if not bruto_path.exists():
        print(f"[PULADO] {curso['nome']}: bruto.json ausente (rode etl/ingestao.py).")
        return None

    with open(bruto_path, encoding="utf-8") as f:
        bruto = json.load(f)

    qualidade = {}
    qual_path = destino / "qualidade.json"
    if qual_path.exists():
        with open(qual_path, encoding="utf-8") as f:
            qualidade = json.load(f).get("ufs", {})

    # Fonte da cobertura correlata, declarada por curso; ausente → indicador omitido.
    cobertura_cfg = curso.get("cobertura")
    cobertura_dados = {}
    if cobertura_cfg:
        cob_path = destino / "cobertura.json"
        if cob_path.exists():
            with open(cob_path, encoding="utf-8") as f:
                cobertura_dados = json.load(f).get("ufs", {})

    ufs, nulos = {}, {}
    for uf, d in bruto["ufs"].items():
        q = qualidade.get(uf, {})
        registro = dict(d)
        for campo in CAMPOS_QUALIDADE:
            registro[campo] = q.get(campo)
        if q.get("por_modalidade"):
            registro["por_modalidade"] = q["por_modalidade"]

        valor_ict = ict(d["vagas_capital"], d["vagas_presencial"],
                        d["municipios_oferta"], d["municipios_total"])
        registro["ICT"] = round(valor_ict, 4) if valor_ict is not None else None
        e = equidade(valor_ict)
        registro["E"] = round(e, 4) if e is not None else None
        # V (cobertura avaliativa) precisa comparar universos iguais: vagas_avaliadas
        # abrange cursos presenciais E EaD, então o denominador é a capacidade total.
        # Dividir por vagas_presencial produzia V > 1 e IAF acima de 100.
        registro["IAF"] = iaf(q.get("CC"), q.get("ENADE"), q.get("IDD"),
                              q.get("vagas_avaliadas"), d["vagas_total"], valor_ict)

        if cobertura_cfg:
            registro["cobertura"] = cobertura_correlata(
                cobertura_dados.get(uf, {}).get("municipios_com_servico"),
                d["municipios_oferta"])

        ufs[uf] = registro

        ausentes = []
        if registro["IAF"] is None:
            if q.get("ENADE") is None:
                ausentes.append(f"conceitos ENADE (ciclo {curso.get('enade_ano')} indisponível)")
            elif q.get("vagas_avaliadas") is None:
                ausentes.append("vagas_avaliadas (sem correspondência de código de curso)")
        if cobertura_cfg and registro.get("cobertura") is None:
            ausentes.append(f"cobertura ({cobertura_cfg['fonte']})")
        if ausentes:
            nulos[uf] = ausentes

    saida = {
        "metadados": {
            "curso": curso["nome"],
            "slug": curso["slug"],
            "cine_rotulo": curso["cine_rotulo"],
            "area_cine": curso["area_cine"],
            "versao_censo": bruto["ano_censo"],
            "ciclo_enade": curso.get("enade_ano"),
            "data_extracao": str(date.today()),
            "cobertura": cobertura_cfg,
            "fontes": {
                "censo": {
                    "nome": "Microdados do Censo da Educação Superior",
                    "orgao": "INEP/MEC",
                    "ano": int(bruto["ano_censo"]),
                    "url": "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados",
                },
                "cpc": {
                    "nome": "Conceito Preliminar de Curso / ENADE",
                    "orgao": "INEP/MEC",
                    "ano": curso.get("enade_ano"),
                } if qualidade else None,
                "populacao": {"nome": "Estimativas populacionais", "orgao": "IBGE", "ano": 2024},
            },
        },
        "ufs": ufs,
    }

    with open(destino / "nacional.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    com_iaf = sum(1 for u in ufs.values() if u["IAF"] is not None)
    print(f"[OK] {curso['nome']}: {len(ufs)} UFs · IAF calculado em {com_iaf}/{len(ufs)}")
    return nulos


def main():
    parser = argparse.ArgumentParser(description="Consolida dados e calcula índices")
    parser.add_argument("--cursos", default=str(DATA / "cursos.json"))
    args = parser.parse_args()

    with open(args.cursos, encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    relatorio = {}
    for curso in catalogo:
        nulos = consolidar_curso(curso)
        if nulos:
            relatorio[curso["nome"]] = nulos

    if relatorio:
        print("\n[TRANSPARÊNCIA] Indicadores nulos por ausência de fonte:")
        for nome, ufs in relatorio.items():
            motivos = sorted({m for lista in ufs.values() for m in lista})
            print(f"  {nome} ({len(ufs)} UFs): {'; '.join(motivos)}")


if __name__ == "__main__":
    main()
