"""
Mapas e gráficos como SVG gerado no build.

Nada de biblioteca de visualização: a Content-Security-Policy do site proíbe
recurso de terceiro, e um SVG estático imprime bem, funciona por `file://`,
não custa JavaScript e é lido por leitor de tela quando descrito. O preço é que
não há interatividade — o que este observatório compensa com tabelas ao lado de
cada figura, que continuam sendo a fonte exata.

Regras de cor herdadas do projeto:
  · escala divergente é SEMPRE RdBu, nunca RdYlGn (daltonismo);
  · "sem dados" tem cor própria e entra na legenda como categoria, jamais
    confundida com o valor mais baixo da escala.
"""
import html
import math

# Sequencial de azul único — para magnitude sem juízo de valor (vagas, matrículas).
AZUL = ["#EAF0F8", "#C9DAEE", "#A3C0E0", "#7BA3D0", "#5585BE", "#3A69A6", "#2E5496",
        "#22406F"]
# Divergente RdBu — para indicador com direção (melhor/pior).
RDBU = ["#2166AC", "#4393C3", "#92C5DE", "#D1E5F0", "#FDDBC7", "#F4A582", "#D6604D",
        "#B2182B"]
SEM_DADO = "#C9CDD2"
CONTORNO = "#FFFFFF"
TEXTO = "#1B2530"

# Recorte do Brasil continental em graus.
LON_MIN, LON_MAX = -74.1, -34.7
LAT_MIN, LAT_MAX = -33.8, 5.4
# Correção de proporção: um grau de longitude encurta com o cosseno da latitude.
# Sem isto o país aparece esticado na horizontal.
COS_LAT_MEDIA = math.cos(math.radians((LAT_MIN + LAT_MAX) / 2))


def esc(texto):
    return html.escape(str(texto), quote=True)


def _fmt(valor, casas=0):
    if valor is None:
        return "sem dados"
    if casas == 0:
        return f"{round(valor):,}".replace(",", ".")
    return f"{valor:.{casas}f}".replace(".", ",")


class Projecao:
    """Equirretangular com correção de cosseno — suficiente para mapa nacional."""

    def __init__(self, largura, altura, margem=4):
        self.margem = margem
        span_x = (LON_MAX - LON_MIN) * COS_LAT_MEDIA
        span_y = LAT_MAX - LAT_MIN
        util_x, util_y = largura - 2 * margem, altura - 2 * margem
        self.escala = min(util_x / span_x, util_y / span_y)
        # Centraliza a sobra do eixo mais folgado.
        self.dx = margem + (util_x - span_x * self.escala) / 2
        self.dy = margem + (util_y - span_y * self.escala) / 2

    def __call__(self, lon, lat):
        x = (lon - LON_MIN) * COS_LAT_MEDIA * self.escala + self.dx
        y = (LAT_MAX - lat) * self.escala + self.dy
        return x, y


def _caminho(geometria, proj):
    """Geometria GeoJSON → atributo `d` de <path>."""
    partes = []

    def anel(coords):
        pontos = []
        for lon, lat in coords:
            x, y = proj(lon, lat)
            pontos.append(f"{x:.1f},{y:.1f}")
        if pontos:
            partes.append("M" + "L".join(pontos) + "Z")

    if geometria["tipo"] == "Polygon":
        for a in geometria["coords"]:
            anel(a)
    else:  # MultiPolygon
        for poligono in geometria["coords"]:
            for a in poligono:
                anel(a)
    return "".join(partes)


def _faixas(valores, n):
    """Quebras por quantil. Com poucos valores distintos, quantil evita que uma
    UF discrepante achate todas as outras numa cor só, que é o que faz o
    intervalo igual em dado territorial brasileiro (São Paulo domina tudo)."""
    limpos = sorted(v for v in valores if v is not None)
    if not limpos:
        return []
    if len(set(limpos)) <= n:
        return sorted(set(limpos))[:-1]
    return [limpos[int(len(limpos) * (i + 1) / n)] for i in range(n - 1)]


def _cor(valor, quebras, paleta):
    if valor is None:
        return SEM_DADO
    i = 0
    for q in quebras:
        if valor > q:
            i += 1
    return paleta[min(i, len(paleta) - 1)]


def _rolavel(svg, rotulo):
    """Envolve a figura num contêiner que rola na horizontal em tela estreita.

    O viewBox tem 560 unidades de largura. Num celular de 375px a figura cabia
    inteira porque encolhia para 55% — e um rótulo de eixo de 9 unidades chegava
    ao olho com 5px, ilegível. Aqui a figura passa a ser exibida em escala 1:1 e
    quem está no celular arrasta na horizontal. Um gesto lateral é um preço
    menor do que um gráfico que não se lê.

    O contêiner recebe tabindex para que a rolagem também exista no teclado
    (WCAG 2.1.1) e um rótulo que diz o que ele contém e como operá-lo.
    """
    return (f'<div class="figura-tela" tabindex="0" role="group" '
            f'aria-label="{esc(rotulo)}. Role na horizontal para ver a figura '
            f'inteira.">{svg}</div>')


def coropletico(malha, valores, titulo, descricao, unidade="",
                divergente=False, casas=0, largura=560, altura=520,
                nomes_uf=None):
    """Mapa de UFs preenchido por valor.

    malha    — {"UF": {"tipo": ..., "coords": ...}} de data/geo/ufs.json
    valores  — {"UF": número ou None}
    """
    paleta = RDBU if divergente else AZUL
    quebras = _faixas(valores.values(), len(paleta))
    proj = Projecao(largura, altura)
    nomes_uf = nomes_uf or {}

    partes = [
        f'<svg class="mapa" viewBox="0 0 {largura} {altura}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'aria-labelledby="t-{id(valores)}" aria-describedby="d-{id(valores)}">',
        f'<title id="t-{id(valores)}">{esc(titulo)}</title>',
        f'<desc id="d-{id(valores)}">{esc(descricao)}</desc>',
    ]
    for sigla in sorted(malha):
        v = valores.get(sigla)
        rotulo = f"{nomes_uf.get(sigla, sigla)}: {_fmt(v, casas)}{unidade if v is not None else ''}"
        partes.append(
            f'<path d="{_caminho(malha[sigla], proj)}" fill="{_cor(v, quebras, paleta)}" '
            f'stroke="{CONTORNO}" stroke-width="0.6"><title>{esc(rotulo)}</title></path>')
        # Sigla no centro da UF, para leitura sem interação.
        pontos = []
        geo = malha[sigla]
        if geo["tipo"] == "Polygon":
            for a in geo["coords"]:
                pontos.extend(a)
        else:
            maior = max((a for p in geo["coords"] for a in p), key=len)
            pontos.extend(maior)
        if pontos:
            cx = sum(p[0] for p in pontos) / len(pontos)
            cy = sum(p[1] for p in pontos) / len(pontos)
            x, y = proj(cx, cy)
            claro = _cor(v, quebras, paleta) in (paleta[0], paleta[1], SEM_DADO)
            partes.append(
                f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'dominant-baseline="middle" font-size="9" font-weight="700" '
                f'fill="{TEXTO if claro else "#FFFFFF"}" aria-hidden="true" '
                f'pointer-events="none">{sigla}</text>')
    partes.append("</svg>")
    legenda = _legenda(quebras, paleta, unidade, casas,
                       tem_nulo=any(v is None for v in valores.values()))
    return _rolavel("".join(partes), titulo) + legenda


def _amostra(cor):
    """Quadradinho de cor da legenda, como SVG.

    Em vez de `style="background:..."`: estilo em atributo é o que a
    Content-Security-Policy deste site proíbe, e `fill` num SVG é atributo de
    apresentação — fora do alcance de style-src. O aria-hidden existe porque a
    cor já está dita pelo rótulo ao lado; anunciá-la de novo seria ruído.
    """
    return (f'<svg class="chave-cor" width="13" height="13" viewBox="0 0 13 13" '
            f'aria-hidden="true"><rect width="13" height="13" rx="3" '
            f'fill="{esc(cor)}"/></svg>')


def _legenda(quebras, paleta, unidade, casas, tem_nulo):
    itens = []
    for i, cor in enumerate(paleta):
        if i == 0:
            rotulo = f"até {_fmt(quebras[0], casas)}" if quebras else "todos"
        elif i - 1 < len(quebras):
            rotulo = f"{_fmt(quebras[i - 1], casas)}+"
        else:
            continue
        itens.append(f'<span class="chave">{_amostra(cor)}'
                     f'{esc(rotulo)}{esc(unidade)}</span>')
    if tem_nulo:
        # "Sem dados" é categoria, nunca o degrau mais baixo da escala.
        itens.append(f'<span class="chave">{_amostra(SEM_DADO)}'
                     f'sem dados</span>')
    return '<div class="mapa-legenda">' + "".join(itens) + "</div>"


def pontos_municipais(centroides, municipios, titulo, descricao,
                      largura=560, altura=520, contorno_ufs=None):
    """Mapa de pontos: cada município com oferta vira um círculo proporcional.

    Responde "onde existe oferta", que é a pergunta territorial do observatório.
    Área proporcional ao valor (não o raio) — raio proporcional exageraria a
    diferença ao quadrado.
    """
    proj = Projecao(largura, altura)
    valores = [m["valor"] for m in municipios if m.get("valor")]
    maior = max(valores) if valores else 1
    partes = [
        f'<svg class="mapa" viewBox="0 0 {largura} {altura}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f'<title>{esc(titulo)}</title><desc>{esc(descricao)}</desc>',
    ]
    if contorno_ufs:
        for sigla in sorted(contorno_ufs):
            partes.append(f'<path d="{_caminho(contorno_ufs[sigla], proj)}" '
                          f'fill="#F2F4F7" stroke="#D9DEE5" stroke-width="0.6"/>')
    sem_ponto = 0
    for m in sorted(municipios, key=lambda x: -(x.get("valor") or 0)):
        ponto = centroides.get(str(m.get("cod_ibge")))
        if not ponto:
            sem_ponto += 1
            continue
        x, y = proj(ponto[0], ponto[1])
        r = 1.4 + 9 * math.sqrt((m.get("valor") or 0) / maior)
        partes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#2E5496" '
            f'fill-opacity="0.55" stroke="#16304F" stroke-width="0.4">'
            f'<title>{esc(m["nome"])}: {_fmt(m.get("valor"))}</title></circle>')
    partes.append("</svg>")
    nota = ""
    if sem_ponto:
        nota = (f'<p class="mapa-nota">{sem_ponto} município(s) sem coordenada na '
                f'malha do IBGE não aparecem no mapa — os números da tabela os incluem.</p>')
    return _rolavel("".join(partes), titulo) + nota


def serie_temporal(anos, series, titulo, descricao, largura=560, altura=240,
                   casas=0):
    """Linhas ao longo dos anos. `series` = [{"nome":..., "valores": [...]}].

    Eixo Y começa em zero. Truncar a base é a forma mais comum de fazer uma
    variação modesta parecer um salto, e aqui isso seria mentir com desenho.
    """
    if not anos or not series:
        return ""
    todos = [v for s in series for v in s["valores"] if v is not None]
    if not todos:
        return ""
    topo = max(todos) * 1.08 or 1
    esq, dir_, cima, baixo = 62, 12, 14, 28
    lx, ly = largura - esq - dir_, altura - cima - baixo
    paleta = ["#2E5496", "#B07D22", "#3F6B2E", "#B23A2E", "#6B21A8"]

    def px(i):
        return esq + (lx * i / (len(anos) - 1) if len(anos) > 1 else lx / 2)

    def py(v):
        return cima + ly - (v / topo) * ly

    p = [f'<svg class="grafico" viewBox="0 0 {largura} {altura}" role="img" '
         f'xmlns="http://www.w3.org/2000/svg">',
         f'<title>{esc(titulo)}</title><desc>{esc(descricao)}</desc>']
    for i in range(4):
        v = topo * i / 3
        y = py(v)
        p.append(f'<line x1="{esq}" y1="{y:.1f}" x2="{largura - dir_}" y2="{y:.1f}" '
                 f'stroke="#E5E8EC" stroke-width="1"/>')
        p.append(f'<text x="{esq - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="11" '
                 f'fill="#6B7280">{esc(_fmt(v, casas))}</text>')
    for i, ano in enumerate(anos):
        p.append(f'<text x="{px(i):.1f}" y="{altura - 10}" text-anchor="middle" '
                 f'font-size="11" fill="#6B7280">{esc(ano)}</text>')
    for k, s in enumerate(series):
        cor = paleta[k % len(paleta)]
        # Traços só entre anos CONSECUTIVOS com dado. Uma linha única atravessando
        # um ano ausente desenharia uma tendência que ninguém mediu — e curso que
        # não existia numa edição do Censo tem ponto ausente, não zero.
        trecho = []
        for i, v in enumerate(s["valores"]):
            if v is None:
                if len(trecho) > 1:
                    p.append(f'<polyline points="{" ".join(trecho)}" fill="none" '
                             f'stroke="{cor}" stroke-width="2.5" stroke-linejoin="round"/>')
                trecho = []
                continue
            trecho.append(f"{px(i):.1f},{py(v):.1f}")
        if len(trecho) > 1:
            p.append(f'<polyline points="{" ".join(trecho)}" fill="none" '
                     f'stroke="{cor}" stroke-width="2.5" stroke-linejoin="round"/>')
        for i, v in enumerate(s["valores"]):
            if v is None:
                continue
            p.append(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="3.5" fill="{cor}">'
                     f'<title>{esc(s["nome"])} {esc(anos[i])}: {esc(_fmt(v, casas))}</title>'
                     f'</circle>')
    p.append("</svg>")
    chaves = "".join(
        f'<span class="chave">{_amostra(paleta[k % len(paleta)])}'
        f'{esc(s["nome"])}</span>' for k, s in enumerate(series))
    return (_rolavel("".join(p), titulo)
            + f'<div class="mapa-legenda">{chaves}</div>')


def barras(itens, titulo, descricao, unidade="", casas=0, largura=560,
           altura_barra=22, maximo_itens=12):
    """Barras horizontais — a forma mais legível de ranquear categorias nomeadas."""
    itens = [i for i in itens if i.get("valor") is not None][:maximo_itens]
    if not itens:
        return ""
    maior = max(i["valor"] for i in itens) or 1
    rotulo_px, valor_px = 168, 78
    largura_barra = largura - rotulo_px - valor_px - 10
    altura = len(itens) * altura_barra + 8

    p = [f'<svg class="grafico" viewBox="0 0 {largura} {altura}" role="img" '
         f'xmlns="http://www.w3.org/2000/svg">',
         f'<title>{esc(titulo)}</title><desc>{esc(descricao)}</desc>']
    for i, item in enumerate(itens):
        y = i * altura_barra + 4
        w = max(1.5, largura_barra * item["valor"] / maior)
        p.append(f'<text x="0" y="{y + altura_barra / 2 + 3:.1f}" font-size="11" '
                 f'fill="{TEXTO}">{esc(item["nome"][:30])}</text>')
        p.append(f'<rect x="{rotulo_px}" y="{y:.1f}" width="{w:.1f}" '
                 f'height="{altura_barra - 7}" fill="#2E5496" rx="2"/>')
        p.append(f'<text x="{rotulo_px + w + 6:.1f}" y="{y + altura_barra / 2 + 3:.1f}" '
                 f'font-size="11" font-weight="600" fill="{TEXTO}">'
                 f'{esc(_fmt(item["valor"], casas))}{esc(unidade)}</text>')
    p.append("</svg>")
    return _rolavel("".join(p), titulo)
