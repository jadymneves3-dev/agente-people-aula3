"""Interpreta pedidos dos usuários e executa as ações do Google"""

import json
import os
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from googleapiclient.errors import HttpError
from openai import OpenAI

from google_tools import (
    autenticar_google,
    agendar_entrevista_com_meet,
    registrar_candidato_na_planilha as registrar_candidato_planilha_google,
)

# carregar a GROQ_API_KEY
load_dotenv()  # carrega as variáveis de ambiente do arquivo .env
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = (
    OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    if GROQ_API_KEY
    else None
)

# definir o modelo e indicar o id da planilha
MODELO_GROQ = "openai/gpt-oss-20b"
PLANILHA_ID = os.environ.get(
    "PLANILHA_ID"
)  # pega o id da planilha do Google Sheets das variáveis de ambiente

# prompt para definir as regras do agente
PROMPT = (
    "Você é um assistente virtual especializado em processos seletivos. "
    "Sua função é ajudar na coordenação de entrevistas e no registro de candidatos "
    "em uma planilha do Google Sheets. Ao agendar uma entrevista, informe também "
    "a vaga e o status disponíveis para o registro automático do candidato."
)


# função para normalizar ou tokenizar o texto
def normalizar(texto):
    """Normaliza o texto removendo acentos e convertendo para minúsculas."""
    texto_sem_acento = unicodedata.normalize("NFKD", str(texto))
    return "".join(
        caractere
        for caractere in texto_sem_acento
        if not unicodedata.combining(caractere)
    ).lower()


def _normalizar_ano_datas(argumentos, mensagem_usuario, ano_atual):
    """Usa o ano atual nas datas geradas quando o usuário não especificou um ano."""
    texto = normalizar(mensagem_usuario)
    menciona_ano = re.search(r"\b(?:19|20)\d{2}\b", texto) or re.search(
        r"\b(?:ano que vem|ano seguinte|ano passado|ano anterior|ano atual|"
        r"ano vigente|este ano|neste ano|proximo ano)\b",
        texto,
    )
    if menciona_ano:
        return argumentos

    argumentos_normalizados = dict(argumentos)
    for campo in ("data_hora_inicio", "data_hora_fim"):
        valor = argumentos_normalizados.get(campo)
        if not isinstance(valor, str) or not valor:
            continue
        try:
            data_hora = datetime.fromisoformat(valor)
        except ValueError:
            continue
        if data_hora.year != ano_atual:
            try:
                argumentos_normalizados[campo] = data_hora.replace(
                    year=ano_atual
                ).isoformat()
            except ValueError as erro:
                raise ValueError(
                    f"A data {data_hora:%d/%m} não existe no ano {ano_atual}. "
                    "Informe outro dia para a entrevista."
                ) from erro
    return argumentos_normalizados


def registrar_candidato_na_planilha(
    nome,
    email,
    vaga=None,
    status=None,
    data_hora_inicio=None,
    data_hora_fim=None,
):
    """Registra um candidato na planilha configurada do Google Sheets."""
    if not PLANILHA_ID:
        raise ValueError("A variável PLANILHA_ID não foi configurada.")

    return registrar_candidato_planilha_google(
        id_planilha=PLANILHA_ID,
        nome=nome,
        email=email,
        vaga=vaga,
        status=status,
        data_hora_inicio=data_hora_inicio,
        data_hora_fim=data_hora_fim,
    )


# criando as ferramentas do agente
FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "agendar_entrevista_com_meet",
            "description": (
                "Agendar uma entrevista no Google Calendar com link do Google Meet. "
                "Informe vaga e status quando estiverem no pedido; o candidato também "
                "será registrado automaticamente na planilha."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_candidato": {"type": "string"},
                    "email_candidato": {"type": "string"},
                    "data_hora_inicio": {
                        "type": "string",
                        "description": "Data e hora de início no formato ISO 8601.",
                    },
                    "data_hora_fim": {
                        "type": "string",
                        "description": "Data e hora de término no formato ISO 8601.",
                    },
                    "vaga": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": [
                    "nome_candidato",
                    "email_candidato",
                    "data_hora_inicio",
                    "data_hora_fim",
                ],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_candidato_na_planilha",
            "description": "Registrar os dados de um candidato na planilha de People.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "email": {"type": "string"},
                    "vaga": {"type": "string"},
                    "status": {"type": "string"},
                    "data_hora_inicio": {"type": "string"},
                    "data_hora_fim": {"type": "string"},
                },
                "required": ["nome", "email"],
                "additionalProperties": False,
            },
        },
    },
]


def _executar_ferramenta(nome, argumentos):
    """Executa uma ferramenta solicitada pelo modelo."""
    if nome == "agendar_entrevista_com_meet":
        return agendar_entrevista_com_meet(
            nome_candidato=argumentos["nome_candidato"],
            email_candidato=argumentos["email_candidato"],
            data_hora_inicio=argumentos["data_hora_inicio"],
            data_hora_fim=argumentos["data_hora_fim"],
        )
    if nome == "registrar_candidato_na_planilha":
        return registrar_candidato_na_planilha(**argumentos)
    raise ValueError(f"Ferramenta desconhecida: {nome}")


# função para executar o agente de recrutamento
def executar_agente_rh(mensagem_usuario):
    """Executa o agente de recrutamento e encaminha chamadas para as ferramentas Google."""
    if client is None:
        return [("texto", "Configure a chave GROQ_API_KEY para usar o agente.")]

    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    mensagens = [
        {
            "role": "system",
            "content": (
                f"{PROMPT} A data atual em São Paulo é "
                f"{agora:%d/%m/%Y}. Se o usuário não informar o ano da entrevista, "
                f"use {agora.year}. Preserve o ano quando ele for informado "
                "explicitamente ou por referência relativa, como 'ano que vem'."
            ),
        },
        {"role": "user", "content": mensagem_usuario},
    ]
    resposta = client.chat.completions.create(
        model=MODELO_GROQ,
        messages=mensagens,
        tools=FERRAMENTAS,
        tool_choice="auto",
    )
    mensagem = resposta.choices[0].message
    chamadas = mensagem.tool_calls or []

    if not chamadas:
        return [("texto", mensagem.content or "Ops, não sei fazer isso.")]

    resultados = []
    chamadas_planilha = [
        chamada
        for chamada in chamadas
        if chamada.function.name == "registrar_candidato_na_planilha"
    ]
    emails_registrados = set()
    for chamada in chamadas_planilha:
        argumentos = json.loads(chamada.function.arguments)
        email = argumentos.get("email", "").strip().lower()
        if email:
            emails_registrados.add(email)

    # Executa cada ferramenta mesmo se outra integração falhar.
    for chamada in chamadas:
        nome = chamada.function.name
        try:
            args = _normalizar_ano_datas(
                json.loads(chamada.function.arguments),
                mensagem_usuario,
                agora.year,
            )
        except ValueError as erro:
            resultados.append(("erro", str(erro)))
            continue

        if nome == "agendar_entrevista_com_meet":
            try:
                resultado = _executar_ferramenta(nome, args)
                resultados.append(("calendar", resultado))
            except (HttpError, ValueError) as erro:
                resultados.append(("erro", f"Falha ao agendar a entrevista: {erro}"))

            email = args["email_candidato"].strip().lower()
            if email not in emails_registrados:
                emails_registrados.add(email)
                argumentos_planilha = {
                    "nome": args["nome_candidato"],
                    "email": args["email_candidato"],
                    "vaga": args.get("vaga", "Não informado"),
                    "status": args.get("status", "Cadastrado"),
                    "data_hora_inicio": args.get("data_hora_inicio"),
                    "data_hora_fim": args.get("data_hora_fim"),
                }
                try:
                    resultado = _executar_ferramenta(
                        "registrar_candidato_na_planilha",
                        argumentos_planilha,
                    )
                    resultados.append(("sheets", resultado))
                except (HttpError, ValueError) as erro:
                    resultados.append(
                        ("erro", f"Falha ao registrar o candidato na planilha: {erro}")
                    )

        elif nome == "registrar_candidato_na_planilha":
            try:
                resultado = _executar_ferramenta(nome, args)
                resultados.append(("sheets", resultado))
            except (HttpError, ValueError) as erro:
                resultados.append(
                    ("erro", f"Falha ao registrar o candidato na planilha: {erro}")
                )
        else:
            resultados.append(("erro", f"Ferramenta desconhecida: {nome}"))

    return resultados
