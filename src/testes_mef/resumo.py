"""Junta os resultados em tabelas Markdown.

    python -m testes_mef.resumo [--detalhado]

As médias de cada modelo são calculadas SÓ sobre as MEFs que o modelo concluiu, e os
métodos clássicos entram na mesma tabela restritos a essas MEFs, para comparar igual com igual.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ORDEM = ["metodo_w", "cobertura_transicoes", "aleatorio_custo_w", "llm", "llm_feedback", "aleatorio_custo_llm"]
NOMES = {
    "metodo_w": "Método W (clássico)",
    "cobertura_transicoes": "Cobertura de transições (clássico)",
    "aleatorio_custo_w": "Aleatório, mesmo custo do W",
    "llm": "LLM, 1 rodada",
    "llm_feedback": "LLM + feedback de cobertura",
    "aleatorio_custo_llm": "Aleatório, mesmo custo do LLM",
}


def carregar(pasta: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    classicos, por_modelo = [], defaultdict(list)
    for arq in sorted(pasta.glob("*.jsonl")):
        if arq.name.endswith(".testes.jsonl"):
            continue
        for linha in arq.read_text("utf-8").splitlines():
            d = json.loads(linha)
            if "metodo" not in d:
                continue  # linha de erro de infraestrutura
            if d["metodo"] in ("metodo_w", "cobertura_transicoes", "aleatorio_custo_w"):
                classicos.append(d)
            else:
                por_modelo[d["modelo"]].append(d)
    return classicos, por_modelo


def _pct(x: float) -> str:
    return f"{x:.0%}"


def tabela(linhas: list[dict]) -> str:
    grupos = defaultdict(list)
    for d in linhas:
        grupos[d["metodo"]].append(d)
    out = [
        "| Método | MEFs | Cobertura de transições | Escore de mutação | Falhas de saída | Falhas de transferência | Entradas por conjunto | Tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for metodo in [m for m in ORDEM if m in grupos]:
        g = grupos[metodo]
        tokens = [d["tokens"] for d in g if "tokens" in d]
        transf = [d["escore_transferencia"] for d in g if d["escore_transferencia"] is not None]
        saida = [d["escore_saida"] for d in g if d["escore_saida"] is not None]
        out.append(
            f"| {NOMES[metodo]} | {len(g)} | {_pct(mean(d['cobertura_transicoes'] for d in g))} "
            f"| {_pct(mean(d['escore_mutacao'] for d in g))} | {_pct(mean(saida)) if saida else '-'} "
            f"| {_pct(mean(transf)) if transf else '-'} | {mean(d['entradas_totais'] for d in g):.0f} "
            f"| {f'{mean(tokens):.0f}' if tokens else '-'} |"
        )
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pasta", default="resultados")
    p.add_argument("--detalhado", action="store_true", help="Também mostra o resultado por MEF")
    a = p.parse_args()
    classicos, por_modelo = carregar(Path(a.pasta))
    if not por_modelo:
        print("## Métodos clássicos (todas as MEFs)\n")
        print(tabela(classicos))
    for modelo, linhas in sorted(por_modelo.items()):
        mefs = {d["mef"] for d in linhas}
        print(f"\n## `{modelo}` ({len(mefs)} MEFs concluídas)\n")
        print(tabela([d for d in classicos if d["mef"] in mefs] + linhas))
        if a.detalhado:
            print("\n| MEF | Método | Cobertura | Mutação | Entradas |\n|---|---|---|---|---|")
            for d in sorted(
                [d for d in classicos if d["mef"] in mefs] + linhas, key=lambda d: (d["mef"], ORDEM.index(d["metodo"]))
            ):
                print(
                    f"| {d['mef']} | {NOMES[d['metodo']]} | {_pct(d['cobertura_transicoes'])} "
                    f"| {_pct(d['escore_mutacao'])} | {d['entradas_totais']} |"
                )


if __name__ == "__main__":
    main()
