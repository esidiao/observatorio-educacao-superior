# Observatório Nacional da Educação Superior

Site estático data-driven com indicadores de acesso territorial, qualidade, capacidade e
concentração institucional da educação superior brasileira — **por curso** e por unidade
federativa, a partir de microdados oficiais do INEP e do IBGE.

Generaliza o [Observatório Nacional da Formação Farmacêutica](https://github.com/esidiao/observatorio-formacao-farmaceutica)
para qualquer curso de graduação, acrescentando a comparação entre cursos.

## Princípio inegociável

Nenhum indicador é estimado, interpolado ou preenchido por analogia. Sem fonte oficial para
um recorte, o valor é `null` e aparece como **"sem dados"** — nunca como zero nem como uma
média plausível. Um vazio explicado vale mais que um número sem lastro.

Consequência prática: o ENADE é trienal e reveza as áreas avaliadas, então cursos fora do
ciclo publicado não têm indicadores de qualidade aqui, e o IAF não é calculado para eles.
Isso é esperado e explícito, não uma falha de coleta.

## Estrutura

```
etl/                 Pipeline (Python)
  referencias.py     Malha municipal, capitais, população — referências IBGE
  indices.py         Fórmulas canônicas + portão de qualidade (GO gate)
  ingestao.py        Microdados do Censo → agregados por curso/UF/município
  qualidade.py       Planilha CPC/ENADE → conceitos por curso/UF
  consolidar.py      Junta tudo, calcula índices, reporta nulos
data/
  cursos.json        Catálogo de cursos (rótulo CINE, ciclo ENADE, cobertura)
  cursos/<slug>/     Dados por curso: bruto, qualidade, cobertura, nacional
site/
  build.py           Gerador estático (Jinja2)
  templates/         Páginas
  static/            CSS, JS (INDICADOR_META + GLOSSARIO)
  dist/              Site gerado — NÃO versionar
tests/               Portão de integridade e coerência do catálogo
```

## Rodar localmente

```bash
pip install -r requirements.txt
```

### Pipeline completo

Os microdados do Censo não estão versionados (>450 MB). Baixe em
[dados abertos do INEP](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados)
e rode:

```bash
python etl/ingestao.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2024.CSV --ies caminho/MICRODADOS_ED_SUP_IES_2024.CSV
python etl/qualidade.py --cpc caminho/CPC_2023.xlsx
python etl/consolidar.py
```

### Portão de qualidade e testes

```bash
python etl/indices.py --autoteste
python tests/test_validacao.py
python tests/test_catalogo.py
```

### Gerar o site

```bash
python site/build.py
```

Abra `site/dist/index.html`.

## Adicionar um curso

Acrescente uma entrada em `data/cursos.json` e rode o pipeline. O `cine_rotulo` precisa bater
**exatamente** com `NO_CINE_ROTULO` dos microdados — nunca use correspondência parcial: buscar
"Medicina" por substring capturaria "Biomedicina" e "Medicina veterinária"; "Direito"
capturaria "Programas interdisciplinares abrangendo negócios, administração e direito".

Para descobrir o rótulo exato:

```bash
python -c "import pandas as pd; print(pd.read_csv('MICRODADOS_CADASTRO_CURSOS_2024.CSV', sep=';', encoding='latin-1', usecols=['NO_CINE_ROTULO'])['NO_CINE_ROTULO'].value_counts().to_string())"
```

Ao criar um indicador novo, adicione-o **tanto** no `GLOSSARIO` (`site/static/js/glossario.js`)
quanto no `INDICADOR_META` (`site/static/js/app.js`) — `tests/test_catalogo.py` falha o build
se algum ficar sem par. Sem entrada em `INDICADOR_META`, o valor cai num fallback de 3 casas
decimais e uma contagem como 19 é renderizada `19,000`, que em pt-BR se lê como dezenove mil.

## Indicadores

| Índice | Fórmula | Direção |
|--------|---------|---------|
| ICT | ½·(vagas_capital/vagas_presencial) + ½·(1 − mun_oferta/mun_total) | ↓ melhor |
| E | 1 − ICT | ↑ melhor |
| IAF | 100·média(Q, V, E) — Q=conceitos normalizados, V=vagas avaliadas/vagas totais, E=equidade | ↑ melhor |
| HHI | Σ(sᵢ²) por IES | ↓ mais disperso |
| CR2 / CR10 | Fatia das 2 / 10 maiores IES | ↓ mais disperso |
| Cobertura correlata | mun. com serviço correlato / mun. com oferta | ↑ melhor |

A **cobertura correlata** é opcional e declarada por curso em `data/cursos.json` (ex.: Farmácia
Popular para Farmácia). Cursos sem uma fonte pública adequada simplesmente não exibem o
indicador — nenhuma proxy é inventada para preencher a lacuna.

## Modalidade a distância

No Censo, a EaD aparece em duas camadas que **não podem ser somadas ingenuamente**: as linhas
de *sede* carregam as vagas autorizadas mas não têm UF própria; as linhas de *polo* carregam as
matrículas por município, com zero vagas. Aqui as vagas EaD são atribuídas à UF-sede da
mantenedora (via cadastro de IES) e o alcance territorial é medido pelos polos, em indicador
separado.

Por isso **"municípios com oferta" conta apenas oferta presencial**. Um polo EaD não equivale a
um campus, e fundir os dois num único número inflaria a leitura de cobertura territorial.

## Fontes

1. **Censo da Educação Superior (INEP)** — vagas, cursos, IES, municípios, matrículas e perfil
2. **Cadastro de IES (INEP)** — UF-sede das mantenedoras, para atribuição das vagas EaD
3. **CPC / ENADE (INEP)** — conceitos de qualidade, titulação docente, avaliação dos estudantes
4. **Estimativas populacionais (IBGE)** — base dos indicadores per capita

## Design System

Cores: `--navy #16304F` · `--blue #2E5496` · `--gold #B07D22` · sem dados `#C9CDD2`
Escalas divergentes: sempre **RdBu** (nunca RdYlGn — regra de acessibilidade para daltonismo)
`lang="pt-BR"` · contraste WCAG AA
