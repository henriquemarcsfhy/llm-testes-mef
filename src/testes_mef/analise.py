"""Compara os testes de um LLM com o conjunto de cobertura de transições clássico.

    python -m testes_mef.analise resultados/llm_<modelo>_<data>.testes.jsonl

Responde: o LLM inventou uma estratégia própria ou reproduziu a de livro-texto?
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .experimento import benchmark
from .metodos import cobertura_de_transicoes


def comparar(caminho: Path) -> list[dict]:
    mefs = {m.nome: m for m in benchmark()}
    linhas = []
    for bruto in caminho.read_text("utf-8").splitlines():
        d = json.loads(bruto)
        mef = mefs[d["mef"]]
        llm = {tuple(t) for t in d["testes_finais"]}
        q = set(cobertura_de_transicoes(mef))
        linhas.append(
            {
                "mef": d["mef"],
                "identico": llm == q,
                "em_comum": len(llm & q),
                "so_llm": len(llm - q),
                "so_cobertura": len(q - llm),
            }
        )
    return linhas


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("arquivo", type=Path, help="Arquivo *.testes.jsonl de uma execução com LLM")
    linhas = comparar(p.parse_args().arquivo)
    print("| MEF | Idêntico à cobertura de transições | Testes em comum | Só do LLM | Só da cobertura |")
    print("|---|---|---|---|---|")
    for x in linhas:
        print(
            f"| {x['mef']} | {'sim' if x['identico'] else 'não'} | {x['em_comum']} | {x['so_llm']} | {x['so_cobertura']} |"
        )
    print(f"\nIdênticos: {sum(x['identico'] for x in linhas)} de {len(linhas)}")


if __name__ == "__main__":
    main()
