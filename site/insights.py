"""
Leituras automáticas: frases derivadas dos números, por regra.

Cada frase aqui é calculada e escrita por template. Nenhuma é gerada por modelo
de linguagem, e a escolha é deliberada.

Um observatório cujo princípio é "nenhum indicador é estimado" não pode ter, ao
lado do número auditável, um parágrafo que ninguém consegue auditar. Texto de LLM
sobre dado quantitativo erra de formas caras: inverte o sinal de uma variação,
arredonda para um número que não está na tabela, e — o pior — atribui causa
("devido à expansão da EaD") onde o dado só mostra correlação temporal. Uma vez
publicado, esse parágrafo tem a mesma aparência de autoridade que o resto do site.

Então as regras aqui são estritas:
  · só afirma o que foi calculado, com o número à vista;
  · descreve variação, participação e posição — nunca causa;
  · exige mínimo de material (série com dois pontos, base não trivial) e cala
    quando não tem;
  · qualquer frase pode ser conferida contra a tabela da mesma página.

Isso entrega o que interessa da "camada analítica" (o leitor não precisa fazer a
conta de cabeça) sem comprar o risco que a torna perigosa.
"""

REGIOES_ORDEM = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]


def _milhar(v):
    return f"{round(v):,}".replace(",", ".")


def _pct(v, casas=1):
    return f"{v:.{casas}f}".replace(".", ",") + "%"


def _variacao(antes, depois):
    """Variação percentual, ou None quando a base não sustenta a conta.

    Base pequena produz variação espetacular e vazia: 2 vagas viram 6 e o texto
    anuncia "crescimento de 200%". O piso de 100 corta esse tipo de manchete.
    """
    if not antes or antes < 100 or depois is None:
        return None
    return 100 * (depois - antes) / antes


def _frase(texto, tipo="neutro"):
    return {"texto": texto, "tipo": tipo}


def do_curso(nome, total, ufs, serie=None, top_ies=None):
    """Leituras da página de um curso."""
    frases = []

    # ── Série histórica ──────────────────────────────────────────────────────
    if serie and len(serie.get("anos", {})) >= 2:
        anos = sorted(serie["anos"])
        primeiro, ultimo = anos[0], anos[-1]
        a = serie["anos"][primeiro]["BR"]
        b = serie["anos"][ultimo]["BR"]

        var_vagas = _variacao(a.get("vagas_total"), b.get("vagas_total"))
        var_mat = _variacao(a.get("matriculas"), b.get("matriculas"))

        if var_vagas is not None:
            verbo = "cresceram" if var_vagas > 0 else "recuaram"
            frase = (f"Entre {primeiro} e {ultimo}, as vagas de {nome} {verbo} "
                     f"{_pct(abs(var_vagas))}, de {_milhar(a['vagas_total'])} para "
                     f"{_milhar(b['vagas_total'])}.")
            # O contraste entre capacidade e ocupação é a leitura mais útil aqui,
            # e é onde a conta de cabeça mais engana.
            if var_mat is not None and (var_vagas > 0) != (var_mat > 0):
                verbo_m = "subiram" if var_mat > 0 else "caíram"
                frase += (f" No mesmo período as matrículas presenciais {verbo_m} "
                          f"{_pct(abs(var_mat))} — capacidade e ocupação andaram em "
                          f"sentidos opostos.")
            frases.append(_frase(frase, "atencao" if var_vagas > 15 else "neutro"))

        ead_antes, ead_depois = a.get("vagas_ead") or 0, b.get("vagas_ead") or 0
        var_ead = _variacao(ead_antes, ead_depois)
        if var_ead is not None and abs(var_ead) >= 5:
            verbo = "avançou" if var_ead > 0 else "recuou"
            frases.append(_frase(
                f"A capacidade a distância {verbo} {_pct(abs(var_ead))} de "
                f"{primeiro} para {ultimo}."))
        elif not ead_antes and ead_depois >= 1000:
            # Partir do zero não tem variação percentual — tem uma data de início.
            # Dizer "cresceu 28.600%" seria pior que não dizer nada; dizer que não
            # existia e passou a existir é o fato, e costuma ser o mais importante
            # da série inteira.
            estreia = next((ano for ano in anos
                            if (serie["anos"][ano]["BR"].get("vagas_ead") or 0) > 0), None)
            frases.append(_frase(
                f"Não havia oferta a distância de {nome} em {primeiro}"
                + (f"; ela aparece em {estreia} " if estreia else "; ")
                + f"e chega a {_milhar(ead_depois)} vagas em {ultimo}.", "atencao"))

    # ── Modalidade ───────────────────────────────────────────────────────────
    pct_ead = total.get("pct_ead")
    if pct_ead is not None:
        if pct_ead >= 50:
            frases.append(_frase(
                f"A maior parte da capacidade de {nome} já é a distância: "
                f"{_pct(pct_ead)} das vagas.", "atencao"))
        elif pct_ead <= 1:
            frases.append(_frase(
                f"{nome} é praticamente só presencial — a EaD responde por "
                f"{_pct(pct_ead)} das vagas."))

    # ── Território ───────────────────────────────────────────────────────────
    mun = total.get("municipios_oferta")
    if mun:
        frases.append(_frase(
            f"A oferta presencial existe em {_milhar(mun)} dos 5.570 municípios "
            f"brasileiros ({_pct(100 * mun / 5570)} do território municipal)."))

    # Concentração entre UFs: quantas concentram metade da capacidade.
    capacidades = sorted((u.get("vagas_total") or 0 for u in ufs.values()),
                         reverse=True)
    soma = sum(capacidades)
    if soma and len(capacidades) >= 5:
        acumulado = 0
        n = 0
        for v in capacidades:
            acumulado += v
            n += 1
            if acumulado >= soma / 2:
                break
        if n <= 4:
            frases.append(_frase(
                f"{n} unidade{'s' if n > 1 else ''} federativa{'s' if n > 1 else ''} "
                f"concentra{'m' if n > 1 else ''} metade de toda a capacidade do curso.",
                "atencao"))

    # ── Mercado ──────────────────────────────────────────────────────────────
    cr2 = total.get("CR2")
    if cr2 is not None and cr2 >= 0.3:
        frases.append(_frase(
            f"As duas maiores instituições respondem por {_pct(cr2 * 100)} da "
            f"capacidade nacional do curso.", "atencao"))

    if top_ies:
        maior = top_ies[0]
        frases.append(_frase(
            f"A instituição com mais matrículas em {nome} é {maior['nome']} "
            f"({_milhar(maior['matriculas'])} matrículas)."))

    # ── Qualidade ────────────────────────────────────────────────────────────
    if total.get("ENADE") is None:
        frases.append(_frase(
            f"Não há indicadores de qualidade para {nome}: o ENADE é trienal e "
            f"reveza as áreas avaliadas, e este curso está fora do ciclo publicado. "
            f"Nenhum conceito é estimado para preencher a lacuna.", "sem-dado"))

    return frases


def do_brasil(painel, serie_brasil, fluxo_brasil):
    """Leituras do painel executivo nacional."""
    frases = []
    anos = sorted(serie_brasil)

    if len(anos) >= 2:
        a, b = serie_brasil[anos[0]], serie_brasil[anos[-1]]
        var_ead = _variacao(a["vagas_ead"], b["vagas_ead"])
        var_pres = _variacao(a["vagas_presencial"], b["vagas_presencial"])
        if var_ead is not None and var_pres is not None:
            frases.append(_frase(
                f"Entre {anos[0]} e {anos[-1]}, a capacidade a distância passou de "
                f"{_milhar(a['vagas_ead'])} para {_milhar(b['vagas_ead'])} vagas "
                f"({_pct(abs(var_ead))} de {'alta' if var_ead > 0 else 'queda'}), "
                f"enquanto a presencial foi de {_milhar(a['vagas_presencial'])} para "
                f"{_milhar(b['vagas_presencial'])} "
                f"({_pct(abs(var_pres))} de {'alta' if var_pres > 0 else 'queda'}).",
                "atencao"))

    if fluxo_brasil:
        coortes = sorted(fluxo_brasil)
        com_evasao = [c for c in coortes if fluxo_brasil[c].get("evasao") is not None]
        if len(com_evasao) >= 2:
            antes = fluxo_brasil[com_evasao[0]]["evasao"]
            agora = fluxo_brasil[com_evasao[-1]]["evasao"]
            pontos = f"{abs(agora - antes):.1f}".replace(".", ",")
            frases.append(_frase(
                f"A evasão nacional foi de {_pct(antes)} na coorte {com_evasao[0]} "
                f"para {_pct(agora)} na coorte {com_evasao[-1]} — "
                f"{'alta' if agora > antes else 'queda'} de {pontos} pontos "
                f"percentuais.", "atencao" if agora > antes else "neutro"))
        com_conc = [c for c in coortes if fluxo_brasil[c].get("conclusao") is not None]
        if len(com_conc) >= 2:
            antes = fluxo_brasil[com_conc[0]]["conclusao"]
            agora = fluxo_brasil[com_conc[-1]]["conclusao"]
            if abs(agora - antes) >= 1:
                pontos = f"{abs(agora - antes):.1f}".replace(".", ",")
                frases.append(_frase(
                    f"A conclusão passou de {_pct(antes)} para {_pct(agora)} entre as "
                    f"coortes {com_conc[0]} e {com_conc[-1]}, "
                    f"{'ganho' if agora > antes else 'perda'} de {pontos} pontos."))

    if painel.get("municipios"):
        frases.append(_frase(
            f"A oferta presencial existe em {_milhar(painel['municipios'])} dos 5.570 "
            f"municípios — {_pct(100 * painel['municipios'] / 5570)} do território "
            f"municipal concentra toda a graduação presencial acompanhada aqui."))

    if painel.get("ies") and painel.get("ies_com_pos"):
        frases.append(_frase(
            f"Das {_milhar(painel['ies'])} instituições acompanhadas, "
            f"{_milhar(painel['ies_com_pos'])} mantêm pós-graduação stricto sensu "
            f"e {_milhar(painel.get('ies_com_igc') or 0)} têm IGC publicado."))
    return frases


def do_acesso(painel, maior_mul, menor_mul, maior_ppi, menor_ppi, perfil_uf):
    """Leituras da página de acesso e equidade."""
    frases = []

    if painel.get("pct_mulheres") is not None:
        frases.append(_frase(
            f"{_pct(painel['pct_mulheres'])} dos ingressantes presenciais são "
            f"mulheres. A média nacional esconde extremos: {maior_mul[0]['nome']} "
            f"tem {_pct(maior_mul[0]['pct_mulheres'])} e {menor_mul[0]['nome']}, "
            f"{_pct(menor_mul[0]['pct_mulheres'])}."
            if maior_mul and menor_mul else
            f"{_pct(painel['pct_mulheres'])} dos ingressantes presenciais são mulheres."))

    if painel.get("pct_ppi") is not None and painel.get("pct_cor_nao_declarada") is not None:
        frases.append(_frase(
            f"{_pct(painel['pct_ppi'])} dos ingressantes que declararam cor são "
            f"pretos, pardos ou indígenas. {_pct(painel['pct_cor_nao_declarada'])} "
            f"não declararam — quanto maior essa fatia, menos firme é o número "
            f"anterior.", "atencao"))

    if maior_ppi and menor_ppi:
        frases.append(_frase(
            f"Entre os cursos grandes, {maior_ppi[0]['nome']} tem "
            f"{_pct(maior_ppi[0]['pct_ppi'])} de ingressantes pretos, pardos e "
            f"indígenas e {menor_ppi[0]['nome']}, {_pct(menor_ppi[0]['pct_ppi'])}.",
            "atencao"))

    if painel.get("pct_financiamento") is not None:
        frases.append(_frase(
            f"{_pct(painel['pct_financiamento'])} dos ingressantes entraram com FIES "
            f"ou PROUNI. O número cobre só a oferta presencial."))

    if perfil_uf:
        nd = {s: a["nd"] for s, a in perfil_uf.items() if a.get("nd") is not None}
        if len(nd) >= 2:
            pior = max(nd, key=nd.get)
            melhor = min(nd, key=nd.get)
            frases.append(_frase(
                f"A não-declaração de cor varia de {_pct(nd[melhor])} em {melhor} a "
                f"{_pct(nd[pior])} em {pior}. É diferença de preenchimento do Censo, "
                f"não de perfil da população — e limita a comparação entre estados.",
                "sem-dado"))
    return frases


def das_redes(comparativo, serie_brasil, anos, categorias):
    """Leituras da página de redes."""
    frases = []
    por_rotulo = {l["rotulo"]: l for l in comparativo}

    mat = por_rotulo.get("Matrículas")
    ies = por_rotulo.get("Instituições")
    if mat and mat.get("pct") is not None and ies and ies.get("pct") is not None:
        frases.append(_frase(
            f"A rede pública é {_pct(ies['pct'])} das instituições e responde por "
            f"{_pct(mat['pct'])} das matrículas nos cursos acompanhados.",
            "atencao"))

    ead = por_rotulo.get("Vagas a distância")
    pres = por_rotulo.get("Vagas presenciais")
    if ead and pres and ead.get("pct") is not None and pres.get("pct") is not None:
        frases.append(_frase(
            f"Na oferta presencial a participação pública é {_pct(pres['pct'])}; "
            f"na oferta a distância, {_pct(ead['pct'])}. A expansão da EaD é um "
            f"fenômeno da rede privada."))

    if len(anos) >= 2:
        a, b = serie_brasil[anos[0]], serie_brasil[anos[-1]]
        pub_a, pub_b = a.get("vagas_publicas") or 0, b.get("vagas_publicas") or 0
        priv_a = (a.get("vagas_total") or 0) - pub_a
        priv_b = (b.get("vagas_total") or 0) - pub_b
        var_pub = _variacao(pub_a, pub_b)
        var_priv = _variacao(priv_a, priv_b)
        if var_pub is not None and var_priv is not None:
            frases.append(_frase(
                f"Entre {anos[0]} e {anos[-1]}, a capacidade da rede pública "
                f"{'cresceu' if var_pub > 0 else 'recuou'} {_pct(abs(var_pub))} e a da "
                f"privada {'cresceu' if var_priv > 0 else 'recuou'} {_pct(abs(var_priv))}.",
                "atencao" if abs(var_priv - var_pub) > 20 else "neutro"))
        if a.get("vagas_total") and b.get("vagas_total"):
            antes = 100 * pub_a / a["vagas_total"]
            agora = 100 * pub_b / b["vagas_total"]
            if abs(antes - agora) >= 0.5:
                pontos = f"{abs(antes - agora):.1f}".replace(".", ",")
                frases.append(_frase(
                    f"A fatia pública da capacidade passou de {_pct(antes)} para "
                    f"{_pct(agora)} — {'perda' if agora < antes else 'ganho'} de "
                    f"{pontos} pontos percentuais."))

    dout = por_rotulo.get("% Doutores (média entre IES)")
    if dout and dout.get("publica") is not None and dout.get("privada") is not None:
        frases.append(_frase(
            f"Na média entre instituições, {_pct(dout['publica'])} do corpo docente "
            f"da rede pública tem doutorado, contra {_pct(dout['privada'])} da "
            f"privada. Média simples, não ponderada por tamanho."))

    pos = por_rotulo.get("Instituições com pós stricto sensu")
    if pos and pos.get("publica") is not None and ies:
        if ies.get("publica"):
            taxa_pub = 100 * pos["publica"] / ies["publica"]
            taxa_priv = (100 * pos["privada"] / ies["privada"]) if ies.get("privada") else None
            if taxa_priv is not None:
                frases.append(_frase(
                    f"{_pct(taxa_pub)} das instituições públicas mantêm pós-graduação "
                    f"stricto sensu, contra {_pct(taxa_priv)} das privadas."))
    return frases


def das_regioes(regioes, fluxo_regioes):
    """Leituras da página regional — onde a desigualdade territorial aparece."""
    frases = []
    if not regioes:
        return frases

    # Densidade medida sobre a oferta PRESENCIAL. A capacidade total inclui vagas
    # EaD registradas na sede da mantenedora — o Sul aparece com 16 mil vagas por
    # 100 mil habitantes não porque forme mais gente, mas porque abriga
    # mantenedoras de ensino a distância. Para falar de acesso local, presencial é
    # a única régua honesta.
    com_densidade = [r for r in regioes if r.get("presencial_por_100k")]
    if len(com_densidade) >= 2:
        maior = max(com_densidade, key=lambda r: r["presencial_por_100k"])
        menor = min(com_densidade, key=lambda r: r["presencial_por_100k"])
        razao = maior["presencial_por_100k"] / menor["presencial_por_100k"]
        frases.append(_frase(
            f"Em oferta presencial, {maior['nome']} tem "
            f"{_milhar(maior['presencial_por_100k'])} vagas por 100 mil habitantes "
            f"contra {_milhar(menor['presencial_por_100k'])} do {menor['nome']} — "
            f"{_pct(razao, 1).rstrip('%')} vezes mais. A capacidade total distorce "
            f"essa comparação, porque a vaga EaD é contada na sede da mantenedora.",
            "atencao" if razao >= 1.5 else "neutro"))

    com_cobertura = [r for r in regioes if r.get("pct_cobertura") is not None]
    if len(com_cobertura) >= 2:
        maior = max(com_cobertura, key=lambda r: r["pct_cobertura"])
        menor = min(com_cobertura, key=lambda r: r["pct_cobertura"])
        frases.append(_frase(
            f"A oferta presencial alcança {_pct(maior['pct_cobertura'])} dos municípios "
            f"do {maior['nome']} e {_pct(menor['pct_cobertura'])} dos do {menor['nome']}.",
            "atencao"))

    total = sum(r["vagas_total"] for r in regioes)
    if total:
        maior = max(regioes, key=lambda r: r["vagas_total"])
        frases.append(_frase(
            f"{maior['nome']} concentra {_pct(100 * maior['vagas_total'] / total)} de "
            f"toda a capacidade do país. Boa parte é vaga a distância registrada na "
            f"sede da mantenedora, que fica onde a empresa é, não onde o estudante está."))

    if fluxo_regioes:
        ultimos = {}
        primeiros = {}
        for nome, v in fluxo_regioes.items():
            cs = sorted(c for c in v if (v[c].get("evasao") or {}).get("total") is not None)
            if cs:
                primeiros[nome] = v[cs[0]]["evasao"]["total"]
                ultimos[nome] = v[cs[-1]]["evasao"]["total"]
        if len(ultimos) >= 2:
            pior = max(ultimos, key=ultimos.get)
            melhor = min(ultimos, key=ultimos.get)
            frases.append(_frase(
                f"Na última coorte, a evasão vai de {_pct(ultimos[melhor])} no "
                f"{melhor} a {_pct(ultimos[pior])} no {pior}.", "atencao"))
            # Convergência: a distância entre extremos encolheu, mas para pior.
            antes = max(primeiros.values()) - min(primeiros.values())
            agora = max(ultimos.values()) - min(ultimos.values())
            # Meio ponto de diferença: abaixo disso a "convergência" é ruído de
            # arredondamento, e a frase sairia dizendo "caiu de 2,7 para 2,7".
            if abs(antes - agora) >= 0.5:
                verbo = "encolheu" if antes > agora else "aumentou"
                fecho = (" — as regiões convergiram, mas todas pioraram."
                         if antes > agora else " — a desigualdade regional cresceu.")
                frases.append(_frase(
                    f"A distância entre a região de maior e a de menor evasão {verbo} "
                    f"de {_pct(antes).rstrip('%')} para {_pct(agora).rstrip('%')} "
                    f"pontos" + fecho))
    return frases


def da_uf(nome_uf, resumo, serie_uf=None):
    """Leituras do painel de uma unidade federativa."""
    frases = []

    if resumo.get("municipios_oferta") is not None and resumo.get("municipios_total"):
        cobertos = resumo["municipios_oferta"]
        total_mun = resumo["municipios_total"]
        desertos = total_mun - cobertos
        frases.append(_frase(
            f"{nome_uf} tem oferta presencial de ensino superior em {_milhar(cobertos)} "
            f"dos {_milhar(total_mun)} municípios; {_milhar(desertos)} não têm nenhum "
            f"curso presencial dos que este observatório acompanha.",
            "atencao" if desertos > cobertos else "neutro"))

    pct_pub = resumo.get("pct_rede_publica")
    if pct_pub is not None:
        lado = "pública" if pct_pub >= 50 else "privada"
        valor = pct_pub if pct_pub >= 50 else 100 - pct_pub
        frases.append(_frase(
            f"A rede {lado} concentra {_pct(valor)} da capacidade instalada no estado."))

    if resumo.get("vagas_por_100k") is not None:
        frases.append(_frase(
            f"São {_milhar(resumo['vagas_por_100k'])} vagas por 100 mil habitantes."))

    if serie_uf and len(serie_uf) >= 2:
        anos = sorted(serie_uf)
        var = _variacao(serie_uf[anos[0]].get("vagas_total"),
                        serie_uf[anos[-1]].get("vagas_total"))
        if var is not None:
            verbo = "cresceu" if var > 0 else "recuou"
            frases.append(_frase(
                f"De {anos[0]} a {anos[-1]}, a capacidade total do estado {verbo} "
                f"{_pct(abs(var))}."))

    return frases


def do_fluxo(nome_uf, fluxo_uf):
    """Leituras das taxas de coorte — os únicos números do observatório que
    acompanham as mesmas pessoas ao longo do tempo."""
    frases = []
    if not fluxo_uf:
        return frases
    coortes = sorted(fluxo_uf)

    com_evasao = [c for c in coortes if fluxo_uf[c].get("evasao", {}).get("total") is not None]
    if com_evasao:
        ultimo = com_evasao[-1]
        atual = fluxo_uf[ultimo]["evasao"]["total"]
        frase = (f"Na coorte {ultimo}, {_pct(atual)} dos ingressantes em "
                 f"{nome_uf} evadiram. Diferente das demais taxas do site, esta "
                 f"acompanha as mesmas pessoas ao longo do tempo.")
        if len(com_evasao) >= 2:
            primeiro = com_evasao[0]
            antes = fluxo_uf[primeiro]["evasao"]["total"]
            if antes:
                delta = atual - antes
                if abs(delta) >= 1:
                    verbo = "subiu" if delta > 0 else "caiu"
                    # Diferença entre dois percentuais é medida em PONTOS, não em
                    # percentual: "subiu 7,9%" sobre 11,7% seria 12,6%, outro número.
                    pontos = f"{abs(delta):.1f}".replace(".", ",")
                    frase += (f" Em {primeiro} era {_pct(antes)} — {verbo} "
                              f"{pontos} pontos percentuais.")
        frases.append(_frase(frase, "atencao" if atual >= 20 else "neutro"))

        # Recorte por sexo, quando a diferença é grande o bastante para não ser ruído.
        reg = fluxo_uf[ultimo]["evasao"]
        f_, m = reg.get("feminino"), reg.get("masculino")
        if f_ is not None and m is not None and abs(m - f_) >= 2:
            maior, menor = ("homens", "mulheres") if m > f_ else ("mulheres", "homens")
            frases.append(_frase(
                f"A evasão é maior entre {maior} ({_pct(max(m, f_))}) do que entre "
                f"{menor} ({_pct(min(m, f_))}) na coorte {ultimo}."))

    com_conclusao = [c for c in coortes
                     if fluxo_uf[c].get("conclusao", {}).get("total") is not None]
    if com_conclusao:
        ultimo = com_conclusao[-1]
        frases.append(_frase(
            f"A taxa de conclusão da coorte {ultimo} é "
            f"{_pct(fluxo_uf[ultimo]['conclusao']['total'])}."))
    return frases


def do_municipio(nome, uf, dados, posicao=None, total_uf=None):
    """Leituras da página de um município."""
    frases = []
    if dados.get("vagas_total"):
        frase = (f"{nome} concentra {_milhar(dados['vagas_total'])} vagas presenciais "
                 f"em {dados.get('n_ies', 0)} instituição(ões).")
        if posicao and total_uf:
            frase += (f" É o {posicao}º município de {uf} em capacidade, entre "
                      f"{total_uf} com oferta.")
        frases.append(_frase(frase))
    if dados.get("concluintes") and dados.get("matriculas"):
        frases.append(_frase(
            f"São {_milhar(dados['matriculas'])} matrículas e "
            f"{_milhar(dados['concluintes'])} concluintes no ano do Censo. A razão "
            f"entre os dois é um retrato pontual, não o acompanhamento de uma turma."))
    return frases


def da_instituicao(ies):
    """Leituras do painel de uma instituição."""
    frases = []
    frases.append(_frase(
        f"{ies['nome']} é uma {ies.get('organizacao') or 'instituição'} "
        f"{ies.get('categoria', '').lower() or ''}".strip() +
        f", sediada em {ies.get('municipio_sede')} ({ies.get('uf_sede')})."))

    if ies.get("igc_continuo") is not None:
        faixa = ies.get("igc_faixa")
        frase = f"IGC contínuo de {ies['igc_continuo']:.2f}".replace(".", ",")
        if faixa:
            frase += f", faixa {faixa} de 5"
        if ies.get("cursos_com_cpc"):
            frase += f", calculado sobre {ies['cursos_com_cpc']} curso(s) com CPC no triênio"
        frases.append(_frase(frase + ". É índice da instituição inteira, não de um curso."))
    else:
        frases.append(_frase(
            "Sem IGC publicado: nenhum curso desta instituição foi avaliado no "
            "triênio do ENADE. É ausência de avaliação, não avaliação ruim.",
            "sem-dado"))

    if ies.get("pos_programas"):
        graus = ies.get("pos_por_grau") or {}
        doutorado = sum(n for g, n in graus.items() if "DOUTORADO" in g.upper())
        frase = (f"Mantém {ies['pos_programas']} programa(s) de pós-graduação "
                 f"stricto sensu")
        if doutorado:
            frase += f", {doutorado} deles com doutorado"
        if ies.get("pos_conceito_medio"):
            media = f"{ies['pos_conceito_medio']:.2f}".replace(".", ",")
            frase += (f". O conceito CAPES médio é {media}, numa escala de 1 a 7 "
                      f"que não se compara ao IGC")
        frases.append(_frase(frase + "."))

    if ies.get("pct_doutores") is not None:
        frases.append(_frase(
            f"{_pct(ies['pct_doutores'])} do corpo docente tem doutorado e "
            f"{_pct(ies.get('pct_regime_integral') or 0)} está em regime integral. "
            f"Os percentuais são da instituição inteira, não de um curso específico."))

    if ies.get("vagas") and ies.get("vagas_ead") is not None and ies["vagas"]:
        pct = 100 * ies["vagas_ead"] / ies["vagas"]
        if pct >= 50:
            frases.append(_frase(
                f"{_pct(pct)} da capacidade da instituição nos cursos acompanhados "
                f"é a distância.", "atencao"))

    if len(ies.get("ufs") or []) >= 5:
        frases.append(_frase(
            f"Tem oferta presencial em {len(ies['ufs'])} unidades federativas e "
            f"{ies.get('municipios', 0)} municípios."))
    return frases
