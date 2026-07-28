"""
Acesso HTTPS ao servidor do INEP, com a cadeia que ele não envia.

    from rede import abrir
    with abrir(url, timeout=900) as resposta:
        ...

O problema. `download.inep.gov.br` apresenta **só o certificado folha**: a
intermediária que o assina ("RNP ICPEdu ... OV TLS CA") não vai junto. Uma
máquina que já visitou o domínio completa a cadeia sozinha, e por isso o
download sempre funcionou no Windows de quem desenvolve. Um runner de CI
recém-criado não tem esse cache, e a verificação falha com "unable to get local
issuer certificate".

A correção. O próprio certificado folha diz onde está o emissor, no campo
*Authority Information Access*. Este módulo lê esse endereço, baixa a
intermediária e a acrescenta ao conjunto de confiança **junto com** as raízes do
sistema. A cadeia continua tendo de terminar numa raiz confiável: fornece-se o
elo que o servidor omitiu, não se aceita um elo qualquer.

O que NÃO se faz, e a razão. Em nenhuma hipótese se desliga a verificação. O
atalho existe, cabe em uma linha e resolveria o sintoma — e transformaria todo
download de microdado numa conexão que qualquer intermediário poderia substituir
sem que nada acusasse. Um observatório que publica número oficial não pode ter
dúvida sobre a procedência do arquivo de onde o número saiu.

Uma armadilha que custou uma execução de CI: `urllib` **embrulha** o erro de
verificação num `URLError`, e um `except ssl.SSLCertVerificationError` nunca é
alcançado. É preciso desembrulhar `e.reason`. A primeira versão deste módulo
caiu nisso, e o sintoma foi silencioso — o remendo simplesmente nunca entrava.
"""
import os
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request

_REMENDADO = {}          # host -> contexto com a intermediária adicionada


def _emissor_declarado(host, porta=443):
    """Endereço da intermediária, lido do certificado que o servidor apresenta.

    Ler não é confiar: a conexão aqui serve só para obter o certificado, e a
    verificação de verdade acontece depois, no contexto montado com ele.
    """
    pem = ssl.get_server_certificate((host, porta))
    arquivo = tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode="w")
    try:
        arquivo.write(pem)
        arquivo.close()
        info = ssl._ssl._test_decode_cert(arquivo.name)
    finally:
        os.unlink(arquivo.name)
    enderecos = info.get("caIssuers") or ()
    return enderecos[0] if enderecos else None


def _baixar_intermediaria(endereco):
    """Baixa a intermediária e devolve em PEM. Ela costuma vir em DER."""
    req = urllib.request.Request(
        endereco, headers={"User-Agent": "observatorio-educacao"})
    with urllib.request.urlopen(req, timeout=120) as r:
        bruto = r.read()
    if b"-----BEGIN CERTIFICATE-----" in bruto:
        return bruto.decode("ascii")
    return ssl.DER_cert_to_PEM_cert(bruto)


def contexto_remendado(host, base=None):
    """Contexto com as raízes de sempre mais a intermediária que faltava."""
    if host in _REMENDADO:
        return _REMENDADO[host]

    endereco = _emissor_declarado(host)
    if not endereco:
        raise ssl.SSLCertVerificationError(
            f"{host} não valida e o certificado não declara onde está o emissor")

    ctx = base() if base else ssl.create_default_context()
    ctx.load_verify_locations(cadata=_baixar_intermediaria(endereco))
    print(f"[TLS] {host} não envia a intermediária; obtida em {endereco}")
    _REMENDADO[host] = ctx
    return ctx


def abrir(url, timeout=900, metodo="GET", base=None):
    """urlopen que completa a cadeia se — e só se — ela vier incompleta.

    `base` é uma fábrica de contexto, usada nos testes para reproduzir uma
    máquina sem a intermediária em cache.
    """
    host = urllib.parse.urlparse(url).hostname
    req = urllib.request.Request(
        url, method=metodo, headers={"User-Agent": "observatorio-educacao"})

    if host in _REMENDADO:
        return urllib.request.urlopen(req, timeout=timeout,
                                      context=_REMENDADO[host])
    try:
        ctx = base() if base else ssl.create_default_context()
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except urllib.error.HTTPError:
        # Houve resposta HTTP, logo o TLS funcionou. 404 é ausência do arquivo,
        # não problema de cadeia — remendar aqui não faria sentido.
        raise
    except Exception as original:                    # noqa: BLE001
        # Qualquer outra falha: tenta uma vez com a cadeia completada. Não se
        # classifica o erro pelo texto ou pelo código — a primeira versão deste
        # módulo fazia isso e errava de forma intermitente, o que é pior que
        # errar sempre, porque parece funcionar. O remendo só ACRESCENTA uma
        # intermediária ao conjunto de confiança; se a cadeia continuar
        # inválida, a conexão continua sendo recusada.
        try:
            ctx = contexto_remendado(host, base)
        except Exception:                            # noqa: BLE001
            raise original
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.HTTPError:
            raise
        except Exception:                            # noqa: BLE001
            # O remendo não resolveu: o erro que importa relatar é o primeiro.
            raise original
