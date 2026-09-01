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
sys.path.insert(0, str(REPO / "etl"))
from referencias import MUN_TOTAL_UF  # noqa: E402

UFS_ESPERADAS = 27
MUNICIPIOS_BRASIL = 5570

# Âncoras de regressão: valores conferidos à mão na fonte. Se um refactor mexer
# na modelagem sem querer, é aqui que aparece — um número plausível porém errado
# passa despercebido em qualquer outro teste.
ANCORAS = {
    "farmacia": {"vagas_total": 417010, "ufs": 27},
    # Medicina não tem EaD: o curso é presencial por exigência regulatória, e um
    # valor não-nulo aqui denunciaria contaminação entre camadas do Censo.
    "medicina": {"vagas_ead": 0, "ufs": 27},
}

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
    # Cobertura parcial é legítima: a maioria dos rótulos CINE do Censo existe em
    # poucas UFs, e alguns numa só. O que não pode é UF inventada ou repetida.
    checar(1 <= len(ufs) <= UFS_ESPERADAS,
           f"{slug}: {len(ufs)} UFs (esperado entre 1 e {UFS_ESPERADAS})")
    desconhecidas = sorted(set(ufs) - set(MUN_TOTAL_UF))
    checar(not desconhecidas, f"{slug}: UFs fora da malha oficial: {desconhecidas}")

    # O fechamento territorial vale sobre as UFs presentes, não sobre o país
    # inteiro — só um curso ofertado nas 27 fecha em 5.570.
    soma_mun = sum(u["municipios_total"] for u in ufs.values())
    esperado = sum(MUN_TOTAL_UF[uf] for uf in ufs if uf in MUN_TOTAL_UF)
    checar(soma_mun == esperado,
           f"{slug}: soma de municípios = {soma_mun} (esperado {esperado} "
           f"para as {len(ufs)} UFs presentes)")
    if len(ufs) == UFS_ESPERADAS:
        checar(soma_mun == MUNICIPIOS_BRASIL,
               f"{slug}: curso em 27 UFs deveria somar {MUNICIPIOS_BRASIL} municípios")

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
        # O PPI é calculado sobre quem DECLAROU cor; se algum dia o denominador
        # voltar a ser o total de ingressantes, o par abaixo deixa de fechar e o
        # teste avisa antes de publicar.
        if u.get("pct_ppi") is not None and u.get("pct_cor_nao_declarada") is None:
            falhas.append(f"{ctx}: pct_ppi sem pct_cor_nao_declarada — o percentual "
                          f"perde o denominador que o torna interpretável")

        for campo in ("pct_ead", "pct_mulheres", "pct_ppi", "pct_cor_nao_declarada",
                      "pct_financiamento", "pct_noturno", "pct_rede_publica"):
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


def test_ancoras():
    """Valores conferidos na fonte — detectam regressão silenciosa de modelagem."""
    for slug, esperado in ANCORAS.items():
        dados = carregar_curso(slug)
        if not checar(dados is not None, f"âncora {slug}: nacional.json ausente"):
            continue
        ufs = dados["ufs"]
        if "ufs" in esperado:
            checar(len(ufs) == esperado["ufs"],
                   f"âncora {slug}: {len(ufs)} UFs (esperado {esperado['ufs']})")
        for campo in ("vagas_total", "vagas_ead"):
            if campo not in esperado:
                continue
            obtido = sum(u.get(campo) or 0 for u in ufs.values())
            checar(obtido == esperado[campo],
                   f"âncora {slug}: {campo} = {obtido} (esperado {esperado[campo]})")


def test_cobertura_nacional(catalogo):
    """Somados, os cursos precisam alcançar as 27 UFs — senão faltou ingestão."""
    vistas = set()
    for curso in catalogo:
        dados = carregar_curso(curso["slug"])
        if dados:
            vistas.update(dados["ufs"])
    faltando = sorted(set(MUN_TOTAL_UF) - vistas)
    checar(not faltando, f"nenhum curso tem dados nestas UFs: {faltando}")


ADITIVOS = ("vagas_total", "vagas_presencial", "vagas_ead", "matriculas",
            "matriculas_ead", "ingressos", "concluintes", "vagas_publicas")


def test_series_agregadas():
    """Série territorial e institucional, quando existem.

    A checagem central é de fechamento: o Brasil tem de ser exatamente a soma
    das 27 unidades federativas em todo campo aditivo. Se a atribuição da vaga
    de EaD à sede da mantenedora vazar — indo para o polo, ou para lugar
    nenhum — a diferença aparece aqui e em nenhum outro lugar, porque cada
    número isolado continua plausível.

    As contagens de distintos (n_ies, n_cursos, municipios_oferta) ficam de
    fora de propósito: elas NÃO devem fechar, já que a mesma universidade atua
    em vários estados. Uma soma que fechasse ali seria o sintoma do erro, não a
    prova do acerto — por isso o que se cobra delas é só que o total nacional
    não ultrapasse a soma.
    """
    caminho = REPO / "data" / "series" / "ufs.json"
    if not caminho.exists():
        return                       # camada opcional, como as demais
    series = json.loads(caminho.read_text(encoding="utf-8"))["series"]

    checar("BR" in series, "série territorial sem o recorte BR")
    ufs = [s for s in series if s != "BR"]
    checar(len(ufs) == 27, f"série territorial com {len(ufs)} UFs (esperadas 27)")

    for ano in sorted(series.get("BR", {})):
        br = series["BR"][ano]
        for campo in ADITIVOS:
            soma = sum(series[u][ano].get(campo) or 0 for u in ufs if ano in series[u])
            checar(br.get(campo) == soma,
                   f"série {ano}: BR.{campo} = {br.get(campo)} mas a soma das UFs "
                   f"dá {soma} — diferença de {(br.get(campo) or 0) - soma}")
        for campo in ("n_ies", "n_cursos", "municipios_oferta"):
            soma = sum(series[u][ano].get(campo) or 0 for u in ufs if ano in series[u])
            checar((br.get(campo) or 0) <= soma,
                   f"série {ano}: BR.{campo} = {br.get(campo)} é MAIOR que a soma "
                   f"das UFs ({soma}) — contagem de distintos não pode superá-la")

    caminho_ies = REPO / "data" / "series" / "ies.json"
    if caminho_ies.exists():
        ies = json.loads(caminho_ies.read_text(encoding="utf-8"))["series"]
        checar(len(ies) > 1000, f"série institucional com só {len(ies)} instituições")
        # Ponto sem oferta alguma não deveria existir: a linha mostraria uma
        # queda a zero que nunca aconteceu.
        vazios = [f"{co}/{ano}" for co, anos in ies.items() for ano, d in anos.items()
                  if not any(d.get(c) for c in ("vagas_total", "matriculas",
                                                "matriculas_ead"))]
        checar(not vazios,
               f"{len(vazios)} ponto(s) da série institucional sem oferta alguma: "
               f"{vazios[:3]}")


def test_perfil_municipal():
    """População do IBGE e contagem exata de instituições.

    A checagem que importa é de concordância entre dois caminhos independentes.
    `data/municipios_ies.json` lê o microdado direto; o pipeline principal
    agrega por curso e depois soma os municípios. As matrículas têm de bater
    município a município — e batem nos 1.119. Se um dia divergirem, é porque
    um dos dois passou a contar linha que o outro não conta, e o número que a
    página mostra deixou de ter uma única definição.

    Também se cobra que a contagem exata nunca seja MENOR que o piso antigo
    (`n_ies_minimo`, o maior valor entre os cursos). O piso é, por construção,
    um limite inferior: se a contagem exata ficar abaixo dele, o erro está na
    contagem, não no piso.
    """
    caminho = REPO / "data" / "municipios_ies.json"
    if not caminho.exists():
        return                       # camada opcional
    exato = json.loads(caminho.read_text(encoding="utf-8"))["municipios"]

    pop_caminho = REPO / "data" / "populacao_municipios.json"
    if pop_caminho.exists():
        pop = json.loads(pop_caminho.read_text(encoding="utf-8"))
        checar(len(pop["municipios"]) > 5000,
               f"população de só {len(pop['municipios'])} municípios "
               f"(esperados ~5.570)")
        checar(str(pop.get("ano", "")).isdigit(),
               f"população sem ano identificável: {pop.get('ano')!r}")

        # A população deve acompanhar o ano do Censo. Casados, a razão entre
        # matrículas e habitantes compara dois retratos do mesmo momento; se a
        # série do IBGE não tiver o ano (não há estimativa para 2022, por
        # exemplo), a distância fica registrada — e é isso que a página cita.
        # O que não pode é o arquivo afirmar uma distância que os próprios
        # números desmentem.
        ano = pop.get("ano")
        alvo = pop.get("ano_censo_alvo")
        defasagem = pop.get("defasagem_anos")
        if alvo is not None and ano is not None and defasagem is not None:
            esperada = abs(int(ano) - int(alvo))
            checar(defasagem == esperada,
                   f"população declara defasagem de {defasagem} ano(s), mas "
                   f"{ano} e o Censo {alvo} distam {esperada}")
            checar(defasagem <= 2,
                   f"população de {ano} contra Censo {alvo}: {defasagem} anos de "
                   f"distância é muito para uma razão por habitante")
        sem_pop = [c for c in exato if c not in pop["municipios"]]
        checar(not sem_pop,
               f"{len(sem_pop)} município(s) com oferta e sem população: "
               f"{sem_pop[:3]}")

    api = DATA / ".." / "site" / "dist" / "api" / "v1" / "municipios.json"
    api = api.resolve()
    if not api.exists():
        return                       # site ainda não gerado
    pipeline = {m["cod_ibge"]: m for m in
                json.loads(api.read_text(encoding="utf-8"))["municipios"]}

    divergentes, abaixo_do_piso = [], []
    for codigo, m in pipeline.items():
        d = exato.get(codigo)
        if not d:
            continue
        if d["matriculas"] != m["matriculas"]:
            divergentes.append(f"{m['nome']}/{m['uf']}: microdado "
                               f"{d['matriculas']} vs pipeline {m['matriculas']}")
        piso = m.get("n_ies_minimo")
        if piso is not None and d["n_ies"] < piso:
            abaixo_do_piso.append(f"{m['nome']}/{m['uf']}: exato {d['n_ies']} "
                                  f"< piso {piso}")
    checar(not divergentes,
           f"{len(divergentes)} município(s) com matrículas divergentes entre o "
           f"microdado e o pipeline: {divergentes[:3]}")
    checar(not abaixo_do_piso,
           f"{len(abaixo_do_piso)} município(s) com contagem exata abaixo do "
           f"piso — impossível por construção: {abaixo_do_piso[:3]}")


def main():
    catalogo = carregar_catalogo()
    test_catalogo_bem_formado(catalogo)
    for curso in catalogo:
        test_curso(curso)
    test_ancoras()
    test_cobertura_nacional(catalogo)
    test_series_agregadas()
    test_perfil_municipal()

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) de integridade:\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)

    print(f"[PASSOU] Integridade OK em {len(catalogo)} cursos · "
          f"{len(ANCORAS)} âncoras de regressão conferidas.")


if __name__ == "__main__":
    main()
