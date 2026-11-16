# llm-testes-mef

**Um LLM consegue gerar bons casos de teste a partir de uma máquina de estados finitos?** Este projeto compara testes gerados por LLMs com métodos clássicos de teste baseado em modelos (método W e cobertura de transições). A medida principal é **quantas falhas cada conjunto de testes detecta** (escore de mutação), não só quanto ele cobre.

![CI](https://github.com/henriquemarcsfhy/llm-testes-mef/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> **TL;DR (EN):** Can LLMs generate good test suites from a Mealy finite state machine? This repo compares LLM-generated tests (zero-shot, and with coverage feedback) against the classic W-method, transition coverage, and random testing at equal cost, on 13 FSMs. Suites are judged by **mutation score** over all single output and transfer faults, not only by transition coverage. Everything except the LLM calls runs offline and is covered by 95 tests.

## Pergunta de pesquisa

Em teste baseado em MEFs, há um resultado clássico: o **método W** (Chow, 1978) gera um conjunto de testes que detecta **toda** falha de saída e de transferência, desde que a implementação não tenha mais estados que a especificação. O custo é o tamanho: o conjunto cresce rápido com o número de estados.

LLMs conseguem ler a especificação e propor testes em segundos. Este projeto investiga:

1. Os testes do LLM **cobrem** a máquina? (cobertura de transições)
2. Eles **detectam falhas**? (escore de mutação, separado por falhas de saída e de transferência)
3. Valem mais que **testes aleatórios com o mesmo número de entradas**?
4. Dar ao LLM o retorno de uma **ferramenta de cobertura** ajuda?

## Por que cobertura não basta

Os resultados clássicos já mostram o ponto central do estudo:

| Método | MEFs | Cobertura de transições | Escore de mutação | Falhas de saída | Falhas de transferência | Entradas por conjunto |
|---|---|---|---|---|---|---|
| Método W | 13 | 100% | **100%** | 100% | 100% | 145 |
| Cobertura de transições | 13 | **100%** | 50% | 100% | **28%** | 33 |
| Aleatório, mesmo custo do W | 13 | 95% | 92% | 95% | 91% | 132 |

Um conjunto que passa por **todas** as transições detecta, em média, só **28% das falhas de transferência**: ele percorre a transição, mas nunca confere se ela levou ao estado certo. E testes aleatórios do mesmo tamanho que o W chegam a 92%. Por isso, um conjunto gerado por LLM com "100% de cobertura" pode ainda ser fraco, e o aleatório de mesmo custo é a linha de base que importa.

## Resultados com LLMs

<!-- Gerado por: python -m testes_mef.resumo -->

_Em execução._ As médias de cada modelo são calculadas só sobre as MEFs que ele concluiu, e os métodos clássicos entram na mesma tabela restritos a essas MEFs.

## Método

**Especificações (13 MEFs de Mealy, completas, determinísticas, inicialmente conexas e minimais):**
- 3 realistas, escritas à mão: [ciclo de um pedido de delivery](src/testes_mef/benchmarks/pedido_delivery.json) (6 estados), [máquina de venda](src/testes_mef/benchmarks/maquina_venda.json) (3) e [fechadura com senha](src/testes_mef/benchmarks/fechadura_senha.json) (4);
- 10 aleatórias, de 4 a 10 estados e 2 a 3 entradas, geradas com semente fixa ([`experimento.py`](src/testes_mef/experimento.py)).

**Métodos comparados:**

| Método | Como gera os testes |
|---|---|
| Método W | P · ({ε} ∪ Σ) · W, com P = cobertura de estados e W = conjunto de caracterização |
| Cobertura de transições | P · ({ε} ∪ Σ): cada transição percorrida ao menos uma vez |
| Aleatório, mesmo custo do W / do LLM | Sequências aleatórias até gastar o mesmo número total de entradas |
| LLM, 1 rodada | O modelo recebe a tabela de transições e devolve testes em JSON |
| LLM + feedback de cobertura | Até 2 rodadas extras informando as transições não percorridas. O modelo **nunca** vê os mutantes |

**Modelo de falhas:** todos os mutantes de falha única, de **saída** (trocar a saída de uma transição) e de **transferência** (trocar o destino). Mutantes equivalentes à especificação são descartados por busca no produto das máquinas. Um teste mata um mutante se as sequências de saída diferem.

**Métricas:** cobertura de transições, escore de mutação (total, de saída e de transferência), número de entradas do conjunto (custo de execução), tokens gastos e respostas inválidas do modelo (entradas inexistentes ou JSON quebrado).

**Garantias testadas:** o método W mata 100% dos mutantes em todas as MEFs do benchmark e em 15 MEFs aleatórias extras (teorema de Chow, verificado em [`test_metodos.py`](tests/test_metodos.py)). Nenhum mutante equivalente entra na conta, e cada mutante difere da especificação em exatamente uma transição.

## Como rodar

```bash
git clone https://github.com/henriquemarcsfhy/llm-testes-mef && cd llm-testes-mef
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest -q                                            # 95 testes, sem LLM
python -m testes_mef.experimento --metodos classicos # segundos, sem LLM

# LLM via Groq (plano gratuito) ou qualquer API compatível com OpenAI
export LLM_API_KEY=gsk_...                           # Windows: $env:LLM_API_KEY="gsk_..."
python -m testes_mef.experimento --metodos llm --base-url https://api.groq.com/openai/v1 --modelo openai/gpt-oss-120b
python -m testes_mef.resumo --detalhado
```

Se o limite diário de tokens estourar no meio, o experimento para e mostra como continuar: `--retomar resultados/<arquivo>.jsonl`. Os testes gerados e as respostas brutas do modelo ficam em `resultados/*.testes.jsonl`, para auditoria.

## Limitações

- **Hipótese de m = n:** o método W e os mutantes assumem que a implementação não tem estados extras. Falhas que adicionam estados ficam fora do estudo.
- **Mutantes de falha única:** são o padrão da literatura, mas não representam todas as falhas reais.
- **Benchmark pequeno** (13 MEFs, até 10 estados), escolhido para caber no plano gratuito de APIs. As conclusões valem para máquinas desse porte.
- **Uma execução por modelo, com temperatura 0:** não mede a variância entre execuções.

## Estrutura

```
src/testes_mef/
  mef.py          # MEF de Mealy: execução, validação, sequências distinguidoras, gerador aleatório
  metodos.py      # método W, cobertura de transições, aleatório, mutantes e métricas
  llm.py          # prompt, leitura tolerante da resposta, rodadas com feedback de cobertura
  experimento.py  # benchmark e execução, com retomada
  resumo.py       # tabelas Markdown
  benchmarks/     # MEFs realistas em JSON
tests/            # 95 testes (pytest)
resultados/       # resultados brutos (JSONL)
```

## Referências

- T. S. Chow. *Testing Software Design Modeled by Finite-State Machines*. IEEE Transactions on Software Engineering, SE-4(3), 1978.
- D. Lee e M. Yannakakis. *Principles and Methods of Testing Finite State Machines: A Survey*. Proceedings of the IEEE, 84(8), 1996.
