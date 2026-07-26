"""
Fórmulas canônicas dos índices do Observatório, curso-agnósticas.

Portão de qualidade (GO gate):
    python etl/indices.py --autoteste

O autoteste valida as FÓRMULAS contra valores canônicos sintéticos — não contra
dados reais de um curso específico. Assim ele permanece válido conforme novos
cursos entram no catálogo.
"""
import argparse
import sys


def ict(vagas_capital, vagas_total, mun_oferta, mun_total):
    """Índice de Concentração Territorial ↓ melhor.
    ½·(vagas na capital / vagas totais) + ½·(1 − municípios com oferta / total)"""
    if not vagas_total or not mun_total:
        return None
    if vagas_capital is None or mun_oferta is None:
        return None
    return 0.5 * (vagas_capital / vagas_total) + 0.5 * (1 - mun_oferta / mun_total)


def equidade(valor_ict):
    """E = 1 − ICT ↑ melhor."""
    return None if valor_ict is None else 1 - valor_ict


def qualidade_normalizada(cc, enade, idd):
    """Q = média de [(x−1)/4] sobre os conceitos disponíveis (escala INEP 1–5 → 0–1)."""
    partes = [(v - 1) / 4 for v in (cc, enade, idd) if v is not None]
    return sum(partes) / len(partes) if partes else None


def iaf(cc, enade, idd, vagas_avaliadas, vagas_total, valor_ict):
    """Índice de Adequação Formativa ↑ (0–100): 100 · média(Q, V, E).
    Q = qualidade dos conceitos; V = cobertura avaliativa; E = equidade territorial."""
    if not vagas_total or valor_ict is None or vagas_avaliadas is None:
        return None
    q = qualidade_normalizada(cc, enade, idd)
    if q is None:
        return None
    v = vagas_avaliadas / vagas_total
    e = 1 - valor_ict
    return round(100 * (q + v + e) / 3, 1)


def cobertura_correlata(mun_com_servico, mun_oferta):
    """Razão entre municípios com o serviço correlato ao curso e municípios com oferta.
    Genérico: a fonte do numerador é declarada por curso em data/cursos.json
    (ex.: Farmácia Popular para Farmácia). Sem fonte declarada → None, nunca estimado."""
    if not mun_oferta or mun_com_servico is None:
        return None
    return round(mun_com_servico / mun_oferta, 1)


def hhi(vagas_por_ies):
    """Herfindahl-Hirschman ↓ mais disperso: Σ(sᵢ²) das fatias de vagas por IES."""
    total = sum(vagas_por_ies.values())
    if not total:
        return None
    return round(sum((v / total) ** 2 for v in vagas_por_ies.values()), 4)


def razao_concentracao(vagas_por_ies, n):
    """CRn ↓ mais disperso: fatia das n maiores IES."""
    total = sum(vagas_por_ies.values())
    if not total:
        return None
    maiores = sorted(vagas_por_ies.values(), reverse=True)[:n]
    return round(sum(maiores) / total, 4)


# --------------------------------------------------------------------------- #
# Portão de qualidade — valores canônicos sintéticos
# --------------------------------------------------------------------------- #

CASOS = [
    {
        "nome": "concentração alta (capital domina, poucos municípios)",
        "entrada": dict(vagas_capital=3807, vagas_total=5000, mun_oferta=20, mun_total=246,
                        cc=2.0, enade=1.84, idd=1.68, vagas_avaliadas=2500,
                        mun_com_servico=226),
        "esperado": {"ICT": 0.840, "E": 0.160, "IAF": 29.0, "cobertura": 11.3},
    },
    {
        "nome": "distribuição perfeita (nenhuma vaga na capital, oferta universal)",
        "entrada": dict(vagas_capital=0, vagas_total=1000, mun_oferta=100, mun_total=100,
                        cc=5.0, enade=5.0, idd=5.0, vagas_avaliadas=1000,
                        mun_com_servico=100),
        "esperado": {"ICT": 0.0, "E": 1.0, "IAF": 100.0, "cobertura": 1.0},
    },
    {
        "nome": "concentração total (tudo na capital, um só município)",
        "entrada": dict(vagas_capital=500, vagas_total=500, mun_oferta=1, mun_total=100,
                        cc=1.0, enade=1.0, idd=1.0, vagas_avaliadas=0,
                        mun_com_servico=0),
        "esperado": {"ICT": 0.995, "E": 0.005, "IAF": 0.2, "cobertura": 0.0},
    },
]

TOLERANCIA = 0.05


def _calcular(e):
    valor_ict = ict(e["vagas_capital"], e["vagas_total"], e["mun_oferta"], e["mun_total"])
    return {
        "ICT": round(valor_ict, 3) if valor_ict is not None else None,
        "E": round(equidade(valor_ict), 3) if valor_ict is not None else None,
        "IAF": iaf(e["cc"], e["enade"], e["idd"], e["vagas_avaliadas"], e["vagas_total"], valor_ict),
        "cobertura": cobertura_correlata(e["mun_com_servico"], e["mun_oferta"]),
    }


def autoteste():
    print("=== PORTÃO DE QUALIDADE — fórmulas canônicas ===")
    ok = True

    for caso in CASOS:
        print(f"\n[caso] {caso['nome']}")
        obtido = _calcular(caso["entrada"])
        for ind, esperado in caso["esperado"].items():
            calc = obtido[ind]
            passou = calc is not None and abs(calc - esperado) <= TOLERANCIA
            ok = ok and passou
            print(f"  {ind}: calculado={calc}  esperado={esperado}  [{'OK' if passou else 'FALHOU'}]")

    print("\n[caso] ausência de fonte deve produzir null, nunca estimativa")
    nulos = {
        "ICT sem vagas": ict(0, 0, 5, 100),
        "IAF sem conceitos": iaf(None, None, None, 100, 1000, 0.5),
        "IAF sem vagas avaliadas": iaf(3.0, 3.0, 3.0, None, 1000, 0.5),
        "cobertura sem fonte": cobertura_correlata(None, 50),
        "HHI sem vagas": hhi({}),
    }
    for rotulo, valor in nulos.items():
        passou = valor is None
        ok = ok and passou
        print(f"  {rotulo}: {valor}  [{'OK' if passou else 'FALHOU'}]")

    print("\n[caso] concentração de mercado")
    monopolio = hhi({"A": 100})
    disperso = hhi({chr(65 + i): 10 for i in range(10)})
    cr2 = razao_concentracao({"A": 50, "B": 30, "C": 20}, 2)
    for rotulo, calc, esperado in [
        ("HHI monopólio", monopolio, 1.0),
        ("HHI 10 iguais", disperso, 0.1),
        ("CR2", cr2, 0.8),
    ]:
        passou = calc is not None and abs(calc - esperado) <= 0.001
        ok = ok and passou
        print(f"  {rotulo}: calculado={calc}  esperado={esperado}  [{'OK' if passou else 'FALHOU'}]")

    if ok:
        print("\n[PASSOU] Fórmulas conferem. Pode prosseguir.")
        sys.exit(0)
    print("\n[FALHOU] Corrigir as fórmulas antes de publicar.")
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Índices do Observatório da Educação Superior")
    parser.add_argument("--autoteste", action="store_true", help="Roda o portão de qualidade")
    args = parser.parse_args()
    if args.autoteste:
        autoteste()
    else:
        parser.print_help()
