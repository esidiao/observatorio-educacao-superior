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
