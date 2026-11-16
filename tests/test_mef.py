import pytest

from testes_mef.experimento import benchmark
from testes_mef.mef import MEF, gerar_aleatoria, remover_prefixos, sequencia_distinguidora


def venda() -> MEF:
    return next(m for m in benchmark() if m.nome == "maquina_venda")


def test_executar_produz_saidas_da_especificacao():
    m = venda()
    assert m.executar(["moeda1", "moeda2"]) == ["nada", "produto"]
    assert m.executar(["moeda2", "moeda2"]) == ["nada", "produto_troco1"]


def test_cobertura_de_estados_usa_sequencias_mais_curtas():
    p = venda().cobertura_de_estados()
    assert p == {"credito0": (), "credito1": ("moeda1",), "credito2": ("moeda2",)}


def test_ida_e_volta_em_dict():
    m = venda()
    assert MEF.de_dict(m.para_dict()).delta == m.delta


def _minima(delta, estados=("A", "B"), entradas=("x",)):
    return MEF("t", estados, entradas, "A", delta)


def test_detecta_transicao_indefinida():
    m = _minima({("A", "x"): ("B", "0")})
    assert any("indefinida" in e for e in m.problemas())


def test_detecta_estado_inalcancavel():
    m = _minima({("A", "x"): ("A", "0"), ("B", "x"): ("A", "1")})
    assert any("inalcançáveis" in e for e in m.problemas())


def test_detecta_mef_nao_minimal():
    m = _minima({("A", "x"): ("B", "0"), ("B", "x"): ("A", "0")})
    assert any("equivalentes" in e for e in m.problemas())
    with pytest.raises(ValueError):
        m.validar()


def test_nao_deterministica_e_rejeitada():
    dados = venda().para_dict()
    dados["transicoes"].append(dict(dados["transicoes"][0], para="credito2"))
    with pytest.raises(ValueError, match="determinística"):
        MEF.de_dict(dados)


def test_sequencia_distinguidora_realmente_distingue():
    m = gerar_aleatoria(8, 3, 2, semente=7)
    for i, s1 in enumerate(m.estados):
        for s2 in m.estados[i + 1 :]:
            seq = sequencia_distinguidora(m, s1, m, s2)
            assert seq is not None and m.executar(seq, de=s1) != m.executar(seq, de=s2)


def test_remover_prefixos():
    assert remover_prefixos([("a",), ("a", "b"), ("a", "b"), (), ("b",)]) == [("a", "b"), ("b",)]


@pytest.mark.parametrize("semente", range(20))
def test_gerador_aleatorio_produz_mef_valida(semente):
    m = gerar_aleatoria(6, 2, 2, semente)
    assert m.problemas() == []


def test_gerador_aleatorio_e_reprodutivel():
    assert gerar_aleatoria(8, 3, 2, 1).delta == gerar_aleatoria(8, 3, 2, 1).delta


def test_benchmark_tem_13_mefs_validas():
    mefs = benchmark()
    assert len(mefs) == 13 and all(m.problemas() == [] for m in mefs)
