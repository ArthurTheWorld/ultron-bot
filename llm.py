"""Cliente único de LLM para todo o projeto.

Suporta dois provedores, escolhidos por config.PROVEDOR:
- "gemini" → SDK google-genai
- "ollama" → SDK openai apontando pra API local do Ollama
"""
from functools import lru_cache

import httpx

import config

# Erros temporários: vale tentar de novo ou trocar de modelo.
CODIGOS_TRANSITORIOS = [429, 500, 502, 503, 504]
TIMEOUT_S = 120.0


def erro_transitorio(e: Exception) -> bool:
    """Falhas temporárias: vale tentar de novo ou trocar de modelo."""
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
        return True

    if config.PROVEDOR == "gemini":
        from google.genai import errors
        return isinstance(e, errors.APIError) and e.code in CODIGOS_TRANSITORIOS

    if config.PROVEDOR == "ollama":
        from openai import APIStatusError, APIConnectionError, APITimeoutError
        if isinstance(e, (APIConnectionError, APITimeoutError)):
            return True
        if isinstance(e, APIStatusError):
            return e.status_code in CODIGOS_TRANSITORIOS

    return False


@lru_cache(maxsize=1)
def cliente():
    """Devolve o cliente do provedor configurado."""
    if config.PROVEDOR == "ollama":
        from openai import OpenAI
        return OpenAI(
            base_url=config.OLLAMA_URL,
            api_key=config.OLLAMA_API_KEY,
            timeout=TIMEOUT_S,
        )

    from google import genai
    from google.genai import types
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=30_000,
            retry_options=types.HttpRetryOptions(
                attempts=3,
                initial_delay=2.0,
                max_delay=20.0,
                http_status_codes=CODIGOS_TRANSITORIOS,
            )
        ),
    )


def carregar_prompt(nome: str) -> str:
    return (config.PROMPTS / nome).read_text(encoding="utf-8")
