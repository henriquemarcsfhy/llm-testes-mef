import json

import pytest

from testes_mef.experimento import benchmark, rodar_llm
from testes_mef.llm import ClienteRoteirizado, descrever, extrair_testes, gerar_com_llm
from testes_mef.resumo import carregar, tabela

VENDA = next(m for m in benchmark() if m.nome == "maquina_venda")
ENTRADAS = VENDA.entradas


@pytest.mark.parametrize(
    "texto",
    [
        '{"testes": [["moeda1", "moeda2"]]}',
        'Claro!\n```json\n{"testes": [["moeda1", "moeda2"]]}\n```',
        '<think>vou pensar {"testes": []}</think>{"testes": [["moeda1", "moeda2"]]}',
        '{"testes": ["moeda1 moeda2"]}',
    ],
)
def test_extrai_testes_de_formatos_variados(texto):
    assert extrair_testes(texto, ENTRADAS).testes == [("moeda1", "moeda2")]


def test_descarta_testes_com_entrada_inexistente():
    p = extrair_testes('{"testes": [["moeda1"], ["moeda5"], [], 3]}', ENTRADAS)
    assert p.testes == [("moeda1",)] and p.invalidos == 3


@pytest.mark.parametrize("texto", [None, "", "sem json", '{"outra": 1}', '{"testes": [["moeda1"]'])
def test_resposta_inutilizavel_vira_erro_e_nao_excecao(texto):
    p = extrair_testes(texto, ENTRADAS)
    assert p.testes == [] and p.erro


def test_prompt_traz_a_tabela_completa():
    texto = descrever(VENDA)
    for (s, a), (d, o) in VENDA.delta.items():
        assert f"{s} --{a}/{o}--> {d}" in texto


def test_feedback_lista_so_as_transicoes_faltando():
    parcial = json.dumps({"testes": [["moeda1"]]})
    cliente = ClienteRoteirizado([parcial, '{"testes": []}', '{"testes": []}'])
    r = gerar_com_llm(VENDA, cliente, rodadas_feedback=2)
    feedback = cliente.chamadas[1][-1]["content"]
    assert "estado credito0, entrada moeda1" not in feedback
    assert "estado credito0, entrada moeda2" in feedback
    assert len(r.rodadas) == 3 and r.tokens == 45


def test_para_quando_a_cobertura_fica_completa():
    from testes_mef.metodos import cobertura_de_transicoes

    completo = json.dumps({"testes": [list(t) for t in cobertura_de_transicoes(VENDA)]})
    cliente = ClienteRoteirizado([completo])
    r = gerar_com_llm(VENDA, cliente, rodadas_feedback=2)
    assert len(cliente.chamadas) == 1
    assert r.testes_primeira_rodada == r.testes_finais


def test_feedback_acumula_testes_das_rodadas():
    cliente = ClienteRoteirizado(['{"testes": [["moeda1"]]}', '{"testes": [["moeda2"]]}'])
    r = gerar_com_llm(VENDA, cliente, rodadas_feedback=1)
    assert r.testes_primeira_rodada == [("moeda1",)]
    assert r.testes_finais == [("moeda1",), ("moeda2",)]


def test_experimento_grava_resultados_e_resumo(tmp_path):
    from testes_mef.experimento import rodar_classicos

    saida = tmp_path / "llm_falso.jsonl"
    (tmp_path / "classicos.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rodar_classicos([VENDA])), "utf-8")
    rodar_llm([VENDA], ClienteRoteirizado(['{"testes": [["moeda1", "moeda2"]]}'] * 3), "falso", 2, saida)
    linhas = [json.loads(x) for x in saida.read_text().splitlines()]
    assert [x["metodo"] for x in linhas] == ["llm", "llm_feedback", "aleatorio_custo_llm"]
    assert (tmp_path / "llm_falso.testes.jsonl").exists()
    classicos, por_modelo = carregar(tmp_path)
    t = tabela(classicos + por_modelo["falso"])
    assert "Método W" in t and "LLM + feedback" in t


def test_limite_de_taxa_interrompe_o_experimento(tmp_path):
    class RateLimitError(Exception):
        pass

    def estoura(_):
        raise RateLimitError("tokens per day")

    saida = tmp_path / "x.jsonl"
    mefs = benchmark()[:3]
    cliente = ClienteRoteirizado([estoura, '{"testes": []}'])
    rodar_llm(mefs, cliente, "m", 0, saida)
    linhas = [json.loads(x) for x in saida.read_text().splitlines()]
    assert len(linhas) == 1 and linhas[0]["erro_infra"]
    assert len(cliente.chamadas) == 1  # parou em vez de queimar as próximas MEFs


def test_analise_reconhece_a_cobertura_de_transicoes(tmp_path):
    from testes_mef.analise import comparar
    from testes_mef.metodos import cobertura_de_transicoes

    arq = tmp_path / "x.testes.jsonl"
    arq.write_text(
        json.dumps({"mef": "maquina_venda", "testes_finais": [list(t) for t in cobertura_de_transicoes(VENDA)]})
        + "\n"
        + json.dumps({"mef": "pedido_delivery", "testes_finais": [["pagar"]]})
        + "\n",
        "utf-8",
    )
    r = comparar(arq)
    assert r[0]["identico"] and not r[1]["identico"]
