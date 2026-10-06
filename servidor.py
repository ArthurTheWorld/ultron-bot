"""Servidor HTTP que conecta o WhatsApp ao nucleo do Ultron."""
from fastapi import FastAPI
from pydantic import BaseModel
from nucleo import tratar

app = FastAPI()

class Mensagem(BaseModel):
    texto: str = ""

@app.post("/mensagem")
async def receber_mensagem(msg: Mensagem):
    """Recebe uma mensagem do WhatsApp e devolve a resposta do Ultron."""
    respostas = []

    def enviar(texto: str, falar: bool = False):
        respostas.append({"texto": texto, "falar": falar})

    try:
        tratar(enviar=enviar, texto=msg.texto if msg.texto else None)
        return {"respostas": respostas}
    except Exception as e:
        return {"respostas": [{"texto": f"Erro: {type(e).__name__}: {e}", "falar": False}]}

@app.get("/")
async def raiz():
    return {"status": "Ultron online"}