"""
Monta o título e o corpo da issue que anuncia uma edição nova do Censo.

    python .github/scripts/issue_novo_censo.py relatorio.json corpo.md

Escreve o corpo no arquivo indicado e imprime o título na saída padrão.

Existe como arquivo, e não como heredoc dentro do YAML, por uma razão prática:
no workflow o texto ficaria indentado junto com o passo, e markdown lê recuo de
quatro espaços como bloco de código — a issue inteira sairia dentro de um
<pre>. Fora do YAML, o texto é texto.
"""
import json
import sys
from pathlib import Path

MODELO = """\
O servidor do INEP passou a responder pelo pacote de microdados do
**Censo {ano}**, mais recente que a edição em uso no site (Censo {atual}).

Tamanho do pacote: {mb} MB.

## Antes de ingerir

O Censo costuma sair primeiro como **prévia** e depois como versão
consolidada. Confirme na página de divulgação do INEP qual das duas está
publicada: ingerir a prévia troca dado estável por dado provisório, e o site
não tem como distinguir uma da outra depois de ingerida.

## Ordem de execução

```bash
python etl/catalogo.py                   # rótulos CINE da nova edição
python etl/ingestao.py                   # agregados por curso, UF e município
python etl/qualidade.py                  # CPC/ENADE, se houver ciclo novo
python etl/instituicoes.py
python etl/consolidar.py
python etl/baixar_censo.py --anos {ano}  # acumula nas três séries históricas
python site/build.py
```

## O que vai falhar, e deve falhar

`tests/test_validacao.py` guarda âncoras de regressão com valores do Censo
{atual}. Elas **vão reprovar** — é para isso que existem. Conferir os novos
números contra a fonte e então atualizar as âncoras é parte da ingestão; passar
por cima delas transformaria o portão em enfeite.

Os outros portões (`test_catalogo`, `test_seguranca`, `test_site_gerado`,
`test_viewport`) devem continuar verdes. Se algum reprovar, a causa é outra.

## Depois

- Atualizar o ano citado no README e na página de metodologia.
- Rodar `python etl/registro_autoral.py` para reselar o registro de
  anterioridade com o novo conjunto de arquivos.

---

Relatório da verificação automática:

```json
{relatorio}
```
"""


def main():
    if len(sys.argv) != 3:
        sys.exit("uso: issue_novo_censo.py <relatorio.json> <corpo.md>")
    relatorio = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    novas = relatorio.get("novas") or []
    if not novas:
        sys.exit("[ERRO] relatório sem edição nova — este script não deveria ter "
                 "sido chamado")

    # A mais recente entre as encontradas: se duas edições saíram entre duas
    # execuções, é a última que interessa anunciar.
    nova = max(novas, key=lambda n: n["ano"])
    corpo = MODELO.format(
        ano=nova["ano"], mb=nova["mb"], atual=relatorio["edicao_em_uso"],
        relatorio=json.dumps(relatorio, ensure_ascii=False, indent=2))
    Path(sys.argv[2]).write_text(corpo, encoding="utf-8")
    print(f"Censo {nova['ano']} publicado pelo INEP")


if __name__ == "__main__":
    main()
