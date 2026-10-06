"""O Ultron: agente roteador que interpreta a mensagem e escolhe a ferramenta.

Usa o Ollama local via API compatível com OpenAI (SDK openai).
Tool calling é feito manualmente: o modelo pede a ferramenta, o código executa
e devolve o resultado até o modelo responder só com texto.
"""
import functools
import json
import logging

import config
from llm import carregar_prompt, cliente, erro_transitorio
from tools import conteudo, contatos, registro

log = logging.getLogger("ultron.bot")

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

COM_EFEITO = {
    "registrar_dia", "rascunhar_post", "ajustar_post", "aprovar_post", "descartar_post",
    "adicionar_contato", "atualizar_status", "registrar_interacao",
}
_execucoes: list[tuple[str, dict, dict]] = []


class AcoesSemResposta(Exception):
    """Ações já executadas, mas o modelo caiu antes de responder."""

    def __init__(self, execucoes):
        super().__init__("ações executadas sem resposta final")
        self.execucoes = execucoes


class ModelosIndisponiveis(Exception):
    """Nenhum modelo conseguiu responder e nada foi alterado."""


def _rastrear(funcao):
    @functools.wraps(funcao)
    def envoltorio(*args, **kwargs):
        log.info("Ferramenta chamada: %s %s", funcao.__name__, kwargs)
        resultado = funcao(*args, **kwargs)
        falhou = isinstance(resultado, dict) and resultado.get("ok") is False
        if funcao.__name__ in COM_EFEITO and not falhou:
            _execucoes.append((funcao.__name__, kwargs, resultado))
        return resultado
    return envoltorio


FERRAMENTAS = [_rastrear(f) for f in (
    registro.registrar_dia,
    registro.consultar_dia,
    registro.resumo_semana,
    conteudo.rascunhar_post,
    conteudo.ajustar_post,
    conteudo.aprovar_post,
    conteudo.descartar_post,
    contatos.adicionar_contato,
    contatos.atualizar_status,
    contatos.registrar_interacao,
    contatos.consultar_contatos,
    contatos.listar_followups_pendentes,
)]

FERRAMENTAS_POR_NOME = {f.__name__: f for f in FERRAMENTAS}


def _schema(nome, descricao, propriedades, obrigatorios):
    return {
        "type": "function",
        "function": {
            "name": nome,
            "description": descricao,
            "parameters": {
                "type": "object",
                "properties": propriedades,
                "required": obrigatorios,
            },
        },
    }


_SCHEMAS = [
    _schema(
        "registrar_dia",
        "Registra atividades de LinkedIn e inglês de um dia na planilha. "
        "Use quando o usuário relatar o que fez em um dia. Informe SOMENTE os campos citados.",
        {
            "data": {"type": "string", "description": "Data AAAA-MM-DD. Resolva 'hoje', 'ontem' a partir do contexto."},
            "modo": {"type": "string", "enum": ["somar", "corrigir"]},
            "rotina_feita": {"type": "boolean"},
            "posts": {"type": "integer"},
            "convites": {"type": "integer"},
            "convites_recrutadores": {"type": "integer"},
            "convites_aceitos": {"type": "integer"},
            "comentarios": {"type": "integer"},
            "acoes_relacionamento": {"type": "integer"},
            "conversas_iniciadas": {"type": "integer"},
            "ingles_minutos": {"type": "integer"},
            "observacoes": {"type": "string"},
        },
        ["data"],
    ),
    _schema(
        "consultar_dia",
        "Mostra o que já está registrado na planilha para um dia.",
        {"data": {"type": "string"}},
        ["data"],
    ),
    _schema(
        "resumo_semana",
        "Retorna a performance de uma semana do desafio frente às metas.",
        {"semana": {"type": "integer"}},
        [],
    ),
    _schema(
        "rascunhar_post",
        "Cria um rascunho de post de LinkedIn a partir de um aprendizado ou experiência.",
        {
            "tema": {"type": "string"},
            "transcricao": {"type": "string"},
        },
        ["tema", "transcricao"],
    ),
    _schema(
        "ajustar_post",
        "Ajusta o rascunho de post em revisão com base no pedido do usuário.",
        {"instrucao": {"type": "string"}},
        ["instrucao"],
    ),
    _schema("aprovar_post", "Aprova o rascunho em revisão. Só use com aprovação explícita.", {}, []),
    _schema("descartar_post", "Descarta o rascunho em revisão.", {}, []),
    _schema(
        "adicionar_contato",
        "Adiciona um novo contato ao CRM do LinkedIn. Preencha só o que foi dito.",
        {
            "nome": {"type": "string"},
            "empresa": {"type": "string"},
            "cargo": {"type": "string"},
            "url_perfil": {"type": "string"},
            "status": {"type": "string", "enum": ["convidado", "aceito", "conversando", "followup_pendente", "arquivado"]},
            "origem": {"type": "string", "enum": ["busca", "indicacao", "evento", "comentario"]},
            "notas": {"type": "string"},
        },
        ["nome"],
    ),
    _schema(
        "atualizar_status",
        "Atualiza o status de um contato no CRM.",
        {
            "nome": {"type": "string"},
            "novo_status": {"type": "string", "enum": ["convidado", "aceito", "conversando", "followup_pendente", "arquivado"]},
            "notas": {"type": "string"},
        },
        ["nome", "novo_status"],
    ),
    _schema(
        "registrar_interacao",
        "Registra uma interação com um contato e, opcionalmente, agenda follow-up.",
        {
            "nome": {"type": "string"},
            "resumo": {"type": "string"},
            "proximo_followup": {"type": "string"},
        },
        ["nome", "resumo"],
    ),
    _schema(
        "consultar_contatos",
        "Consulta contatos do CRM com filtros opcionais.",
        {
            "status": {"type": "string", "enum": ["convidado", "aceito", "conversando", "followup_pendente", "arquivado"]},
            "empresa": {"type": "string"},
            "sem_interacao_dias": {"type": "integer"},
        },
        [],
    ),
    _schema("listar_followups_pendentes", "Lista contatos com follow-up para hoje ou atrasado.", {}, []),
]


class Ultron:
    def __init__(self) -> None:
        self._sistema = carregar_prompt("ultron.md")
        self._modelos = [m for m in dict.fromkeys([config.MODELO, config.MODELO_RESERVA]) if m]
        self._modelo_atual = config.MODELO
        self._mensagens: list[dict] = [{"role": "system", "content": self._sistema}]
        self._notas: list[str] = []
        self._client = cliente()

    def _falhou_depois_de_agir(self, e: Exception) -> None:
        resumo = "; ".join(f"{nome}({args})" for nome, args, _ in _execucoes)
        self._notas = [
            f"[Sistema: na mensagem anterior do usuário, estas ações JÁ foram executadas "
            f"e não devem ser repetidas: {resumo}]"
        ]
        raise AcoesSemResposta(list(_execucoes)) from e

    def _executar_ferramenta(self, nome: str, argumentos_json: str) -> dict:
        try:
            args = json.loads(argumentos_json or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "erro": f"Argumentos inválidos: {argumentos_json!r}"}
        funcao = FERRAMENTAS_POR_NOME.get(nome)
        if funcao is None:
            return {"ok": False, "erro": f"Ferramenta desconhecida: {nome}"}
        try:
            return funcao(**args)
        except Exception as e:
            return {"ok": False, "erro": f"{type(e).__name__}: {e}"}

    def _loop_tool_calling(self, modelo: str) -> str:
        max_iteracoes = 6
        for _ in range(max_iteracoes):
            resp = self._client.chat.completions.create(
                model=modelo,
                messages=self._mensagens,
                tools=_SCHEMAS,
                tool_choice="auto",
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                texto = msg.content or "(sem resposta em texto)"
                self._mensagens.append({"role": "assistant", "content": texto})
                return texto

            self._mensagens.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                resultado = self._executar_ferramenta(tc.function.name, tc.function.arguments)
                self._mensagens.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(resultado, ensure_ascii=False),
                })

        return "(loop de ferramentas excedeu o limite)"

    def responder(self, texto: str | None = None, audio: bytes | None = None,
                  mime: str = "audio/ogg") -> str:
        agora = config.agora()
        contexto = (
            f"[Contexto: agora é {DIAS[agora.weekday()]}, "
            f"{agora:%Y-%m-%d %H:%M}, horário de Brasília]"
        )

        # Atualiza o system prompt com o contexto atual (não aparece como mensagem do usuário)
        contexto_interno = (
            f"<contexto_do_sistema>\n{contexto}\n</contexto_do_sistema>\n"
            "(Não mencione nem repita o conteúdo de <contexto_do_sistema> na sua resposta.)"
        )
        self._mensagens[0] = {
            "role": "system",
            "content": f"{self._sistema}\n\n{contexto_interno}",
        }

        if audio:
            log.warning("Ollama não processa áudio nativamente; áudio ignorado.")

        conteudo_user = texto or ""
        if self._notas:
            conteudo_user = "\n".join(self._notas) + "\n" + conteudo_user
        self._mensagens.append({"role": "user", "content": conteudo_user})

        for modelo in self._modelos:
            _execucoes.clear()
            try:
                resultado = self._loop_tool_calling(modelo)
            except Exception as e:
                if not erro_transitorio(e):
                    raise
                if _execucoes:
                    self._falhou_depois_de_agir(e)
                log.warning("Modelo %s indisponível (%s).", modelo, type(e).__name__)
                continue
            self._notas = []
            return resultado

        raise ModelosIndisponiveis("modelos indisponíveis")
