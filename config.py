"""Configuração central do Ultron. Tudo que muda entre ambientes vem do .env."""
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent
load_dotenv(RAIZ / ".env")


def _caminho(valor: str) -> Path:
    """Aceita caminho absoluto ou relativo à raiz do projeto."""
    p = Path(valor)
    return p if p.is_absolute() else RAIZ / p


# Provedor do modelo: "gemini" ou "ollama". Padrão: gemini.
PROVEDOR = os.getenv("PROVEDOR", "gemini").lower()

# --- Gemini (usado quando PROVEDOR=gemini) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MODELO_GEMINI_RESERVA = os.getenv("GEMINI_MODEL_RESERVA", "gemini-2.5-flash-lite")

# --- Ollama (usado quando PROVEDOR=ollama) ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
MODELO_OLLAMA = os.getenv("OLLAMA_MODEL", "qwen3:4b")
MODELO_OLLAMA_RESERVA = os.getenv("OLLAMA_MODEL_RESERVA", "")

# --- Interface única (usada pelo agente) ---
if PROVEDOR == "ollama":
    MODELO = MODELO_OLLAMA
    MODELO_RESERVA = MODELO_OLLAMA_RESERVA
else:
    MODELO = MODELO_GEMINI
    MODELO_RESERVA = MODELO_GEMINI_RESERVA

# --- Google Sheets (obrigatório em ambos) ---
GOOGLE_CREDENTIALS = _caminho(os.environ["GOOGLE_CREDENTIALS"])
PLANILHA_ID = os.environ["PLANILHA_ID"]

FUSO = ZoneInfo("America/Sao_Paulo")
PROMPTS = RAIZ / "prompts"
POSTS_APROVADOS = RAIZ / "posts_aprovados.jsonl"
POSTS_PUBLICADOS = RAIZ / "posts_publicados.jsonl"

def agora() -> datetime:
    return datetime.now(FUSO)


def hoje() -> date:
    return agora().date()
