import pytest

from testes_mef.experimento import benchmark
from testes_mef.mef import gerar_aleatoria, sequencia_distinguidora
from testes_mef.metodos import (
    avaliar,
    cobertura,
    cobertura_de_transicoes,
    conjunto_caracterizacao,
    gerar_mutantes,
    mata,
    metodo_w,
    passeio_aleatorio,
)

MEFS = benchmark()


@pytest.mark.parametrize("mef", MEFS, ids=lambda m: m.nome)
def test_cobertura_de_transicoes_percorre_tudo(mef):
    assert cobertura(mef, cobertura_de_transicoes(mef)) == 1.0


@pytest.mark.parametrize("mef", MEFS, ids=lambda m: m.nome)
def test_metodo_w_mata_todos_os_mutantes(mef):
    """Teorema do método W: com m = n, detecta toda falha de saída e de transferência."""
    assert avaliar(mef, metodo_w(mef)).escore_mutacao == 1.0


@pytest.mark.parametrize("semente", range(15))
def test_metodo_w_completo_em_mefs_aleatorias(semente):
    mef = gerar_aleatoria(7, 3, 2, semente=100 + semente)
    assert avaliar(mef, metodo_w(mef)).escore_mutacao == 1.0


def test_w_distingue_todo_par_de_estados():
    mef = next(m for m in MEFS if m.nome == "pedido_delivery")
    w = conjunto_caracterizacao(mef)
    for i, s1 in enumerate(mef.estados):
        for s2 in mef.estados[i + 1 :]:
            assert any(mef.executar(seq, de=s1) != mef.executar(seq, de=s2) for seq in w)


def test_nenhum_mutante_e_equivalente():
    mef = MEFS[0]
    for m in gerar_mutantes(mef):
        assert sequencia_distinguidora(mef, mef.inicial, m.mef, m.mef.inicial) is not None


def test_mutantes_mudam_uma_unica_transicao():
    mef = MEFS[0]
    for m in gerar_mutantes(mef):
        diferentes = [k for k in mef.delta if mef.delta[k] != m.mef.delta[k]]
        assert diferentes == [m.transicao]


def test_conjunto_vazio_nao_mata_nada():
    mef = MEFS[0]
    r = avaliar(mef, [])
    assert r.mortos == 0 and r.cobertura_transicoes == 0


def test_mata_compara_saidas():
    mef = next(m for m in MEFS if m.nome == "maquina_venda")
    erro_produto = mef.copiar_com(("credito1", "moeda2"), "credito0", "nada", "mutante")
    assert mata(mef, erro_produto, [("moeda1", "moeda2")])
    assert not mata(mef, erro_produto, [("moeda2",)])


def test_aleatorio_respeita_orcamento_e_semente():
    mef = MEFS[0]
    a = passeio_aleatorio(mef, 50, semente=3)
    assert a == passeio_aleatorio(mef, 50, semente=3)
    assert sum(map(len, a)) <= 50


def test_cobertura_de_transicoes_nao_garante_falhas_de_transferencia():
    """O ponto central do estudo: 100% de cobertura não implica detectar todas as falhas."""
    mef = next(m for m in MEFS if m.nome == "pedido_delivery")
    r = avaliar(mef, cobertura_de_transicoes(mef))
    assert r.cobertura_transicoes == 1.0
    assert r.mortos_transferencia < r.total_transferencia
