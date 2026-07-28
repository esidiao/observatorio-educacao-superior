"""
Acesso HTTPS ao servidor do INEP, com a cadeia que ele não envia.

    from rede import abrir
    with abrir(url, timeout=900) as resposta:
        ...

O problema. `download.inep.gov.br` apresenta **só o certificado folha**: a
intermediária que o assina ("RNP ICPEdu ... OV TLS CA") não vai junto. Um
navegador ou uma máquina que já visitou o domínio completam a cadeia sozinhos —
por cache ou por buscar o emissor — e por isso o download funciona no Windows
de quem desenvolve. Um runner de CI recém-criado não tem esse cache, e a
verificação falha com "unable to get local issuer certificate".

A correção. O próprio certificado folha diz onde está o emissor, no campo
*Authority Information Access*. Esta função lê esse endereço, baixa a
intermediária e a acrescenta ao conjunto de confiança **junto com** as raízes do
sistema. A cadeia continua tendo de terminar numa raiz confiável: o que se faz
aqui é fornecer o elo que o servidor omitiu, não aceitar um elo qualquer.

O que NÃO se faz, e a razão. Em nenhuma hipótese se desliga a verificação. O
atalho existe, cabe em uma linha e resolveria o sintoma — e transformaria todo
download de microdado numa conexão que qualquer intermediário poderia substituir
sem que nada acusasse. Um observatório que publica número oficial não pode ter
dúvida sobre a procedência do arquivo de onde o número saiu.
"""
import os
import ssl
import tempfile
import urllib.request

_CONTEXTO = None


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


def contexto(host):
    """Contexto TLS com as raízes do sistema mais a intermediária ausente.

    Devolve o contexto padrão quando o servidor manda a cadeia completa — a
    remenda só entra onde faz falta.
    """
    global _CONTEXTO
    if _CONTEXTO is not None:
        return _CONTEXTO

    padrao = ssl.create_default_context()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(f"https://{host}/", method="HEAD",
                                       headers={"User-Agent": "observatorio-educacao"}),
                timeout=60, context=padrao):
            pass
        _CONTEXTO = padrao          # cadeia completa: nada a remendar
        return _CONTEXTO
    except ssl.SSLCertVerificationError:
        pass
    except Exception:               # noqa: BLE001
        # 404, 403, timeout: a cadeia validou, o recurso é que não existe.
        _CONTEXTO = padrao
        return _CONTEXTO

    endereco = _emissor_declarado(host)
    if not endereco:
        raise ssl.SSLCertVerificationError(
            f"{host} não valida e o certificado não declara onde está o emissor")

    remendado = ssl.create_default_context()
    pem = _baixar_intermediaria(endereco)
    remendado.load_verify_locations(cadata=pem)
    print(f"[TLS] {host} não envia a intermediária; obtida em {endereco}")
    _CONTEXTO = remendado
    return _CONTEXTO


def abrir(url, timeout=900, metodo="GET"):
    """urlopen com o contexto certo para o host da URL.

    `metodo="HEAD"` serve para perguntar se o arquivo existe e que tamanho tem
    sem abrir o fluxo de centenas de megabytes.
    """
    host = urllib.request.urlparse(url).hostname
    req = urllib.request.Request(
        url, method=metodo, headers={"User-Agent": "observatorio-educacao"})
    return urllib.request.urlopen(req, timeout=timeout, context=contexto(host))
