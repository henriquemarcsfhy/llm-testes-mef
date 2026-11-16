"""Experimento: métodos clássicos vs. LLM na geração de testes a partir de MEFs.

    python -m testes_mef.experimento --metodos classicos
    python -m testes_mef.experimento --metodos llm --base-url https://api.groq.com/openai/v1 --modelo openai/gpt-oss-120b

Cada linha do resultado (JSONL) é um par (MEF, método). As execuções com LLM são salvas
MEF a MEF, então um limite de taxa no meio não perde o que já rodou: use --retomar.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from importlib import resources
from pathlib import Path

from .mef import MEF, gerar_aleatoria
from .metodos import avaliar, cobertura_de_transicoes, gerar_mutantes, metodo_w, passeio_aleatorio

# (estados, entradas, saídas, semente): tamanhos pequenos o bastante para caber no plano gratuito de um LLM.
CONFIG_ALEATORIAS = [
    (4, 2, 2, 1),
    (4, 2, 2, 2),
    (6, 2, 2, 1),
    (6, 2, 2, 2),
    (6, 3, 3, 1),
    (6, 3, 3, 2),
    (8, 3, 2, 1),
    (8, 3, 2, 2),
    (10, 3, 3, 1),
    (10, 3, 3, 2),
]

ERROS_DE_INFRA = {"RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError"}


def benchmark() -> list[MEF]:
    pasta = resources.files("testes_mef").joinpath("benchmarks")
    realistas = sorted(
        (MEF.de_dict(json.loads(f.read_text("utf-8"))).validar() for f in pasta.iterdir() if f.name.endswith(".json")),
        key=lambda m: m.nome,
    )
    return realistas + [gerar_aleatoria(*cfg) for cfg in CONFIG_ALEATORIAS]


def _linha(mef: MEF, metodo: str, testes, mutantes, **extra) -> dict:
    return {
        "mef": mef.nome,
        "n_estados": len(mef.estados),
        "n_entradas": len(mef.entradas),
        "n_transicoes": len(mef.delta),
        "metodo": metodo,
        **avaliar(mef, testes, mutantes).como_dict(),
        **extra,
    }


def rodar_classicos(mefs: list[MEF]) -> list[dict]:
    linhas = []
    for mef in mefs:
        mutantes = gerar_mutantes(mef)
        w = metodo_w(mef)
        custo_w = sum(len(t) for t in w)
        linhas.append(_linha(mef, "cobertura_transicoes", cobertura_de_transicoes(mef), mutantes))
        linhas.append(_linha(mef, "metodo_w", w, mutantes))
        linhas.append(_linha(mef, "aleatorio_custo_w", passeio_aleatorio(mef, custo_w, semente=0), mutantes))
    return linhas


def rodar_llm(mefs: list[MEF], cliente, modelo: str, rodadas_feedback: int, saida: Path) -> None:
    from .llm import gerar_com_llm

    for mef in mefs:
        inicio = time.perf_counter()
        try:
            r = gerar_com_llm(mef, cliente, rodadas_feedback)
        except Exception as e:
            nome = type(e).__name__
            _anexar(
                saida,
                {"mef": mef.nome, "modelo": modelo, "erro_infra": nome in ERROS_DE_INFRA, "erro": f"{nome}: {e}"[:500]},
            )
            print(f"[ERRO] {mef.nome}: {nome}. Pare aqui e use --retomar {saida} quando o limite liberar.")
            if nome in ERROS_DE_INFRA:
                return
            continue
        mutantes = gerar_mutantes(mef)
        custo_llm = sum(len(t) for t in r.testes_finais)
        comum = {
            "modelo": modelo,
            "latencia_s": round(time.perf_counter() - inicio, 1),
            "rodadas": len(r.rodadas),
            "invalidos": sum(x.invalidos for x in r.rodadas),
            "erros_parse": [x.erro for x in r.rodadas if x.erro],
        }
        linhas = [
            _linha(mef, "llm", r.testes_primeira_rodada, mutantes, tokens=r.tokens_primeira_rodada, **comum),
            _linha(mef, "llm_feedback", r.testes_finais, mutantes, tokens=r.tokens, **comum),
            _linha(
                mef,
                "aleatorio_custo_llm",
                passeio_aleatorio(mef, max(custo_llm, 1), semente=0),
                mutantes,
                modelo=modelo,
            ),
        ]
        for linha in linhas:
            _anexar(saida, linha)
        _anexar(
            saida.with_suffix(".testes.jsonl"),
            {"mef": mef.nome, "testes_finais": r.testes_finais, "respostas": r.respostas},
        )
        print(
            f"[OK] {mef.nome}: cobertura {linhas[1]['cobertura_transicoes']:.0%}, "
            f"mutação {linhas[1]['escore_mutacao']:.0%}, {r.tokens} tokens"
        )


def _anexar(caminho: Path, linha: dict) -> None:
    with caminho.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metodos", choices=["classicos", "llm"], required=True)
    p.add_argument("--modelo")
    p.add_argument("--base-url")
    p.add_argument("--rodadas-feedback", type=int, default=2)
    p.add_argument("--limite", type=int, help="Usa só as N primeiras MEFs (para economizar tokens)")
    p.add_argument("--retomar", metavar="ARQUIVO.jsonl", help="Continua uma execução com LLM, pulando MEFs já feitas")
    p.add_argument("--saida-dir", default="resultados")
    a = p.parse_args()

    mefs = benchmark()[: a.limite] if a.limite else benchmark()
    pasta = Path(a.saida_dir)
    pasta.mkdir(exist_ok=True)

    if a.metodos == "classicos":
        caminho = pasta / "classicos.jsonl"
        caminho.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rodar_classicos(mefs)), "utf-8")
        print(f"Resultados em {caminho}")
        return

    if not a.modelo:
        p.error("--modelo é obrigatório com --metodos llm")
    from .llm import ClienteOpenAICompativel

    if a.retomar:
        saida = Path(a.retomar)
        feitas = {json.loads(x)["mef"] for x in saida.read_text("utf-8").splitlines() if '"metodo"' in x}
        mefs = [m for m in mefs if m.nome not in feitas]
        print(f"Retomando: {len(mefs)} MEF(s) restantes")
    else:
        saida = pasta / f"llm_{a.modelo.replace('/', '_').replace(':', '_')}_{datetime.now():%Y%m%d_%H%M}.jsonl"
    rodar_llm(mefs, ClienteOpenAICompativel(a.modelo, a.base_url), a.modelo, a.rodadas_feedback, saida)
    print(f"\nResultados em {saida}. Para a tabela: python -m testes_mef.resumo")


if __name__ == "__main__":
    main()
