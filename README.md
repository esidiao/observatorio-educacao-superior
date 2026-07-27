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
  catalogo.py        Microdados → data/cursos.json (todos os rótulos CINE)
  serie.py           Acumula uma edição do Censo na série histórica por curso
  baixar_censo.py    Baixa edições do INEP e alimenta a série (um ano por vez)
  instituicoes.py    Camada institucional (IES, organização, corpo docente)
  igc.py             Índice Geral de Cursos do INEP, por instituição
  fluxo.py           Evasão, conclusão e retenção por coorte (INEP)
  capes.py           Pós-graduação stricto sensu e conceitos CAPES
  emec.py            Conceito Institucional e credenciamento — exige chave de API
  malha.py           Baixa e versiona a malha do IBGE (UFs e centroides)
  ingestao.py        Microdados do Censo → agregados por curso/UF/município
  qualidade.py       Planilha CPC/ENADE → conceitos por curso/UF
  consolidar.py      Junta tudo, calcula índices, reporta nulos
data/
  cursos.json        Catálogo gerado (rótulo CINE, área, ciclo ENADE, cobertura)
  cursos/<slug>/     Por curso: bruto, qualidade, cobertura, nacional, serie
  instituicoes.json  2.561 IES com oferta no catálogo
  igc.json           IGC por instituição (fonte e calendário distintos do Censo)
  fluxo.json         Taxas de coorte por UF, 2010–2024
  capes.json         Programas de pós stricto sensu por instituição
  geo/               Malha do IBGE: fronteiras de UF e centroides municipais
site/
  build.py           Gerador estático (Jinja2)
  graficos.py        Mapas e gráficos em SVG, gerados no build
  agregados.py       Somas entre cursos — painéis de UF e de município
  insights.py        Leituras automáticas por regra — nunca por LLM
  templates/         Páginas
  static/            CSS, JS (INDICADOR_META + GLOSSARIO)
  dist/              Site gerado — NÃO versionar
tests/
  test_validacao.py  Integridade dos dados e âncoras de regressão
  test_catalogo.py   Coerência entre GLOSSARIO e INDICADOR_META
  test_seguranca.py  CSP, JS inline, recursos externos, rastreio, contraste AA
  test_site_gerado.py  Cobertura de páginas e invariantes do HTML publicado
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
python etl/catalogo.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2024.CSV --cpc caminho/CPC_2023.xlsx
python etl/ingestao.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2024.CSV --ies caminho/MICRODADOS_ED_SUP_IES_2024.CSV
python etl/qualidade.py --cpc caminho/CPC_2023.xlsx
python etl/consolidar.py
```

O primeiro passo reescreve `data/cursos.json` com **todos** os rótulos CINE que
existem no Censo — hoje 353. Os campos de curadoria humana (`cobertura` e um
`enade_ano` declarado à mão) são preservados por slug a cada regeração.

### Portão de qualidade e testes

```bash
python etl/indices.py --autoteste
python tests/test_validacao.py
python tests/test_catalogo.py
python tests/test_seguranca.py
python tests/test_site_gerado.py   # depois de gerar o site
```

### Gerar o site

```bash
python site/build.py
```

Abra `site/dist/index.html` — o site funciona por `file://`, sem servidor.

Para publicar, informe a URL pública, que habilita `sitemap.xml`, `robots.txt` e
os caminhos absolutos da página de erro:

```bash
python site/build.py --base-url https://usuario.github.io/observatorio-educacao-superior
```

Sem `--base-url` o sitemap não é gerado — um sitemap com URL inventada é pior que
sitemap nenhum.

## O catálogo de cursos

Não há curadoria de quais cursos entram: entram todos os rótulos CINE do Censo, do
maior (Pedagogia, 1,1 milhão de vagas) ao menor (cursos com uma dezena de vagas numa
única UF). Cobertura territorial parcial é o caso normal, não uma falha — a maioria
dos rótulos existe em poucas UFs.

O `cine_rotulo` bate **exatamente** com `NO_CINE_ROTULO` dos microdados. Match parcial
está proibido no pipeline inteiro: buscar "Medicina" por substring capturaria
"Biomedicina" (7.193 linhas) e "Medicina veterinária"; "Direito" capturaria "Programas
interdisciplinares abrangendo negócios, administração e direito".

Dois campos continuam sendo decisão humana e sobrevivem à regeração do catálogo:

- `cobertura` — a proxy territorial de cobertura correlata, quando existe fonte oficial;
- `enade_ano` — o ciclo declarado, quando se sabe o ano mas a planilha ainda não saiu.

A ligação com o ENADE é derivada: `etl/catalogo.py` casa a área de avaliação do CPC com
o rótulo CINE (a planilha usa outra nomenclatura — "TECNOLOGIA EM RADIOLOGIA" para o
rótulo "Radiologia"). Quem não casa fica sem ciclo, sem conceitos e sem IAF. Como o
ENADE é trienal e reveza as áreas, isso vale para a grande maioria dos cursos.

## Escala

Com 353 cursos × 27 UFs, duas coisas mudaram de forma no site:

- a lista de cursos saiu do HTML de cada página e virou `static/js/cursos.js`, carregado
  uma vez para todo o site — repetida em ~10 mil páginas, ela sozinha pesaria mais que
  todo o resto;
- a matriz de comparação virou `static/js/comparacao.js` em formato colunar (uma lista
  de campos + um vetor de valores por recorte), em vez de objetos com os nomes dos
  campos repetidos por curso e por UF.

Ambos são `<script>`, não `fetch` — o site continua abrindo por `file://`.

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

## Privacidade, segurança e acessibilidade

O site não coleta nada: sem cookies, sem `localStorage`, sem analytics e sem
recursos de terceiros. A restrição é técnica, não só declarada — a
Content-Security-Policy de cada página bloqueia qualquer carregamento externo, e
`tests/test_seguranca.py` reprova o build se um recurso de fora aparecer. Os dados
publicados são agregados por curso, UF e município; nenhum registro individual de
pessoa é usado. A página `privacidade.html` explica isso nos termos da LGPD.

Decisões que valem registro:

- **`script-src 'self'`, sem `'unsafe-inline'`.** Todo JavaScript vive em arquivo
  próprio e os dados por página vão em `<script type="application/json">`, que não
  é executável. Handlers no markup (`onclick=`) estão proibidos por teste.
- **`style-src` ainda admite `'unsafe-inline'`**, porque o layout usa atributos
  `style=` em vários pontos. É um risco muito menor que o equivalente em script, e
  está explícito aqui em vez de escondido.
- **Autoescape do Jinja precisa incluir `j2`.** `select_autoescape` casa pelo
  sufixo do arquivo; como todo template termina em `.j2`, uma lista com apenas
  `html`/`xml` desliga o escape em todas as páginas parecendo protegê-las. Há teste
  para isso.
- **Contraste WCAG AA.** Cores de traço e de texto são tokens distintos:
  `--gold`/`--nodata` desenham bordas e barras; `--gold-texto`/`--nodata-texto` são
  as versões legíveis. "Sem dados" é conteúdo, não decoração — precisa ser lido.

## Leituras automáticas, e por que não são geradas por IA

Cada página traz frases calculadas a partir dos próprios números — variação da
série, participação, concentração, posição. Elas são escritas por regra
(`site/insights.py`), com template, e não por modelo de linguagem.

A razão é o princípio do projeto. Um observatório que se recusa a estimar um
indicador não pode publicar, ao lado do número auditável, um parágrafo que
ninguém consegue auditar. Texto de LLM sobre dado quantitativo erra de formas
caras — inverte o sinal de uma variação, cita um número que não está na tabela e,
sobretudo, atribui causa onde o dado só mostra coincidência temporal. Publicado,
esse parágrafo herda a aparência de autoridade do resto do site.

As regras são estritas: só se afirma o que foi calculado, com o número à vista;
descreve-se variação, participação e posição, nunca causa; exige-se base mínima
(variação só a partir de 100 unidades, senão "2 vagas viraram 6" vira "crescimento
de 200%"); e cala-se quando não há material.

## Mapas e gráficos

Tudo é SVG gerado no build, sem biblioteca de visualização. A CSP proíbe recurso
de terceiro, e SVG estático imprime bem, funciona por `file://`, não custa
JavaScript e é lido por leitor de tela quando descrito. O preço é a ausência de
interatividade, compensada pela tabela exata ao lado de cada figura.

O coroplético usa **quantil**, não intervalo igual: em dado territorial brasileiro
São Paulo sozinho achataria as outras 26 UFs numa faixa só. O mapa municipal usa
**pontos**, não polígonos — a pergunta é "onde existe oferta", e ponto responde
isso com 150 KB em vez de vários MB. Área do círculo proporcional ao valor, nunca
o raio, que exageraria a diferença ao quadrado. A série temporal começa o eixo em
zero.

## Série histórica: o que ela não autoriza dizer

A série cobre **2016 a 2024**, nove edições do Censo. Para estendê-la ou
reconstruí-la:

```bash
python etl/baixar_censo.py --anos 2016 2017 2018 2019 2020 2021 2022
```

O script pega uma edição por vez, extrai só os dois CSVs necessários, alimenta a
série e descarta — sem o descarte, nove edições ocupariam mais de um giga em disco
para produzir treze megabytes de série. Dá para voltar até 2016 porque o INEP
reclassificou as edições antigas na CINE e republicou, então o match exato de
rótulo vale para trás sem gambiarra. (2015 responde de forma instável no servidor
do INEP; quando entrar, é só rodar o comando com `--anos 2015`.)

Ela mostra
**variação de estoque**, e isso não é evasão. O Censo é um retrato anual: a
diferença de matrículas entre dois anos mistura quem entrou, saiu, trancou e
concluiu, sem acompanhar os mesmos estudantes. Evasão e permanência exigem coorte
— os indicadores de fluxo do INEP, publicados à parte e ainda não ingeridos aqui.
Enquanto não estiverem, esses indicadores não existem no observatório.

Pelo mesmo motivo o corpo docente aparece só no nível da instituição: o Censo
informa docentes por IES, não por curso, e ratear seria inventar.

## Painéis territoriais e institucionais

As páginas de curso respondem "onde está este curso". Os painéis respondem o
contrário:

- `estados.html` e `uf/<UF>.html` — o que existe no estado somando os 353 cursos;
- `municipio/<UF>-<slug>.html` — os 1.119 municípios com oferta presencial;
- `instituicoes.html` e `instituicao/<código>.html` — as 2.561 IES;
- `rankings.html` — 12 listas, cada uma declarando por qual campo ordena.

Três coisas **não somam** entre cursos e são tratadas à parte: número de IES e de
municípios (a mesma instituição e o mesmo município aparecem em vários cursos, e
somar os contaria repetidamente — guarda-se o conjunto e conta-se no fim), e os
índices ICT, IAF e HHI, que são definidos por curso. Média de HHI de Medicina com
HHI de Pedagogia não significa nada: são mercados diferentes. Por isso os painéis
territoriais não os exibem, e a página do curso continua sendo o lugar deles.

Na página de município aparece um **piso** de instituições, não um total: o Censo
informa quantas IES ofertam cada curso ali, não quais. Somar contaria a mesma
instituição uma vez por curso que ela oferta.

Rankings sempre declaram a régua. Não é formalidade: "a maior universidade do
país" tem quatro respostas diferentes conforme a régua seja matrícula, vaga,
número de cursos ou corpo docente. E não há ranking de qualidade agregada — só 28
dos 353 cursos têm ciclo ENADE publicado, e ordenar instituições por uma nota que
existe para uma fração da oferta produziria um pódio que diz mais sobre quem foi
avaliado do que sobre quem é bom.

## Dados abertos

`api.html` documenta endpoints JSON estáticos em `api/v1/`: catálogo de cursos,
totais por UF e por município, camada institucional e, por curso, os indicadores
completos e a série histórica. Sem chave, sem cota, sem cadastro.

Não é uma API dinâmica — não há parâmetro de consulta nem paginação. Em troca,
nada quebra, nada tem limite de requisição e tudo é reproduzível: o conteúdo de
cada endereço só muda quando o observatório é reconstruído.

### Três armadilhas da série, e como estão tratadas

**Base zero.** Curso que não tinha EaD e passou a ter não gera variação
percentual — gera uma data de início. "Cresceu 28.600%" é pior que não dizer
nada; a leitura automática diz que não existia, em que ano apareceu e onde
chegou.

**Ano ausente.** Rótulo CINE que não existe numa edição vira ponto ausente, nunca
zero, e a linha do gráfico só liga anos consecutivos com dado. Uma linha única
atravessando o buraco desenharia uma tendência que ninguém mediu.

**Estrutura da EaD.** Verificado que a separação sede/polo é a mesma desde 2016 —
sede sem UF carrega as vagas, polo com UF tem zero. Sem essa checagem, um ano cujo
arquivo tivesse outra estrutura apareceria com EaD zerada e produziria um
crescimento inteiramente falso.

## IGC: o que ele é e o que ele não é

`etl/igc.py` ingere o Índice Geral de Cursos do INEP, indexado pelo código da IES
— a mesma chave do Censo, então o casamento é exato, sem heurística sobre nome.
Cobre **1.913 das 2.561 instituições (75%)**.

```bash
python etl/igc.py --igc caminho/IGC_2023.xlsx
```

Fica em arquivo separado de propósito: o IGC vem de outra fonte, com outro
calendário e outro ciclo (é trienal, sobre os CPC dos três últimos anos).
Misturá-lo ao `instituicoes.json` faria uma reingestão do Censo apagar dado de
avaliação. O build funde os dois na leitura.

**IGC não é Conceito Institucional.** Um é índice calculado sobre CPC e
pós-graduação; o outro é nota de comissão que visitou a instituição. CI, situação
de credenciamento e data da última avaliação continuam ausentes — estão no e-MEC,
que não tem base aberta com download estável — e as páginas dizem isso em vez de
aproximar um pelo outro.

**Ausência de IGC é ausência de avaliação, não avaliação ruim.** Instituição nova,
ou cujas áreas não entraram no rodízio do ENADE, fica sem. O caso mais eloquente é
a USP, que não tem IGC na planilha de 2023: o painel dela diz exatamente isso, em
vez de exibir um vazio que se leia como nota baixa. Pelo mesmo motivo, o ranking
por IGC declara na chamada que só lista quem foi avaliado.

Duas armadilhas técnicas que isso expôs e que ficaram tratadas: campos de
avaliação existem em **toda** instituição com `None` quando ausentes — sem isso o
template recebe `Undefined`, e `Undefined is not none` é verdadeiro no Jinja, o
que mandaria justamente quem não tem IGC para o ramo "tem avaliação". E os
formatadores passaram a converter qualquer coisa não numérica em "sem dados", em
vez de estourar no meio do build.

## Evasão: o indicador que o Censo não produz

Durante todo o desenvolvimento este observatório se recusou a falar em evasão, e
a recusa estava certa: o Censo é um retrato anual de estoque, e a diferença de
matrículas entre dois anos mistura quem entrou, saiu, trancou e concluiu, sem
seguir ninguém. Agora existe a fonte correta.

```bash
python etl/fluxo.py --fluxo caminho/indicadores_fluxo_UF_2010_2024.zip
```

Os Indicadores de Fluxo do INEP acompanham **coortes de ingressantes** ao longo do
tempo e produzem evasão, conclusão, retenção e permanência. São os únicos números
do site que seguem as mesmas pessoas — todo o resto é estoque. Cobrem 27 UFs e as
coortes de 2010-2011 a 2023-2024, com recorte por sexo, cor/raça e faixa etária.

**Limite de agregação, que decide onde eles podem aparecer.** O INEP publica por
unidade federativa, não por curso nem por instituição. Por isso a seção existe nos
painéis estaduais e em lugar nenhum mais. Ratear a taxa de um estado entre seus
cursos seria a estimativa que este projeto recusa: cursos têm perfis de evasão
radicalmente diferentes, e a média estadual não descreve nenhum deles.

**Séries de comprimentos diferentes.** Evasão é publicada desde a coorte
2010-2011; conclusão, retenção e permanência só desde 2016-2017. O gráfico desenha
as três no mesmo eixo com o buraco à vista, em vez de recortar todas ao menor
período comum — o que esconderia uma década de dado que existe.

**Ponto percentual não é percentual.** A leitura automática diz "subiu 7,9 pontos
percentuais", nunca "subiu 7,9%": sobre uma base de 11,7%, a segunda formulação
significaria 12,6%, um número diferente e errado.

## Pós-graduação: a face de pesquisa das instituições

```bash
python etl/capes.py --programas caminho/br-capes-colsucup-prog-2024.csv
```

Dados abertos da CAPES (Plataforma Sucupira). A junção é **exata, não heurística**:
o campo `CD_ENTIDADE_EMEC` da CAPES é o mesmo código de instituição usado pelo
INEP. Medido antes de escrever qualquer código: 353 das 375 IES da CAPES casam
pelo código, e as 22 restantes são entidades sem graduação nos rótulos
acompanhados. Ficam de fora por não terem onde aparecer, não por falha de
casamento.

Cobre 351 das 2.561 instituições do observatório, das quais 247 oferecem
doutorado.

Três ressalvas que aparecem na própria página:

**Escalas não se misturam.** O conceito CAPES vai de 1 a 7; o IGC e o CPC vão de
1 a 5. Avaliam objetos diferentes — programa de pós, instituição e curso de
graduação. Somar, mediar ou ranquear os três juntos não significaria nada, e por
isso não há nenhum indicador composto entre eles.

**Isto não descreve a graduação.** Doutorado nota 7 numa área não diz nada sobre a
graduação em outra. A seção existe para responder "que pesquisa esta instituição
faz", que é outra pergunta.

**Ausência aqui é fato, não lacuna.** Instituição sem programa stricto sensu
simplesmente não tem — diferente da ausência de IGC, que significa "não foi
avaliada". As duas ausências são semanticamente distintas e o site as distingue.
O caso da USP torna isso visível: sem IGC publicado, e com 259 programas de pós,
221 deles com doutorado.

## Painel executivo

A home abre com o sistema de educação superior em números — capacidade, alcance
territorial, modalidade e trajetória — mais duas séries: presencial contra EaD
(2016–2024) e evasão contra conclusão por coorte (2010–2024).

O total nacional de fluxo **não é a média das UFs**: é ponderado pelos estudantes
de cada uma, e por isso vem do arquivo do Brasil publicado pelo INEP, não de um
cálculo local sobre os 27 estados. Já a série de capacidade é somada dos cursos
durante o próprio laço do build, que já lê cada `serie.json` — evita uma segunda
varredura de 353 arquivos.

O que o painel mostra hoje, e que só ficou visível com as quatro fontes reunidas:
a capacidade a distância saiu de 4,3 para 18,6 milhões de vagas entre 2016 e 2024
(+327,6%) enquanto a presencial recuou 17,4%; a evasão nacional subiu 6,2 pontos
percentuais desde a coorte 2010-2011; e a conclusão perdeu 4,4 pontos desde
2016-2017.

## Sobre o e-MEC, com precisão

Afirmei em versões anteriores desta documentação que o e-MEC "não tem base
aberta". A afirmação era forte demais. O que se verifica:

- existe um conjunto "Sistema e-MEC — Instituições de Educação Superior do Brasil"
  registrado no dados.gov.br;
- a API daquele portal responde **401** sem chave de acesso;
- o portal `dadosabertos.mec.gov.br` responde **403** a requisição programática;
- Conceito Institucional (CI) e Conceito de Curso (CC) **não** estão no diretório
  de resultados do INEP, onde CPC e IDD estão e de onde este projeto já baixa.

Ou seja: a barreira é de credencial, não de inexistência. Obter chave de API é
decisão de quem mantém o observatório, porque a chave fica vinculada a uma
identidade. Enquanto isso, CI e credenciamento seguem declarados como ausentes nas
páginas — o que continua correto.

## Três comparações, um script

O site compara cursos, estados e instituições. A comparação de cursos nasceu antes
e tem lógica própria — recorte territorial, presets de indicador. As outras duas
têm exatamente a mesma necessidade (escolher itens, escolher campos, ver tabela e
barras), então usam um único script parametrizado por
`window.COMPARAVEIS`. Duas cópias quase idênticas divergiriam na primeira correção.

O que **não** entra na comparação entre estados: ICT, IAF e HHI. São índices
definidos curso a curso, e a média deles entre cursos diferentes não significa
nada. As taxas de coorte entram, sempre da última publicada.

O índice de municípios (`municipios.html`) fechou uma lacuna de navegação: as
1.119 páginas municipais existiam desde antes, mas só eram alcançáveis descendo
pela página da UF. A numeração da lista é recalculada a cada filtro — deixar o
número original faria a lista filtrada começar em "37", como se faltassem itens.

## e-MEC: o que a chave revelou

`etl/emec.py` está implementado e funcionando. A chave de API do Portal Brasileiro
de Dados Abertos permitiu **verificar** o que antes era suposição — e o resultado
foi o oposto do esperado.

```bash
export DADOS_GOV_API_KEY="sua-chave"
python etl/emec.py --listar --id 07f78ae9-e781-41bf-b88c-6f3bd2ab4326
```

**O conjunto aberto do e-MEC não tem os conceitos de avaliação.** Os campos que o
serviço declara no próprio `$metadata` são:

    CODIGO_DA_IES, NOME_DA_IES, SIGLA, CATEGORIA_DA_IES, COMUNITARIA,
    CONFESSIONAL, FILANTROPICA, ORGANIZACAO_ACADEMICA, CODIGO_MUNICIPIO_IBGE,
    MUNICIPIO, UF, SITUACAO_IES

Nada de Conceito Institucional, Conceito de Curso, IGC, credenciamento ou data de
avaliação. Esses vivem no sistema web do e-MEC, não no dado aberto. As quatro
ausências que os painéis declaram **continuam**, e o texto das páginas foi
corrigido para dizer o motivo certo: não é falta de acesso, é ausência na fonte
aberta.

**O serviço também está fora.** O endpoint OData do MEC responde HTTP 500 em todas
as entidades, com `FATAL: password authentication failed for user "sysolindamec"`
— falha de credencial do banco do lado deles. O `$metadata` responde porque é
estático, e foi por isso que deu para inspecionar os campos mesmo com o serviço
caído.

**O que ainda vale ingerir quando voltar:** `SITUACAO_IES`, que o Censo não traz —
se a instituição segue ativa ou foi extinta. E, pela entidade de cursos,
`SITUACAO_CURSO` e `QT_VAGAS_AUTORIZADAS`: a visão **regulatória** (o que o MEC
autorizou) contra a do Censo (o que a instituição declarou ofertar). O confronto
interessa justamente porque as duas podem divergir.

A descoberta da URL real veio da API do dados.gov.br; os dados em si estão num
OData público do MEC, que não exige chave. Ou seja: a chave foi útil para achar e
verificar, não para baixar.

