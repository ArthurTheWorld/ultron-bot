"""Voz do Ultron.

Com Ollama, o TTS nativo do Gemini não está disponível. Este módulo fica como
stub: o bot funciona em texto. Para áudio real, integre Piper ou Coqui depois.
"""
import logging

log = logging.getLogger("ultron.voz")

NOME_VOZ = "indisponível"


def sintetizar(texto: str) -> bytes:
    raise RuntimeError("TTS não disponível com Ollama. Respostas em áudio estão desativadas.")
