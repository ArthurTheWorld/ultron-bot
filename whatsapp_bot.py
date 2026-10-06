"""Ultron no WhatsApp via Evolution API.

    python whatsapp_bot.py

Recebe mensagens por webhook (a Evolution API faz POST em /webhook) e envia
respostas via HTTP para a Evolution API. Configure no .env:

    EVOLUTION_URL=http://localhost:8080
    EVOLUTION_API_KEY=ultron-secret
    EVOLUTION_INSTANCE=ultron
    WHATSAPP_ALLOWED_NUMBERS=5511999999999   (só o número, com DDI+DDD)
    WHATSAPP_PORT=5000
"""
import logging
import os
import threading

from flask import Flask, jsonify, request

import config  # noqa: F401
import nucleo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ultron.whatsapp")

EVOLUTION_URL = os.environ["EVOLUTION_URL"].rstrip("/")
EVOLUTION_API_KEY = os.environ["EVOLUTION_API_KEY"]
EVOLUTION_INSTANCE = os.environ["EVOLUTION_INSTANCE"]
WHATSAPP_PORT = int(os.getenv("WHATSAPP_PORT", "5000"))

PERMITIDOS = {
    n.strip() for n in os.getenv("WHATSAPP_ALLOWED_NUMBERS", "").replace(" ", "").split(",")
    if n.strip()
}

app = Flask(__name__)
_trava = threading.Lock()


def enviar(numero: str, texto: str, falar: bool = False) -> None:
    """Envia mensagem de texto via Evolution API. `falar` é ignorado (sem TTS local)."""
    import requests
    url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": numero, "text": texto[:4000]}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code >= 400:
            log.warning("Falha ao enviar (%s): %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("Erro ao enviar: %s", e)


def _extrair_texto(data: dict) -> str | None:
    msg = data.get("message") or {}
    if "conversation" in msg:
        return msg["conversation"]
    if "extendedTextMessage" in msg:
        return msg["extendedTextMessage"].get("text")
    return None


@app.route("/webhook", methods=["POST"])
def webhook():
    corpo = request.get_json(silent=True) or {}
    evento = corpo.get("event", "")

    if evento != "messages.upsert":
        return jsonify({"ok": True})

    data = corpo.get("data") or {}
    key = data.get("key") or {}

    if key.get("fromMe"):
        return jsonify({"ok": True})

    remote_jid = key.get("remoteJid", "")
    numero = remote_jid.split("@")[0] if remote_jid else ""

    if PERMITIDOS and numero not in PERMITIDOS:
        log.warning("Mensagem ignorada de número não autorizado: %s", numero)
        return jsonify({"ok": True})

    texto = _extrair_texto(data)
    if not texto:
        enviar(numero, "Por enquanto eu entendo apenas mensagens de texto.")
        return jsonify({"ok": True})

    log.info("Mensagem de %s: %s", numero, texto[:80])

    def responder(resposta: str, falar: bool = False) -> None:
        enviar(numero, resposta)

    threading.Thread(
        target=lambda: nucleo.tratar(responder, texto=texto),
        daemon=True,
    ).start()

    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "instance": EVOLUTION_INSTANCE})


def main() -> None:
    log.info("Ultron WhatsApp ouvindo em :%d (Evolution API: %s / instância: %s)",
             WHATSAPP_PORT, EVOLUTION_URL, EVOLUTION_INSTANCE)
    if not PERMITIDOS:
        log.warning("WHATSAPP_ALLOWED_NUMBERS vazio: qualquer número poderá falar com o bot!")
    app.run(host="0.0.0.0", port=WHATSAPP_PORT)


if __name__ == "__main__":
    main()
