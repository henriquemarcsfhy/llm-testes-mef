"""Máquinas de estados finitos de Mealy: representação, execução e análise.

Convenções (as usuais em teste baseado em MEF):
- a MEF é determinística, completa (toda entrada é definida em todo estado) e
  inicialmente conexa (todo estado é alcançável a partir do inicial);
- um caso de teste é uma sequência de entradas aplicada a partir do estado
  inicial, após um reset; o veredito compara as sequências de saída.
"""

from __future__ import annotations

import json
import random
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

Transicao = tuple[str, str]  # (estado, entrada)
Seq = tuple[str, ...]


@dataclass
class MEF:
    nome: str
    estados: tuple[str, ...]
    entradas: tuple[str, ...]
    inicial: str
    # (estado, entrada) -> (destino, saída)
    delta: dict[Transicao, tuple[str, str]]
    descricao: str = ""
    saidas: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.saidas:
            self.saidas = tuple(sorted({s for _, s in self.delta.values()}))

    # ---------- execução ----------

    def passo(self, estado: str, entrada: str) -> tuple[str, str]:
        return self.delta[(estado, entrada)]

    def executar(self, seq: Sequence[str], de: str | None = None) -> list[str]:
        """Saídas produzidas por `seq` a partir de `de` (padrão: estado inicial)."""
        estado = self.inicial if de is None else de
        saidas = []
        for entrada in seq:
            estado, saida = self.delta[(estado, entrada)]
            saidas.append(saida)
        return saidas

    def transicoes_percorridas(self, seq: Sequence[str]) -> list[Transicao]:
        estado, percorridas = self.inicial, []
        for entrada in seq:
            percorridas.append((estado, entrada))
            estado = self.delta[(estado, entrada)][0]
        return percorridas

    # ---------- validação ----------

    def problemas(self) -> list[str]:
        erros = []
        if self.inicial not in self.estados:
            erros.append(f"estado inicial '{self.inicial}' não existe")
        for s in self.estados:
            for a in self.entradas:
                if (s, a) not in self.delta:
                    erros.append(f"transição indefinida: ({s}, {a})")
        for (s, a), (d, _) in self.delta.items():
            if s not in self.estados or a not in self.entradas or d not in self.estados:
                erros.append(f"transição inválida: ({s}, {a}) -> {d}")
        if not erros:
            inalcancaveis = set(self.estados) - set(self.cobertura_de_estados())
            if inalcancaveis:
                erros.append(f"estados inalcançáveis: {sorted(inalcancaveis)}")
            for s1, s2 in self._pares_equivalentes():
                erros.append(f"estados equivalentes (MEF não minimal): {s1} e {s2}")
        return erros

    def validar(self) -> MEF:
        erros = self.problemas()
        if erros:
            raise ValueError(f"MEF '{self.nome}' inválida: " + "; ".join(erros))
        return self

    def _pares_equivalentes(self):
        for i, s1 in enumerate(self.estados):
            for s2 in self.estados[i + 1 :]:
                if sequencia_distinguidora(self, s1, self, s2) is None:
                    yield s1, s2

    # ---------- estruturas clássicas ----------

    def cobertura_de_estados(self) -> dict[str, Seq]:
        """Sequência de acesso mais curta para cada estado (conjunto P), por BFS."""
        acesso: dict[str, Seq] = {self.inicial: ()}
        fila = deque([self.inicial])
        while fila:
            s = fila.popleft()
            for a in self.entradas:
                d = self.delta[(s, a)][0]
                if d not in acesso:
                    acesso[d] = acesso[s] + (a,)
                    fila.append(d)
        return acesso

    # ---------- E/S ----------

    def para_dict(self) -> dict:
        return {
            "nome": self.nome,
            "descricao": self.descricao,
            "estados": list(self.estados),
            "entradas": list(self.entradas),
            "inicial": self.inicial,
            "transicoes": [
                {"de": s, "entrada": a, "para": d, "saida": o}
                for s in self.estados
                for a in self.entradas
                for d, o in [self.delta[(s, a)]]
            ],
        }

    @classmethod
    def de_dict(cls, dados: dict) -> MEF:
        delta = {}
        for t in dados["transicoes"]:
            chave = (t["de"], t["entrada"])
            if chave in delta:
                raise ValueError(f"MEF não determinística em {chave}")
            delta[chave] = (t["para"], t["saida"])
        return cls(
            nome=dados["nome"],
            descricao=dados.get("descricao", ""),
            estados=tuple(dados["estados"]),
            entradas=tuple(dados["entradas"]),
            inicial=dados["inicial"],
            delta=delta,
        )

    @classmethod
    def carregar(cls, caminho: str | Path) -> MEF:
        return cls.de_dict(json.loads(Path(caminho).read_text("utf-8"))).validar()

    def copiar_com(self, chave: Transicao, destino: str, saida: str, nome: str) -> MEF:
        delta = dict(self.delta)
        delta[chave] = (destino, saida)
        return MEF(nome, self.estados, self.entradas, self.inicial, delta, self.descricao, self.saidas)


def sequencia_distinguidora(m1: MEF, s1: str, m2: MEF, s2: str) -> Seq | None:
    """Sequência de entradas mais curta cujas saídas diferem partindo de (m1, s1) e (m2, s2).

    BFS no produto das duas máquinas. `None` = os estados são equivalentes.
    Requer o mesmo alfabeto de entrada.
    """
    inicio = (s1, s2)
    anterior: dict[tuple[str, str], tuple[tuple[str, str], str] | None] = {inicio: None}
    fila = deque([inicio])
    while fila:
        par = fila.popleft()
        a1, a2 = par
        for entrada in m1.entradas:
            d1, o1 = m1.delta[(a1, entrada)]
            d2, o2 = m2.delta[(a2, entrada)]
            if o1 != o2:
                seq = [entrada]
                cursor = par
                while anterior[cursor] is not None:
                    cursor, e = anterior[cursor]
                    seq.append(e)
                return tuple(reversed(seq))
            prox = (d1, d2)
            if prox not in anterior:
                anterior[prox] = (par, entrada)
                fila.append(prox)
    return None


def remover_prefixos(testes: Iterable[Seq]) -> list[Seq]:
    """Remove testes vazios, duplicados e prefixos de outros testes (já executados por eles)."""
    unicos = sorted({tuple(t) for t in testes if t}, key=lambda t: (-len(t), t))
    mantidos: list[Seq] = []
    for t in unicos:
        if not any(m[: len(t)] == t for m in mantidos):
            mantidos.append(t)
    return sorted(mantidos)


def gerar_aleatoria(n_estados: int, n_entradas: int, n_saidas: int, semente: int, max_tentativas: int = 500) -> MEF:
    """MEF de Mealy aleatória, completa, inicialmente conexa e minimal (reamostra até conseguir)."""
    rng = random.Random(semente)
    estados = tuple(f"s{i}" for i in range(n_estados))
    entradas = tuple("abcdefgh"[:n_entradas])
    saidas = tuple(str(i) for i in range(n_saidas))
    for _ in range(max_tentativas):
        delta: dict[Transicao, tuple[str, str]] = {}
        # Árvore geradora a partir de s0 garante que todo estado é alcançável.
        livres = [(estados[0], a) for a in entradas]
        for novo in estados[1:]:
            chave = livres.pop(rng.randrange(len(livres)))
            delta[chave] = (novo, rng.choice(saidas))
            livres.extend((novo, a) for a in entradas)
        for chave in livres:
            delta[chave] = (rng.choice(estados), rng.choice(saidas))
        mef = MEF(f"aleatoria_n{n_estados}_e{n_entradas}_s{n_saidas}_r{semente}", estados, entradas, "s0", delta)
        mef.descricao = f"MEF aleatória com {n_estados} estados, {n_entradas} entradas e {n_saidas} saídas."
        if not mef.problemas():
            return mef
    raise RuntimeError("não foi possível gerar MEF minimal; aumente o número de saídas")
