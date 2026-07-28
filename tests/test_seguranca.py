"""
Portão de segurança, acessibilidade e privacidade dos templates.

    python tests/test_seguranca.py

Cada checagem aqui nasceu de um problema real encontrado em auditoria. São
invariantes fáceis de quebrar sem perceber — um `onclick=` conveniente, um
recurso externo "só para testar", um `select_autoescape` que parece proteger e
não protege. O teste existe para que a regressão apareça no build, não em
produção.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
TEMPLATES = REPO / "site" / "templates"
STATIC = REPO / "site" / "static"
BUILD = REPO / "site" / "build.py"

falhas = []


def checar(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


def test_autoescape():
    """select_autoescape casa pelo SUFIXO do arquivo.

    Todo template aqui termina em ".j2". Uma lista como ("html", "xml") deixa o
    escape DESLIGADO em 100% das páginas, e o build parece protegido sem estar.
    """
    codigo = BUILD.read_text(encoding="utf-8")
    bloco = re.search(r"select_autoescape\((.*?)\)\)", codigo, re.S)
    checar(bloco is not None, "select_autoescape não localizado em site/build.py")
    if bloco:
        checar('"j2"' in bloco.group(1) or "'j2'" in bloco.group(1),
               "select_autoescape não inclui 'j2' — o escape fica desligado em "
               "todos os templates, que terminam em .j2")


def test_sem_handlers_inline():
    """Handler no markup exigiria 'unsafe-inline' em script-src."""
    padrao = re.compile(r"\son(click|input|change|submit|focus|blur|keydown|keyup|"
                        r"load|error|mouseover)\s*=", re.I)
    for arq in sorted(TEMPLATES.glob("*.j2")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                falhas.append(f"{arq.name}:{n}: handler inline — use addEventListener "
                              f"em site/static/js/")
    for arq in sorted(STATIC.glob("js/*.js")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                falhas.append(f"static/js/{arq.name}:{n}: handler inline gerado em "
                              f"string HTML — a CSP bloqueia")


def test_csp():
    base = (TEMPLATES / "base.html.j2").read_text(encoding="utf-8")
    csp = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', base)
    checar(csp is not None, "base.html.j2 sem Content-Security-Policy")
    if not csp:
        return
    politica = csp.group(1)
    diretivas = {}
    for parte in politica.split(";"):
        parte = parte.strip()
        if parte:
            nome, _, valor = parte.partition(" ")
            diretivas[nome] = valor

    checar("'unsafe-inline'" not in diretivas.get("script-src", ""),
           "script-src permite 'unsafe-inline' — todo JS deve viver em arquivo")
    checar("'unsafe-eval'" not in diretivas.get("script-src", ""),
           "script-src permite 'unsafe-eval'")
    for obrigatoria in ("default-src", "object-src", "base-uri", "frame-ancestors",
                        "form-action"):
        checar(obrigatoria in diretivas, f"CSP sem a diretiva {obrigatoria}")
    checar(diretivas.get("frame-ancestors") == "'none'",
           "frame-ancestors deveria ser 'none' (proteção contra clickjacking)")


# Hospedeiros para os quais um LINK pode apontar. Link não é requisição: nada
# sai daqui até que a pessoa clique, e clicar é decisão dela. O que a página de
# privacidade promete — e o que a CSP impõe — é que nenhum SUBRECURSO venha de
# fora, e essa proibição continua sem exceção alguma.
DESTINOS_DE_LINK = ("www.gov.br", "lattes.cnpq.br")


def test_sem_recursos_externos():
    """Nenhuma requisição automática sai do domínio."""
    subrecurso = re.compile(r'src\s*=\s*["\'](https?:)?//', re.I)
    link_externo = re.compile(r'href\s*=\s*["\'](?:https?:)?//([^/"\']+)', re.I)
    for arq in sorted(TEMPLATES.glob("*.j2")) + sorted(STATIC.glob("**/*.js")) \
            + sorted(STATIC.glob("**/*.css")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if subrecurso.search(linha):
                falhas.append(f"{arq.name}:{n}: subrecurso externo — a promessa de "
                              f"privacidade e a CSP proíbem")
            if "<link" in linha.lower() and link_externo.search(linha):
                falhas.append(f"{arq.name}:{n}: <link> para fora busca recurso "
                              f"antes de qualquer clique")
            for host in link_externo.findall(linha):
                if host not in DESTINOS_DE_LINK:
                    falhas.append(f"{arq.name}:{n}: link para {host}, fora da "
                                  f"lista de destinos declarados")
    for arq in sorted(STATIC.glob("**/*.css")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"@import\s+url\(\s*['\"]?https?:", linha, re.I):
                falhas.append(f"{arq.name}:{n}: @import externo no CSS")


PISO_REM = 0.82   # 13,1px com raiz de 16px


def test_piso_tipografico():
    """Nenhum texto abaixo de 13px, e nenhum tamanho preso em atributo.

    As duas metades desta checagem são a mesma coisa vista de dois lados. O
    piso de ~13px veio de medir o site num aparelho de 375px, onde o texto de
    apoio saía entre 10,9px e 12,5px. E `style=` em atributo vence qualquer
    folha de estilo, inclusive a media query que estabelece esse piso — foi
    exatamente assim que 69 elementos escaparam da primeira correção. Um
    tamanho que mora no atributo é um tamanho que ninguém consegue ajustar
    depois; por isso ele é barrado aqui, e não só o valor pequeno.
    """
    em_atributo = re.compile(r'style="[^"]*font-size:\s*([0-9.]+)rem')
    em_bloco = re.compile(r"([^{}]+)\{[^{}]*font-size:\s*([0-9.]+)rem")
    for arq in sorted(TEMPLATES.glob("*.j2")):
        texto = arq.read_text(encoding="utf-8")
        for n, linha in enumerate(texto.splitlines(), 1):
            if em_atributo.search(linha):
                falhas.append(f"{arq.name}:{n}: font-size em atributo style — "
                              f"vence a folha de estilo e escapa do piso do celular")
        for bloco in re.findall(r"<style>(.*?)</style>", texto, re.S):
            for seletor, valor in em_bloco.findall(bloco):
                if float(valor) < PISO_REM:
                    falhas.append(f"{arq.name}: {seletor.strip()[:40]} usa "
                                  f"{valor}rem, abaixo do piso de {PISO_REM}rem")
    # Na folha principal o piso não vale para toda largura: no desktop, texto de
    # apoio menor é legítimo. O que não pode é um seletor ficar pequeno E não ser
    # elevado pela media query do celular. Então a checagem é relacional — quais
    # seletores a media query resgata, e quais ficaram de fora dela.
    for arq in sorted(STATIC.glob("**/*.css")):
        # Comentário grudado no seletor seguinte vira parte do nome e faz a
        # comparação falhar sem que nada esteja errado na folha.
        folha = re.sub(r"/\*.*?\*/", "", arq.read_text(encoding="utf-8"), flags=re.S)
        resgatados = set()
        for m in re.finditer(r"@media \(max-width: (\d+)px\)\s*\{", folha):
            if int(m.group(1)) < 600:      # blocos de ajuste fino, não o piso
                continue
            corpo, nivel, i = "", 1, m.end()
            while i < len(folha) and nivel:
                nivel += (folha[i] == "{") - (folha[i] == "}")
                corpo += folha[i]
                i += 1
            for seletor, valor in em_bloco.findall(corpo):
                if float(valor) >= PISO_REM:
                    resgatados.update(s.strip() for s in seletor.split(","))
        for seletor, valor in em_bloco.findall(folha):
            partes = [s.strip() for s in seletor.split(",")]
            if float(valor) >= PISO_REM:
                continue
            # As figuras têm tipografia própria, em unidades do viewBox.
            if "figura" in seletor:
                continue
            orfas = [s for s in partes if s and not s.startswith("/*")
                     and s not in resgatados]
            if orfas:
                falhas.append(f"{arq.name}: {orfas[0][:40]} usa {valor}rem e a "
                              f"media query do celular não o eleva ao piso")


def test_sem_rastreamento():
    """Sem cookies, sem storage, sem analytics — a base da declaração de LGPD."""
    proibidos = {
        "document.cookie": "cookie",
        "localStorage": "armazenamento local",
        "sessionStorage": "armazenamento de sessão",
        "indexedDB": "IndexedDB",
        "gtag(": "Google Analytics",
        "dataLayer": "tag manager",
        "sendBeacon": "beacon de telemetria",
    }
    alvos = sorted(STATIC.glob("**/*.js")) + sorted(TEMPLATES.glob("*.j2"))
    for arq in alvos:
        texto = arq.read_text(encoding="utf-8")
        for agulha, nome in proibidos.items():
            # A página de privacidade cita os termos justamente para negá-los.
            if agulha in texto and arq.name != "privacidade.html.j2":
                falhas.append(f"{arq.name}: usa {nome} ({agulha}) — contradiz "
                              f"privacidade.html")


def test_sem_credencial_versionada():
    """Chave de API não pode entrar no repositório.

    Este repositório é público: uma chave commitada fica no histórico para
    sempre, e removê-la do HEAD não a apaga de lá — o remédio seria reescrever
    o histórico e rotacionar a chave. Melhor nunca deixar entrar.
    """
    padroes = [
        (re.compile(r"DADOS_GOV_API_KEY\s*=\s*['\"][^'\"]{8,}"), "chave do dados.gov.br"),
        (re.compile(r"chave-api-dados-abertos['\"]?\s*[:=]\s*['\"][^'\"]{8,}"), "header com chave"),
        (re.compile(r"(?i)(api[_-]?key|secret|token|senha|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}"),
         "credencial literal"),
    ]
    alvos = list((REPO / "etl").glob("*.py")) + list((REPO / "site").glob("*.py"))         + list((REPO / "tests").glob("*.py")) + list(STATIC.glob("**/*.js"))         + list(TEMPLATES.glob("*.j2")) + list((REPO / ".github").glob("**/*.yml"))
    # Exemplos de uso na documentação usam valor obviamente fictício. Ignorar
    # esses casos mantém o teste útil: um teste que grita em falso é desligado,
    # e aí deixa de proteger de verdade.
    marcadores = ("sua-chave", "sua_chave", "your-key", "your_key", "exemplo",
                  "coloque", "xxxx", "<", "trocar", "changeme")
    for arq in alvos:
        texto = arq.read_text(encoding="utf-8")
        for padrao, rotulo in padroes:
            for achado in padrao.finditer(texto):
                trecho = achado.group(0).lower()
                if any(m in trecho for m in marcadores):
                    continue
                falhas.append(f"{arq.name}: {rotulo} aparentemente literal no código "
                              f"— use variável de ambiente")
                break


def test_acessibilidade_base():
    base = (TEMPLATES / "base.html.j2").read_text(encoding="utf-8")
    checar('lang="pt-BR"' in base, "sem lang=\"pt-BR\" no <html>")
    checar("pular-para-conteudo" in base, "sem link de pular para o conteúdo")
    checar('id="conteudo"' in base, "sem alvo #conteudo para o link de pular")
    checar("aria-live" in base, "sem região aria-live para anunciar resultados")


def test_contraste_tokens():
    """Cor de texto precisa de 4,5:1 (WCAG AA). Tokens de traço não servem de texto."""
    css = (STATIC / "css" / "style.css").read_text(encoding="utf-8")

    def luminancia(hexa):
        canais = []
        for i in (1, 3, 5):
            v = int(hexa[i:i + 2], 16) / 255
            canais.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]

    def razao(a, b):
        la, lb = luminancia(a), luminancia(b)
        maior, menor = max(la, lb), min(la, lb)
        return (maior + 0.05) / (menor + 0.05)

    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", css))
    fundo = tokens.get("--bg", "#FFFFFF")
    for nome in ("--text", "--text-muted", "--gold-texto", "--nodata-texto",
                 "--navy", "--blue"):
        cor = tokens.get(nome)
        if not cor:
            falhas.append(f"token {nome} ausente em style.css")
            continue
        r = razao(cor, fundo)
        checar(r >= 4.5, f"{nome} ({cor}) tem contraste {r:.2f}:1 sobre {fundo} — "
                         f"WCAG AA exige 4,5:1 para texto")

    # Os tokens de traço não podem voltar a ser usados como cor de texto.
    for bruto in ("var(--gold)", "var(--nodata)"):
        for n, linha in enumerate(css.splitlines(), 1):
            if re.search(r"color:\s*" + re.escape(bruto), linha):
                falhas.append(f"style.css:{n}: {bruto} usado como cor de texto — "
                              f"use a variante -texto, que passa no AA")


def main():
    test_autoescape()
    test_sem_handlers_inline()
    test_csp()
    test_sem_recursos_externos()
    test_sem_rastreamento()
    test_sem_credencial_versionada()
    test_acessibilidade_base()
    test_contraste_tokens()
    test_piso_tipografico()

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) de segurança/acessibilidade:\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)

    print("[PASSOU] CSP sem unsafe-inline, zero handler inline, zero recurso "
          "externo, zero rastreamento, contraste AA nos tokens de texto.")


if __name__ == "__main__":
    main()
