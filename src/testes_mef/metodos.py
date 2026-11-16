"""Métodos clássicos de geração de testes e métricas de qualidade de um conjunto de testes."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .mef import MEF, Seq, remover_prefixos, sequencia_distinguidora

# ---------- geração clássica ----------


def cobertura_de_transicoes(mef: MEF) -> list[Seq]:
    """Conjunto Q = P · ({ε} ∪ Σ): percorre toda transição ao menos uma vez.

    Garante 100% de cobertura de transições, mas não verifica o estado de destino,
    então não detecta todas as falhas de transferência.
    """
    p = mef.cobertura_de_estados()
    return remover_prefixos(acesso + (a,) for acesso in p.values() for a in mef.entradas)


def conjunto_caracterizacao(mef: MEF) -> list[Seq]:
    """Conjunto W: para cada par de estados, uma sequência mais curta que os distingue."""
    w = set()
    for i, s1 in enumerate(mef.estados):
        for s2 in mef.estados[i + 1 :]:
            seq = sequencia_distinguidora(mef, s1, mef, s2)
            if seq is None:
                raise ValueError(f"MEF não minimal: {s1} e {s2} são equivalentes")
            w.add(seq)
    return sorted(w, key=lambda s: (len(s), s))


def metodo_w(mef: MEF) -> list[Seq]:
    """Método W (Chow, 1978) supondo que a implementação tem no máximo n estados.

    T = P · ({ε} ∪ Σ) · W. Para MEFs minimais e completas, detecta TODA falha de
    saída e de transferência que não aumente o número de estados.
    """
    p = list(mef.cobertura_de_estados().values())
    q = p + [acesso + (a,) for acesso in p for a in mef.entradas]
    w = conjunto_caracterizacao(mef) or [()]
    return remover_prefixos(seq + sufixo for seq in q for sufixo in w)


def passeio_aleatorio(mef: MEF, orcamento: int, semente: int, comprimento_max: int | None = None) -> list[Seq]:
    """Testes aleatórios até gastar `orcamento` entradas no total (linha de base)."""
    rng = random.Random(semente)
    comprimento_max = comprimento_max or max(2, 2 * len(mef.estados))
    testes, gasto = [], 0
    while gasto < orcamento:
        n = min(rng.randint(1, comprimento_max), orcamento - gasto)
        testes.append(tuple(rng.choice(mef.entradas) for _ in range(n)))
        gasto += n
    return remover_prefixos(testes)


# ---------- mutantes ----------


@dataclass(frozen=True)
class Mutante:
    tipo: str  # "saida" | "transferencia"
    transicao: tuple[str, str]
    mef: MEF


def gerar_mutantes(mef: MEF) -> list[Mutante]:
    """Todos os mutantes de falha única de saída e de transferência, sem equivalentes.

    Mutantes equivalentes à especificação são descartados (nenhum teste os mata).
    """
    mutantes = []
    for chave, (destino, saida) in mef.delta.items():
        candidatos = [("saida", destino, o) for o in mef.saidas if o != saida]
        candidatos += [("transferencia", d, saida) for d in mef.estados if d != destino]
        for tipo, novo_destino, nova_saida in candidatos:
            nome = f"{mef.nome}~{tipo}:{chave[0]}/{chave[1]}->{novo_destino}/{nova_saida}"
            m = mef.copiar_com(chave, novo_destino, nova_saida, nome)
            if sequencia_distinguidora(mef, mef.inicial, m, m.inicial) is not None:
                mutantes.append(Mutante(tipo, chave, m))
    return mutantes


# ---------- métricas ----------


@dataclass
class Metricas:
    n_testes: int
    entradas_totais: int
    cobertura_transicoes: float
    mutantes: int
    mortos: int
    mortos_saida: int
    total_saida: int
    mortos_transferencia: int
    total_transferencia: int

    @property
    def escore_mutacao(self) -> float:
        return self.mortos / self.mutantes if self.mutantes else 1.0

    def como_dict(self) -> dict:
        return {
            "n_testes": self.n_testes,
            "entradas_totais": self.entradas_totais,
            "cobertura_transicoes": round(self.cobertura_transicoes, 4),
            "escore_mutacao": round(self.escore_mutacao, 4),
            "escore_saida": round(self.mortos_saida / self.total_saida, 4) if self.total_saida else None,
            "escore_transferencia": round(self.mortos_transferencia / self.total_transferencia, 4)
            if self.total_transferencia
            else None,
            "mutantes": self.mutantes,
        }


def cobertura(mef: MEF, testes: Sequence[Seq]) -> float:
    percorridas = {t for seq in testes for t in mef.transicoes_percorridas(seq)}
    return len(percorridas) / len(mef.delta)


def mata(mef: MEF, mutante: MEF, testes: Sequence[Seq]) -> bool:
    return any(mef.executar(t) != mutante.executar(t) for t in testes)


def avaliar(mef: MEF, testes: Sequence[Seq], mutantes: Sequence[Mutante] | None = None) -> Metricas:
    mutantes = gerar_mutantes(mef) if mutantes is None else mutantes
    mortos = [m for m in mutantes if mata(mef, m.mef, testes)]
    return Metricas(
        n_testes=len(testes),
        entradas_totais=sum(len(t) for t in testes),
        cobertura_transicoes=cobertura(mef, testes),
        mutantes=len(mutantes),
        mortos=len(mortos),
        mortos_saida=sum(m.tipo == "saida" for m in mortos),
        total_saida=sum(m.tipo == "saida" for m in mutantes),
        mortos_transferencia=sum(m.tipo == "transferencia" for m in mortos),
        total_transferencia=sum(m.tipo == "transferencia" for m in mutantes),
    )
