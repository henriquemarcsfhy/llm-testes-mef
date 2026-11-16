"""Geração de testes a partir de máquinas de estados finitos: métodos clássicos vs. LLMs."""

from .mef import MEF, gerar_aleatoria, remover_prefixos, sequencia_distinguidora
from .metodos import avaliar, cobertura_de_transicoes, gerar_mutantes, metodo_w, passeio_aleatorio

__all__ = [
    "MEF",
    "avaliar",
    "cobertura_de_transicoes",
    "gerar_aleatoria",
    "gerar_mutantes",
    "metodo_w",
    "passeio_aleatorio",
    "remover_prefixos",
    "sequencia_distinguidora",
]

__version__ = "0.1.0"
