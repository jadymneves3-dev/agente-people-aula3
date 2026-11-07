# ETAPA 1: IMPORTAÇÃO DAS BIBLIOTECAS
import os  # acessa os arquivos do sistema
import unicodedata  # normaliza os caracteres especiais
import uuid  # gera identificadores únicos (para criar os links do google meet)
from datetime import datetime  # trabalha com datas e horários

from google.auth.exceptions import RefreshError  # trata erros de autenticação
from google.auth.transport.requests import Request  # faz requisições HTTP
from google.oauth2.credentials import (
    Credentials,
)  # gerencia as credenciais de autenticação
from google_auth_oauthlib.flow import (
    InstalledAppFlow,
)  # gerencia o fluxo de autenticação
from googleapiclient.discovery import build  # cria o objeto de autenticação

# ETAPA 2: CRIAR OS ESCOPOS DE AUTENTICAÇÃO
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",  # eventos do Google Calendar
    "https://www.googleapis.com/auth/spreadsheets",  # planilhas do Google Sheets
]

# dicionário com os nomes das colunas na planilha e seus respectivos IDs
CAMPOS_DA_PLANILHA = {
    "nome": {"nome", "nomecandidato"},
    "vaga": {"vaga", "cargo"},
    "data": {"data", "dataentrevista"},
    "hora": {"hora", "horario", "horarioentrevista"},
    "email": {"email", "emailcandidato"},
    "status": {"status", "situacao"},
}


# ETAPA 3: FUNÇÃO PARA AUTENTICAÇÃO NO GOOGLE
def autenticar_google():
    """
    Função para autenticar no Google e retornar o serviço de planilhas e calendário.
    """
    credenciais = None  # variável para armazenar as credenciais do Google está vazia
    if os.path.exists("token.json"):  # verifica se o arquivo de token existe
        credenciais = Credentials.from_authorized_user_file(
            "token.json", SCOPES
        )  # carrega as credenciais do arquivo
    if (
        credenciais and credenciais.expired and credenciais.refresh_token
    ):  # verifica se as credenciais são válidas
        try:
            credenciais.refresh(Request())  # tenta atualizar as credenciais
        except (
            RefreshError
        ):  # se não conseguir atualizar, solicita uma nova autenticação
            credenciais = None  # se não conseguir atualizar, as credenciais são nulas

    if (
        not credenciais or not credenciais.valid
    ):  # verifica se as credenciais são válidas
        fluxo = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )  # cria o fluxo de autenticação
        credenciais = fluxo.run_local_server(port=0)  # executa o fluxo de autenticação

        with open(
            "token.json", "w", encoding="utf-8"
        ) as arquivo_token:  # salva as credenciais no arquivo de token
            arquivo_token.write(
                credenciais.to_json()
            )  # escreve as credenciais no arquivo de token
    return credenciais  # retorna as credenciais


def listar_agendamentos():
    """Retorna todos os eventos de entrevista do calendário principal."""
    servico = build("calendar", "v3", credentials=autenticar_google())
    eventos = []
    pagina = None

    while True:
        resposta = (
            servico.events()
            .list(
                calendarId="primary",
                maxResults=2500,
                pageToken=pagina,
                showDeleted=True,
                singleEvents=True,
                fields=(
                    "nextPageToken,items(id,summary,start,end,status,attendees"
                    "(email,responseStatus),htmlLink,hangoutLink,originalStartTime)"
                ),
            )
            .execute()
        )
        eventos.extend(
            evento
            for evento in resposta.get("items", [])
            if evento.get("summary", "").strip().casefold().startswith("entrevista com ")
        )
        pagina = resposta.get("nextPageToken")
        if not pagina:
            return eventos


def agendar_entrevista_com_meet(
    nome_candidato,
    email_candidato,
    data_hora_inicio,
    data_hora_fim,
):
    """Função para agendar uma entrevista no Google Calendar com link do Google Meet."""
    servico = build("calendar", "v3", credentials=autenticar_google())

    evento = {
        "summary": f"Entrevista com {nome_candidato}",  # título do
        "description": "Entrevista de alinhamento com o time de People.",  # descrição do evento
        "start": {
            "dateTime": data_hora_inicio,  # data e hora de início
            "timeZone": "America/Sao_Paulo",  # fuso horário
        },
        "end": {
            "dateTime": data_hora_fim,  # data e hora de término
            "timeZone": "America/Sao_Paulo",  # fuso horário
        },
        "attendees": [
            {
                "email": email_candidato
            },  # adiciona o e-mail do candidato como participante
        ],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),  # gera um ID único para a reunião
                "conferenceSolutionKey": {
                    "type": "hangoutsMeet"  # tipo de conferência (Google Meet)
                },
            },
        },
    }

    evento_criado = (
        servico.events()
        .insert(
            calendarId="primary",  # ID do calendário (padrão)
            body=evento,  # corpo do evento
            conferenceDataVersion=1,  # versão da conferência
            sendUpdates="all",  # envia atualizações para todos os participantes
        )
        .execute()
    )  # executa a criação do evento

    link_meet = evento_criado.get("hangoutLink")  # pega o link do Google Meet
    return link_meet  # retorna o link do Google Meet


def registrar_candidato_na_planilha(
    id_planilha,
    nome,
    email,
    vaga,
    data_hora_inicio=None,
    data_hora_fim=None,
    status=None,
):
    """Função para registrar os dados do candidato na planilha do Google Sheets."""
    servico = build("sheets", "v4", credentials=autenticar_google())

    planilha = (
        servico.spreadsheets()
        .get(
            spreadsheetId=id_planilha,
            fields="sheets(properties(sheetId,title))",
        )
        .execute()
    )  # pega as informações da planilha

    aba = next(
        (
            item["properties"]
            for item in planilha.get("sheets", [])
            if item.get("properties", {}).get("sheetId") == 0
        ),
        None,
    )  # tenta encontrar a aba com ID 0 (primeira aba/principal) da planilha

    if not aba:  # se não encontrar a aba, lança um erro
        raise ValueError(
            "Aba principal não encontrada na planilha."
        )  # mensagem de erro

    nome_aba = aba.get("title", "Sheet1").replace("'", "''")
    intervalo_cabecalho = f"'{nome_aba}'!1:1"
    resposta = (
        servico.spreadsheets()
        .values()
        .get(
            spreadsheetId=id_planilha,
            range=intervalo_cabecalho,
        )
        .execute()
    )  # pega os valores das células do intervalo definido

    linhas = resposta.get(
        "values", []
    )  # pega os valores das células do intervalo definido
    cabecalho = linhas[0] if linhas else []  # pega o cabeçalho da planilha
    colunas = {}
    for indice, valor_cabecalho in enumerate(cabecalho):
        normalizado = "".join(
            caractere
            for caractere in unicodedata.normalize(
                "NFKD", str(valor_cabecalho).strip().lower()
            )
            if not unicodedata.combining(caractere) and caractere.isalnum()
        )
        for campo, alternativas in CAMPOS_DA_PLANILHA.items():
            if normalizado in alternativas:
                colunas[campo] = indice
                break

    if "nome" not in colunas or "email" not in colunas:
        raise ValueError("A planilha precisa ter colunas de nome e email.")

    dados = {
        "nome": nome,
        "email": email,
        "vaga": vaga or "",
        "status": status or "",
    }
    if data_hora_inicio:
        try:
            inicio = datetime.fromisoformat(
                data_hora_inicio
            )  # converte a string de data e hora para objeto datetime
            if "data" in colunas:
                dados["data"] = inicio.strftime(
                    "%d/%m/%Y"
                )  # formata a data para o formato dd/mm/aaaa
            if "hora" in colunas:
                hora = inicio.strftime("%H:%M")  # formata a hora para o formato hh:mm
                if data_hora_fim:
                    fim = datetime.fromisoformat(
                        data_hora_fim
                    )  # converte a string de data e hora para objeto datetime
                    hora += f" - {fim.strftime('%H:%M')}"  # concatena a hora de início e fim
                dados["hora"] = hora
        except ValueError:
            raise ValueError(
                "Formato de data e hora inválido. Use o formato YYYY-MM-DDTHH:MM:SS ou YYYY-MM-DDTHH:MM:SS+00:00."
            )  # mensagem de erro caso o formato seja inválido

    # prepara uma lista com os valores na ordem das colunas da planilha
    valores = [""] * (max(colunas.values()) + 1)
    for campo, valor in dados.items():
        if campo in colunas:
            valores[colunas[campo]] = valor

    # adiciona os valores na planilha
    servico.spreadsheets().values().append(
        spreadsheetId=id_planilha,
        range=f"'{nome_aba}'!A:F",
        valueInputOption="USER_ENTERED",
        body={"values": [valores]},
    ).execute()  # executa a adição dos valores na planilha

    return "Candidato registrado com sucesso na planilha."  # mensagem de sucesso
