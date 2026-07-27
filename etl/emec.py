"""
e-MEC: situação cadastral e regulatória das instituições.

Precisa de chave da API do Portal Brasileiro de Dados Abertos, que é pessoal e se
obtém em https://dados.gov.br, área "Minha Conta".

    export DADOS_GOV_API_KEY="sua-chave"
    python etl/emec.py --listar          # inspeciona conjunto, recursos e colunas
    python etl/emec.py                   # ingere para data/emec.json

A CHAVE NUNCA VAI PARA O REPOSITÓRIO. É lida só de variável de ambiente, e
tests/test_seguranca.py reprova o build se algo com cara de credencial aparecer no
código. O repositório é público: chave commitada fica no histórico para sempre.

O QUE ESTE CONJUNTO *NÃO* TEM — verificado, não suposto. O e-MEC aberto publica
cadastro, e só. Os campos declarados no $metadata do serviço são:

    CODIGO_DA_IES, NOME_DA_IES, SIGLA, CATEGORIA_DA_IES, COMUNITARIA,
    CONFESSIONAL, FILANTROPICA, ORGANIZACAO_ACADEMICA, CODIGO_MUNICIPIO_IBGE,
    MUNICIPIO, UF, SITUACAO_IES

Não há Conceito Institucional, Conceito de Curso, IGC, situação de credenciamento
nem data de avaliação. Esses vivem no sistema web do e-MEC, não no dado aberto.
Portanto as quatro ausências que os painéis institucionais declaram CONTINUAM
ausentes, e a explicação nas páginas foi corrigida para dizer o motivo certo:
não é que falte base aberta, é que a base aberta não publica esses campos.

O que dá para acrescentar, quando o serviço voltar: SITUACAO_IES — o Censo não
informa se a instituição está ativa ou extinta. E, pela entidade de cursos,
SITUACAO_CURSO e QT_VAGAS_AUTORIZADAS, que são a visão REGULATÓRIA (o que o MEC
autorizou) contra a visão do Censo (o que a instituição declarou ofertar). O
confronto entre as duas é interessante justamente por poderem divergir.

ESTADO DO SERVIÇO. Em 27/07/2026 o endpoint OData do MEC responde HTTP 500 em
todas as entidades, com "FATAL: password authentication failed for user
sysolindamec" — falha de credencial do banco do lado deles, não nosso. O
$metadata responde porque é estático. Este ETL está correto e apontado para a URL
certa; é só rodar quando o serviço voltar.
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

BASE = "https://dados.gov.br/dados/api/publico"
CABECALHO_CHAVE = "chave-api-dados-abertos"
VARIAVEL = "DADOS_GOV_API_KEY"
BUSCA_PADRAO = "e-MEC"

# Campo interno → possíveis nomes de coluna, em ordem de preferência. Vale por
# trecho e sem caixa: o e-MEC muda pontuação e acentuação entre publicações.
CAMPOS = {
    "co_ies": ("CODIGO_DA_IES", "CODIGO_IES", "CO_IES"),
    "nome": ("NOME_DA_IES", "NOME_IES"),
    "sigla": ("SIGLA",),
    # O único campo aqui que o Censo não traz: se a instituição segue ativa.
    "situacao": ("SITUACAO_IES", "SITUACAO"),
    "categoria": ("CATEGORIA_DA_IES", "CATEGORIA_ADMINISTRATIVA"),
    "organizacao": ("ORGANIZACAO_ACADEMICA",),
    "comunitaria": ("COMUNITARIA",),
    "confessional": ("CONFESSIONAL",),
    "filantropica": ("FILANTROPICA",),
    "municipio": ("MUNICIPIO",),
    "uf": ("UF",),
}


def chave():
    valor = os.environ.get(VARIAVEL, "").strip()
    if not valor:
        sys.exit(
            f"[ERRO] Variável {VARIAVEL} não definida.\n"
            f"       A chave é pessoal e não pode ser versionada. Obtenha em\n"
            f"       https://dados.gov.br (Minha Conta) e exporte na sessão:\n"
            f'         PowerShell:  $env:{VARIAVEL} = "sua-chave"\n'
            f'         bash:        export {VARIAVEL}="sua-chave"')
    return valor


def pedir(caminho, params=None):
    url = f"{BASE}{caminho}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        CABECALHO_CHAVE: chave(),
        "Accept": "application/json",
        "User-Agent": "observatorio-educacao",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("[ERRO] 401: chave recusada. Confira se copiou a chave inteira "
                     "e se o perfil tem permissão de consulta.")
        sys.exit(f"[ERRO] HTTP {e.code} em {url}")


def normalizar(nome):
    return "".join(c if c.isalnum() else "_" for c in str(nome).upper()).strip("_")


def achar_coluna(colunas, candidatos):
    normalizadas = {normalizar(c): c for c in colunas}
    for alvo in candidatos:
        if alvo in normalizadas:
            return normalizadas[alvo]
    # Segunda passada, por trecho — cobre sufixos e prefixos inesperados.
    for alvo in candidatos:
        for norm, original in normalizadas.items():
            if alvo in norm:
                return original
    return None


def baixar_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "observatorio-educacao"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        bruto = resp.read()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(enc)
        except UnicodeDecodeError:
            continue
        amostra = texto[:4000]
        delim = ";" if amostra.count(";") > amostra.count(",") else ","
        return list(csv.DictReader(io.StringIO(texto), delimiter=delim))
    sys.exit("[ERRO] não foi possível decodificar o CSV.")


def main():
    parser = argparse.ArgumentParser(description="Ingestão do cadastro e-MEC")
    parser.add_argument("--busca", default=BUSCA_PADRAO)
    parser.add_argument("--id", help="ID do conjunto, quando a busca traz vários")
    parser.add_argument("--listar", action="store_true",
                        help="Só mostra conjuntos, recursos e colunas — não ingere")
    parser.add_argument("--recurso", help="URL de um recurso CSV específico")
    parser.add_argument("--saida", default=str(DATA / "emec.json"))
    args = parser.parse_args()

    if args.recurso:
        linhas = baixar_csv(args.recurso)
    else:
        print(f"[INFO] Buscando conjuntos com '{args.busca}' ...")
        # `pagina` é obrigatório na API — sem ele a resposta é 400, não 401.
        resultado = pedir("/conjuntos-dados",
                          {"nomeConjuntoDados": args.busca, "pagina": 1})
        conjuntos = resultado if isinstance(resultado, list) else resultado.get("value", [])
        if not conjuntos:
            sys.exit(f"[ERRO] nenhum conjunto encontrado para '{args.busca}'.")

        print(f"[INFO] {len(conjuntos)} conjunto(s):")
        for c in conjuntos[:10]:
            print(f"   id={c.get('id')}  {c.get('title') or c.get('nome')}")

        escolhido = args.id
        if not escolhido:
            # A busca traz espelhos de universidades junto do conjunto oficial.
            # Preferir o que o MEC publica, não o primeiro que voltou.
            def pontuar(c):
                titulo = (c.get("title") or c.get("nome") or "").lower()
                return (("sistema e-mec" in titulo) * 2
                        + ("institui" in titulo) * 2
                        - ("ufu" in titulo or "curso" in titulo))
            escolhido = max(conjuntos, key=pontuar).get("id")
        print(f"[INFO] usando conjunto {escolhido}")
        detalhe = pedir(f"/conjuntos-dados/{escolhido}")
        recursos = detalhe.get("recursos") or detalhe.get("resources") or []
        print(f"\n[INFO] {len(recursos)} recurso(s) no primeiro conjunto:")
        csvs = []
        for r in recursos:
            formato = (r.get("formato") or r.get("format") or "").upper()
            link = r.get("link") or r.get("url")
            print(f"   [{formato}] {r.get('titulo') or r.get('name')}\n        {link}")
            if formato == "CSV" and link and not link.rstrip("#{}").endswith("/"):
                csvs.append(link)
        if not csvs:
            sys.exit("[ERRO] nenhum recurso CSV. Rode com --recurso <url> se souber "
                     "o endereço, ou confira a saída acima.")
        linhas = baixar_csv(csvs[0])

    if not linhas:
        sys.exit("[ERRO] recurso vazio.")
    colunas = list(linhas[0].keys())
    if len(colunas) <= 1:
        sys.exit("[ERRO] o recurso baixado tem 1 coluna — provavelmente é uma "
                 "página HTML, não um CSV. Alguns conjuntos apontam para a página "
                 "do arquivo, não para o arquivo. Use --recurso com a URL direta.")
    print(f"\n[INFO] {len(linhas)} linhas · {len(colunas)} colunas")

    mapa = {campo: achar_coluna(colunas, candidatos)
            for campo, candidatos in CAMPOS.items()}
    print("\n[INFO] mapeamento de colunas:")
    for campo, coluna in mapa.items():
        print(f"   {campo:<16} -> {coluna or '(NAO ENCONTRADA)'}")

    if args.listar:
        print("\n[INFO] Colunas disponíveis:")
        for c in colunas:
            print("   ", c)
        print("\nConfira o mapeamento acima contra CAMPOS em etl/emec.py e rode "
              "sem --listar para ingerir.")
        return

    if not mapa["co_ies"]:
        sys.exit("[ERRO] coluna de código da IES não localizada. Sem ela não há "
                 "junção exata com o Censo, e casar por nome seria heurística — "
                 "o que este projeto recusa. Rode --listar e ajuste CAMPOS.")

    saida = {}
    for linha in linhas:
        codigo = str(linha.get(mapa["co_ies"]) or "").strip().split(".")[0]
        if not codigo or not codigo.isdigit():
            continue
        registro = {}
        for campo, coluna in mapa.items():
            if campo == "co_ies" or not coluna:
                continue
            valor = str(linha.get(coluna) or "").strip()
            registro[campo] = valor or None
        saida[codigo] = registro

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump({
            "_nota": ("Conceito Institucional (CI) vem de avaliação in loco por "
                      "comissão e NÃO é o IGC, que é índice calculado sobre CPC e "
                      "pós-graduação. Os dois convivem, nunca se substituem."),
            "_fonte": "Portal Brasileiro de Dados Abertos — cadastro e-MEC",
            "instituicoes": saida,
        }, f, ensure_ascii=False, indent=1)

    caminho_ies = DATA / "instituicoes.json"
    print(f"\n[OK] {len(saida)} instituições em {args.saida}")
    if caminho_ies.exists():
        with open(caminho_ies, encoding="utf-8") as f:
            nossas = json.load(f)["instituicoes"]
        casadas = sum(1 for co in nossas if co in saida)
        print(f"     {casadas} de {len(nossas)} do observatório casaram por código "
              f"({100 * casadas / len(nossas):.0f}%)")
        if casadas < len(nossas) * 0.5:
            print("     [ATENÇÃO] casamento baixo. O código do e-MEC pode não ser o "
                  "mesmo do Censo neste recurso — confira antes de publicar.")


if __name__ == "__main__":
    main()
