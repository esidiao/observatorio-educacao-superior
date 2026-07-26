"""
Testes de integridade dos dados publicados.

    python tests/test_validacao.py

Falha impede a publicação. Cobre invariantes que um erro de ETL violaria:
faixas dos índices, fechamento territorial, ausência de estimativa silenciosa
e coerência entre os cursos do catálogo.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

UFS_ESPERADAS = 27
MUNICIPIOS_BRASIL = 5570

falhas = []


def checar(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)
    return condicao


def carregar_catalogo():
    with open(DATA / "cursos.json", encoding="utf-8") as f:
        return json.load(f)["cursos"]


def carregar_curso(slug):
    caminho = DATA / "cursos" / slug / "nacional.json"
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def test_catalogo_bem_formado(catalogo):
    slugs = [c["slug"] for c in catalogo]
    checar(len(slugs) == len(set(slugs)), "slugs de curso duplicados no catálogo")
    rotulos = [c["cine_rotulo"] for c in catalogo]
    checar(len(rotulos) == len(set(rotulos)), "rótulos CINE duplicados no catálogo")
    for c in catalogo:
        for campo in ("slug", "nome", "cine_rotulo", "area_cine"):
            checar(c.get(campo), f"{c.get('slug')}: campo obrigatório '{campo}' ausente")


def test_curso(curso):
    slug = curso["slug"]
    dados = carregar_curso(slug)
    if not checar(dados is not None, f"{slug}: nacional.json ausente (rode o pipeline)"):
        return

    ufs = dados["ufs"]
    checar(len(ufs) == UFS_ESPERADAS, f"{slug}: {len(ufs)} UFs (esperado {UFS_ESPERADAS})")

    soma_mun = sum(u["municipios_total"] for u in ufs.values())
    checar(soma_mun == MUNICIPIOS_BRASIL,
           f"{slug}: soma de municípios = {soma_mun} (esperado {MUNICIPIOS_BRASIL})")

    for uf, u in ufs.items():
        ctx = f"{slug}/{uf}"

        checar(u["municipios_oferta"] + u["municipios_deserto"] == u["municipios_total"],
               f"{ctx}: oferta + desertos ≠ total de municípios")
        checar(u["municipios_oferta"] <= u["municipios_total"],
               f"{ctx}: municípios com oferta excede o total da UF")
        checar(u["vagas_presencial"] + u["vagas_ead"] == u["vagas_total"],
               f"{ctx}: presencial + EaD ≠ vagas totais")
        checar(u["vagas_capital"] <= u["vagas_presencial"],
               f"{ctx}: vagas na capital excedem as vagas presenciais")

        for campo in ("vagas_total", "vagas_presencial", "vagas_ead", "vagas_capital",
                      "municipios_oferta", "municipios_deserto", "n_ies", "matriculas"):
            valor = u.get(campo)
            checar(valor is None or valor >= 0, f"{ctx}: {campo} negativo ({valor})")

        if u.get("ICT") is not None:
            checar(0 <= u["ICT"] <= 1, f"{ctx}: ICT fora de 0–1 ({u['ICT']})")
        if u.get("E") is not None and u.get("ICT") is not None:
            checar(abs(u["E"] - (1 - u["ICT"])) < 1e-3, f"{ctx}: E ≠ 1 − ICT")
        if u.get("IAF") is not None:
            checar(0 <= u["IAF"] <= 100, f"{ctx}: IAF fora de 0–100 ({u['IAF']})")
        for campo in ("HHI", "CR2", "CR10"):
            if u.get(campo) is not None:
                checar(0 <= u[campo] <= 1, f"{ctx}: {campo} fora de 0–1 ({u[campo]})")
        if u.get("CR2") is not None and u.get("CR10") is not None:
            checar(u["CR2"] <= u["CR10"] + 1e-9, f"{ctx}: CR2 > CR10")
        for campo in ("pct_ead", "pct_mulheres", "pct_ppi", "pct_financiamento",
                      "pct_noturno", "pct_rede_publica"):
            if u.get(campo) is not None:
                checar(0 <= u[campo] <= 100, f"{ctx}: {campo} fora de 0–100 ({u[campo]})")

        # Sem fonte de qualidade, o IAF não pode existir: null é a resposta honesta.
        if u.get("ENADE") is None:
            checar(u.get("IAF") is None,
                   f"{ctx}: IAF calculado sem conceito ENADE — estimativa silenciosa")

    # A cobertura correlata só existe quando o curso declara uma fonte oficial.
    declara_cobertura = curso.get("cobertura") is not None
    tem_cobertura = any(u.get("cobertura") is not None for u in ufs.values())
    checar(declara_cobertura or not tem_cobertura,
           f"{slug}: indicador de cobertura presente sem fonte declarada em cursos.json")


def main():
    catalogo = carregar_catalogo()
    test_catalogo_bem_formado(catalogo)
    for curso in catalogo:
        test_curso(curso)

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) de integridade:\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)

    print(f"[PASSOU] Integridade OK em {len(catalogo)} cursos "
          f"({UFS_ESPERADAS} UFs, {MUNICIPIOS_BRASIL} municípios cada).")


if __name__ == "__main__":
    main()
