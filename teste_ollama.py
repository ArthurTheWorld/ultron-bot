"""Teste isolado do provedor configurado (Gemini ou Ollama).

Uso:
    python teste_ollama.py
"""
import sys
import time

import config
from llm import cliente


def teste_basico() -> None:
    print(f"\n=== Teste 1: resposta simples ({config.PROVEDOR} / {config.MODELO}) ===")
    c = cliente()

    if config.PROVEDOR == "ollama":
        r = c.chat.completions.create(
            model=config.MODELO,
            messages=[{"role": "user", "content": "Diga apenas: funcionou"}],
        )
        print("Resposta:", r.choices[0].message.content)
    else:
        resp = c.models.generate_content(
            model=config.MODELO,
            contents="Diga apenas: funcionou",
        )
        print("Resposta:", resp.text)


def teste_tool_calling() -> None:
    print(f"\n=== Teste 2: tool calling ({config.PROVEDOR}) ===")

    if config.PROVEDOR != "ollama":
        print("(pulado — só faz sentido pra Ollama por agora)")
        return

    c = cliente()
    ferramentas = [{
        "type": "function",
        "function": {
            "name": "registrar_dia",
            "description": "Registra atividades do dia na planilha",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Data AAAA-MM-DD"},
                    "convites": {"type": "integer", "description": "Convites enviados"},
                },
                "required": ["data"],
            },
        },
    }]
    r = c.chat.completions.create(
        model=config.MODELO,
        messages=[{
            "role": "user",
            "content": "Registra 10 convites enviados hoje (2026-10-06)",
        }],
        tools=ferramentas,
    )
    msg = r.choices[0].message
    if msg.tool_calls:
        for tc in msg.tool_calls:
            print(f"  Ferramenta: {tc.function.name}")
            print(f"  Argumentos: {tc.function.arguments}")
    else:
        print("  ATENCAO: o modelo nao chamou nenhuma ferramenta.")
        print("  Resposta:", msg.content)


if __name__ == "__main__":
    try:
        t0 = time.time()
        teste_basico()
        t1 = time.time()
        print(f"  (latencia: {t1 - t0:.2f}s)")
        teste_tool_calling()
    except Exception as e:
        print(f"\nERRO: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
