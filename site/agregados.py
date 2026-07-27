"""
Agregação entre cursos: o observatório visto pelo território e pela instituição.

As páginas de curso respondem "onde está este curso". Faltava o contrário:
"o que existe neste estado", "o que existe neste município". Isso exige somar
através dos 353 cursos, o que o build faz enquanto já está percorrendo cada um —
acumular na passagem custa memória de um dicionário, e não uma segunda leitura
de 6 mil arquivos.

O que se pode somar e o que não se pode:

  · vagas, matrículas, ingressos e concluintes somam entre cursos sem ressalva;
  · nº de IES NÃO soma — a mesma instituição oferta vários cursos, e a soma a
    contaria uma vez por curso. Aqui se guarda o conjunto de códigos e se conta o
    conjunto no fim;
  · municípios com oferta idem: o mesmo município aparece em vários cursos;
  · índices (ICT, IAF, HHI) não são somados nem mediados entre cursos. Média de
    HHI de Medicina com HHI de Pedagogia não significa nada — são mercados
    diferentes. Ficam fora dos painéis territoriais de propósito.
"""


class Acumulador:
    """Somatórios por UF e por município, alimentados curso a curso."""

    SOMAVEIS = ("vagas_total", "vagas_presencial", "vagas_ead", "matriculas",
                "matriculas_ead", "ingressos", "concluintes")

    def __init__(self):
        self.ufs = {}
        self.municipios = {}

    # ── UF ───────────────────────────────────────────────────────────────────
    def _uf(self, sigla):
        if sigla not in self.ufs:
            self.ufs[sigla] = {
                **{c: 0 for c in self.SOMAVEIS},
                "_ies": set(),
                "_municipios": set(),
                "cursos": [],          # (slug, nome, area, vagas)
                "areas": {},
                "municipios_total": None,
                "populacao": None,
            }
        return self.ufs[sigla]

    def somar_uf(self, sigla, curso, dados, municipios, ies_codigos):
        alvo = self._uf(sigla)
        for campo in self.SOMAVEIS:
            alvo[campo] += dados.get(campo) or 0
        # Conjuntos, não somas: IES e município se repetem entre cursos.
        alvo["_ies"].update(ies_codigos)
        alvo["_municipios"].update(m["nome"] for m in municipios)
        alvo["municipios_total"] = dados.get("municipios_total")
        alvo["populacao"] = dados.get("populacao")

        if dados.get("vagas_total"):
            alvo["cursos"].append({
                "slug": curso["slug"], "nome": curso["nome"],
                "area": curso.get("area_cine"),
                "vagas": dados["vagas_total"],
                "matriculas": dados.get("matriculas") or 0,
            })
            area = curso.get("area_cine") or "Sem área declarada"
            alvo["areas"][area] = alvo["areas"].get(area, 0) + dados["vagas_total"]

    # ── Município ────────────────────────────────────────────────────────────
    def somar_municipio(self, sigla, curso, m):
        chave = (sigla, m["slug"])
        alvo = self.municipios.get(chave)
        if alvo is None:
            alvo = self.municipios[chave] = {
                "nome": m["nome"], "slug": m["slug"], "uf": sigla,
                "cod_ibge": m.get("cod_ibge"),
                "vagas_total": 0, "matriculas": 0, "ingressos": 0,
                "concluintes": 0, "n_cursos": 0,
                "_ies_max": 0, "cursos": [],
            }
        for campo in ("vagas_total", "matriculas", "ingressos", "concluintes",
                      "n_cursos"):
            alvo[campo] += m.get(campo) or 0
        # O Censo dá nº de IES por curso no município; sem os códigos, somar
        # contaria a mesma instituição várias vezes. O máximo é um piso honesto,
        # rotulado como tal na página.
        alvo["_ies_max"] = max(alvo["_ies_max"], m.get("n_ies") or 0)
        if m.get("vagas_total"):
            alvo["cursos"].append({
                "slug": curso["slug"], "nome": curso["nome"],
                "vagas": m["vagas_total"], "matriculas": m.get("matriculas") or 0,
            })

    # ── Fechamento ───────────────────────────────────────────────────────────
    def fechar(self):
        for sigla, u in self.ufs.items():
            u["n_ies"] = len(u.pop("_ies"))
            u["municipios_oferta"] = len(u.pop("_municipios"))
            if u["municipios_total"]:
                u["municipios_deserto"] = u["municipios_total"] - u["municipios_oferta"]
            u["cursos"].sort(key=lambda c: -c["vagas"])
            u["areas"] = dict(sorted(u["areas"].items(), key=lambda kv: -kv[1]))
            if u["populacao"] and u["vagas_total"]:
                u["vagas_por_100k"] = round(100000 * u["vagas_total"] / u["populacao"], 1)
            if u["vagas_total"]:
                u["pct_ead"] = round(100 * u["vagas_ead"] / u["vagas_total"], 1)

        for m in self.municipios.values():
            m["n_ies_minimo"] = m.pop("_ies_max")
            m["cursos"].sort(key=lambda c: -c["vagas"])
        return self


def rankings(instituicoes, ufs, municipios, catalogo_por_slug, limite=20):
    """Listas ordenadas — sempre com a régua explícita no título.

    Ranking sem denominador declarado é a forma mais fácil de enganar com dado
    verdadeiro: "maior universidade" muda inteiramente se a régua é matrícula,
    vaga, curso ou docente. Aqui cada lista diz por qual campo ordena.
    """
    ies = list(instituicoes.values())

    def top(itens, campo, filtro=None, chave=None):
        base = [i for i in itens if (filtro is None or filtro(i))
                and (chave or (lambda x: x.get(campo)))(i) is not None]
        base.sort(key=chave or (lambda x: -(x.get(campo) or 0)))
        return base[:limite]

    def com_docentes(minimo=50):
        # Percentual de doutores em instituição com 3 docentes é ruído, não mérito.
        return lambda i: (i.get("docentes") or 0) >= minimo

    listas = [
        {"id": "ies-matriculas", "titulo": "Instituições por matrículas",
         "nota": "Soma das matrículas nos cursos acompanhados pelo observatório.",
         "campo": "matriculas", "itens": top(ies, "matriculas"),
         "tipo": "ies", "unidade": "matrículas"},
        {"id": "ies-vagas", "titulo": "Instituições por vagas",
         "nota": "Capacidade autorizada, presencial mais EaD.",
         "campo": "vagas", "itens": top(ies, "vagas"), "tipo": "ies",
         "unidade": "vagas"},
        {"id": "ies-publicas", "titulo": "Instituições públicas por matrículas",
         "nota": "Federais, estaduais e municipais.",
         "campo": "matriculas",
         "itens": top(ies, "matriculas", lambda i: i.get("rede") == "Pública"),
         "tipo": "ies", "unidade": "matrículas"},
        {"id": "ies-privadas", "titulo": "Instituições privadas por matrículas",
         "nota": "Com e sem fins lucrativos, incluindo confessionais e comunitárias.",
         "campo": "matriculas",
         "itens": top(ies, "matriculas", lambda i: i.get("rede") == "Privada"),
         "tipo": "ies", "unidade": "matrículas"},
        {"id": "ies-doutores", "titulo": "Instituições por percentual de doutores",
         "nota": ("Corpo docente da instituição inteira. Só entram as que declaram "
                  "50 docentes ou mais — abaixo disso o percentual é ruído."),
         "campo": "pct_doutores",
         "itens": top(ies, "pct_doutores", com_docentes()), "tipo": "ies",
         "unidade": "% doutores", "casas": 1},
        {"id": "ies-territorio", "titulo": "Instituições por alcance territorial",
         "nota": "Número de municípios com oferta presencial.",
         "campo": "municipios", "itens": top(ies, "municipios"), "tipo": "ies",
         "unidade": "municípios"},
        {"id": "ies-cursos", "titulo": "Instituições por número de cursos",
         "nota": "Cursos em funcionamento entre os rótulos do catálogo.",
         "campo": "n_cursos", "itens": top(ies, "n_cursos"), "tipo": "ies",
         "unidade": "cursos"},
    ]

    lista_ufs = [{**u, "sigla": s} for s, u in ufs.items()]
    listas += [
        {"id": "uf-vagas", "titulo": "Unidades federativas por vagas",
         "nota": "Soma de todos os cursos do catálogo.",
         "campo": "vagas_total", "itens": top(lista_ufs, "vagas_total"),
         "tipo": "uf", "unidade": "vagas"},
        {"id": "uf-densidade", "titulo": "Unidades federativas por vagas / 100 mil hab.",
         "nota": "Capacidade relativa à população, não absoluta.",
         "campo": "vagas_por_100k", "itens": top(lista_ufs, "vagas_por_100k"),
         "tipo": "uf", "unidade": "vagas / 100 mil", "casas": 1},
        {"id": "uf-cobertura", "titulo": "Unidades federativas por municípios atendidos",
         "nota": "Municípios com ao menos um curso presencial.",
         "campo": "municipios_oferta", "itens": top(lista_ufs, "municipios_oferta"),
         "tipo": "uf", "unidade": "municípios"},
    ]

    lista_mun = list(municipios.values())
    listas.append(
        {"id": "mun-vagas", "titulo": "Municípios por vagas presenciais",
         "nota": "Só oferta presencial — polo EaD não é campus.",
         "campo": "vagas_total", "itens": top(lista_mun, "vagas_total"),
         "tipo": "municipio", "unidade": "vagas"})

    cursos = [{"slug": s, **c} for s, c in catalogo_por_slug.items()]
    listas.append(
        {"id": "curso-vagas", "titulo": "Cursos por vagas",
         "nota": "Rótulos CINE do Censo, presencial mais EaD.",
         "campo": "vagas_total", "itens": top(cursos, "vagas_total"),
         "tipo": "curso", "unidade": "vagas"})

    return [l for l in listas if l["itens"]]
