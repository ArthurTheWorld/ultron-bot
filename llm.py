"""Cliente único de LLM para todo o projeto.

Suporta dois provedores, escolhidos por config.PROVEDOR:
- "gemini" → SDK google-genai
- "ollama" → SDK openai apontando pra API local do Ollama
"""
from functools import lru_cache
from importlib import import_module

import httpx

import config

# Erros temporárias: vale tentar de novo ou trocar de modelo.
CODIGOS_TRANSITORIOS = [429, 500, 502, 503, 504]
TIMEOUT_S = 120.0


def erro_transitorio(e: Exception) -> bool:
    """Falhas temporárias: vale tentar de novo ou trocar de modelo."""
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
        return True

    if config.PROVEDOR == "gemini":
        try:
            errors = import_module("google.genai").errors
            api_error = getattr(errors, "APIError", None)
        except ModuleNotFoundError:
            return False
        return api_error is not None and isinstance(e, api_error) and e.code in CODIGOS_TRANSITORIOS

    if config.PROVEDOR == "ollama":
        openai = import_module("openai")
        if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
            return True
        if isinstance(e, openai.APIStatusError):
            return e.status_code in CODIGOS_TRANSITORIOS

    return False


@lru_cache(maxsize=1)
def cliente():
    """Devolve o cliente do provedor configurado."""
    if config.PROVEDOR == "ollama":
        openai = import_module("openai")
        return openai.OpenAI(
            base_url=config.OLLAMA_URL,
            api_key=config.OLLAMA_API_KEY,
            timeout=TIMEOUT_S,
        )

    from google import genai
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=genai.types.HttpOptions(
            timeout=30_000,
            retry_options=genai.types.HttpRetryOptions(
                attempts=3,
                initial_delay=2.0,
                max_delay=20.0,
                http_status_codes=CODIGOS_TRANSITORIOS,
            )
        ),
    )


def carregar_prompt(nome: str) -> str:
    return (config.PROMPTS / nome).read_text(encoding="utf-8")
