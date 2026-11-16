"""Geração de casos de teste por um LLM, a partir da descrição da MEF.

Duas variantes:
- `llm`: uma única chamada (zero-shot);
- `llm_feedback`: depois da primeira resposta, uma "ferramenta de cobertura" informa ao
  modelo as transições que ficaram de fora, por até N rodadas. É o que um engenheiro
  teria na prática; o modelo NÃO recebe informação sobre mutantes.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .mef import MEF, Seq, remover_prefixos

SISTEMA = (
    "Você é um engenheiro de testes especialista em teste baseado em máquinas de estados finitos. "
    "Responda sempre e somente com JSON válido."
)

TAREFA = """Especificação: máquina de estados finitos de Mealy "{nome}".
{descricao}

Estado inicial: {inicial}
Entradas possíveis: {entradas}
Transições (estado --entrada/saída--> próximo estado):
{tabela}

Gere um conjunto de casos de teste para uma implementação dessa máquina.
- Cada caso de teste é uma sequência de entradas aplicada a partir do estado inicial (há um reset antes de cada teste).
- O veredito compara as saídas da implementação com as da especificação.
- Objetivo: detectar qualquer falha de saída (saída errada em uma transição) ou de transferência
  (transição que leva ao estado errado), supondo que a implementação tem no máximo {n} estados.
- Use apenas as entradas listadas.

Responda apenas com JSON no formato: {{"testes": [["entrada1", "entrada2"], ["entrada1"]]}}"""

FEEDBACK = """Executei seus testes com uma ferramenta de cobertura. Estas transições NÃO foram percorridas:
{faltando}

Gere testes ADICIONAIS que percorram essas transições e verifiquem o estado de destino de cada uma.
Responda apenas com JSON no formato: {{"testes": [["entrada1", "entrada2"]]}}"""


def descrever(mef: MEF) -> str:
    linhas = [f"{s} --{a}/{o}--> {d}" for s in mef.estados for a in mef.entradas for d, o in [mef.delta[(s, a)]]]
    return TAREFA.format(
        nome=mef.nome,
        descricao=mef.descricao,
        inicial=mef.inicial,
        entradas=", ".join(mef.entradas),
        tabela="\n".join(linhas),
        n=len(mef.estados),
    )


# ---------- parsing ----------


@dataclass
class Parse:
    testes: list[Seq]
    invalidos: int = 0  # testes descartados por usar entrada inexistente
    erro: str | None = None  # resposta sem JSON utilizável


def extrair_testes(texto: str | None, entradas: tuple[str, ...]) -> Parse:
    """Lê a resposta do modelo de forma tolerante: cercas ```json, <think>, texto em volta."""
    if not texto:
        return Parse([], erro="resposta vazia")
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    texto = re.sub(r"```(?:json)?", "", texto)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        return Parse([], erro="nenhum objeto JSON na resposta")
    try:
        dados = json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError as e:
        return Parse([], erro=f"JSON inválido: {e.msg}")
    brutos = dados.get("testes") if isinstance(dados, dict) else None
    if not isinstance(brutos, list):
        return Parse([], erro="campo 'testes' ausente ou não é lista")
    validos, invalidos = [], 0
    permitidas = set(entradas)
    for t in brutos:
        if isinstance(t, str):  # "a b c" ou "a,b,c"
            t = [x for x in re.split(r"[\s,]+", t) if x]
        if not isinstance(t, list) or not t or not all(isinstance(x, str) and x in permitidas for x in t):
            invalidos += 1
            continue
        validos.append(tuple(t))
    return Parse(validos, invalidos)


# ---------- cliente ----------


class ClienteLLM(Protocol):
    def completar(self, mensagens: list[dict[str, str]]) -> tuple[str | None, dict[str, int]]: ...


class ClienteOpenAICompativel:
    """Chat Completions de qualquer provedor compatível (Groq, OpenAI, Ollama, Gemini...)."""

    def __init__(self, modelo: str, base_url: str | None = None, api_key: str | None = None, temperatura: float = 0.0):
        from openai import OpenAI

        self.modelo = modelo
        self.temperatura = temperatura
        self._cliente = OpenAI(
            base_url=base_url or os.environ.get("LLM_BASE_URL") or None,
            api_key=api_key or os.environ.get("LLM_API_KEY") or "nao-usado",
            max_retries=8,  # respeita Retry-After de limites por minuto
            timeout=180,
        )

    def completar(self, mensagens: list[dict[str, str]]) -> tuple[str | None, dict[str, int]]:
        r = self._cliente.chat.completions.create(model=self.modelo, messages=mensagens, temperature=self.temperatura)
        uso = {}
        if r.usage:
            uso = {"prompt_tokens": r.usage.prompt_tokens, "completion_tokens": r.usage.completion_tokens}
        return r.choices[0].message.content, uso


class ClienteRoteirizado:
    """Cliente falso para testes: devolve respostas pré-definidas (ou funções das mensagens)."""

    def __init__(self, respostas: list[str | Callable[[list[dict[str, str]]], str]]):
        self.respostas = list(respostas)
        self.chamadas: list[list[dict[str, str]]] = []

    def completar(self, mensagens):
        self.chamadas.append([dict(m) for m in mensagens])
        r = self.respostas.pop(0)
        return (r(mensagens) if callable(r) else r), {"prompt_tokens": 10, "completion_tokens": 5}


# ---------- geração ----------


@dataclass
class Rodada:
    testes_novos: list[Seq]
    invalidos: int
    erro: str | None
    cobertura_acumulada: float


@dataclass
class ResultadoLLM:
    testes_primeira_rodada: list[Seq]
    testes_finais: list[Seq]
    rodadas: list[Rodada] = field(default_factory=list)
    tokens: int = 0
    tokens_primeira_rodada: int = 0
    respostas: list[str | None] = field(default_factory=list)


def gerar_com_llm(mef: MEF, cliente: ClienteLLM, rodadas_feedback: int = 2) -> ResultadoLLM:
    from .metodos import cobertura

    mensagens: list[dict[str, Any]] = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": descrever(mef)},
    ]
    testes: list[Seq] = []
    resultado = ResultadoLLM([], [])
    for i in range(1 + rodadas_feedback):
        texto, uso = cliente.completar(mensagens)
        resultado.respostas.append(texto)
        resultado.tokens += sum(uso.values())
        p = extrair_testes(texto, mef.entradas)
        testes = remover_prefixos(testes + p.testes)
        cob = cobertura(mef, testes)
        resultado.rodadas.append(Rodada(p.testes, p.invalidos, p.erro, cob))
        if i == 0:
            resultado.testes_primeira_rodada = list(testes)
            resultado.tokens_primeira_rodada = resultado.tokens
        percorridas = {t for seq in testes for t in mef.transicoes_percorridas(seq)}
        faltando = [t for t in mef.delta if t not in percorridas]
        if not faltando or i == rodadas_feedback:
            break
        mensagens.append({"role": "assistant", "content": texto or ""})
        mensagens.append(
            {
                "role": "user",
                "content": FEEDBACK.format(faltando="\n".join(f"- estado {s}, entrada {a}" for s, a in faltando)),
            }
        )
    resultado.testes_finais = testes
    return resultado
