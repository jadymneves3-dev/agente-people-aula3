"""Monta a interface Streamlit da Central de Recrutamento."""

import os  # Verifica se os arquivos de configuração estão disponíveis.
from datetime import datetime
from pathlib import Path  # Encontra o CSS ao lado deste arquivo.
from zoneinfo import ZoneInfo

from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError
import streamlit as st  # Componentes visuais e estado da página.

# Importamos o modelo, o ID da planilha e a função que processa pedidos.
from agent import MODELO_GROQ, PLANILHA_ID, executar_agente_rh
from google_tools import listar_agendamentos

# Configuramos o título, ícone e largura da aplicação.
st.set_page_config(
    page_title="Central de Recrutamento",
    page_icon="\U0001F4BC",
    layout="wide"
)

# O CSS separado define cores, espaçamentos, cartões e botões.
css_path = Path(__file__).with_name("styles.css")
css = css_path.read_text(encoding="utf-8")
st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)

# Estes indicadores mostram se as configurações principais estão presentes.
groq_configurado = bool(os.environ.get("GROQ_API_KEY"))
google_configurado = os.path.exists("credentials.json")
planilha_configurada = bool(PLANILHA_ID)

# A barra lateral resume o nome do sistema, integrações e modelo utilizado.
with st.sidebar:
    st.markdown('<div class="brand-mark">TALENT WORKSPACE</div>', unsafe_allow_html=True)
    st.markdown("## Central de RH")
    st.caption("Assistente de recrutamento")
    st.divider()

    st.markdown("#### Integrações")
    # Cada par associa o nome de uma integração à sua configuração.
    for label, configurado in (
        ("Assistente de IA", groq_configurado),
        ("Google Workspace", google_configurado),
        ("Planilha de candidatos", planilha_configurada),
    ):
        # A classe CSS muda a cor do indicador conforme o estado.
        estado = "Configurado" if configurado else "Verificar configuração"
        classe = "ok" if configurado else "off"
        st.markdown(
            f'<div class="status-line"><span class="status-dot {classe}"></span>'
            f'<span>{label}</span></div>',
            unsafe_allow_html=True
        )
        if not configurado:
            st.caption(estado)

    st.divider()
    st.caption("Modelo de IA")
    st.code(MODELO_GROQ, language=None)
    st.caption("Conectado via Groq Cloud")

# A área principal apresenta o propósito da aplicação.
st.markdown('<div class="eyebrow">OPERAÇÕES DE TALENT ACQUISITION</div>', unsafe_allow_html=True)
st.title("Gestão de recrutamento")
st.markdown(
    '<div class="page-subtitle">Agende entrevistas e mantenha os dados dos candidatos '
    'organizados em um único fluxo.</div>',
    unsafe_allow_html=True
)

tab_solicitacao, tab_dashboard = st.tabs(
    ["Nova solicitação", "Dashboard de agendamentos"]
)

with tab_solicitacao:
    # Os dois cartões explicam o que o Calendar e a planilha fazem.
    st.markdown("### Integrações disponíveis")
    col_calendar, col_sheets = st.columns(2)
    with col_calendar:
        with st.container(border=True):
            st.markdown('<div class="integration-title">Agenda e entrevistas</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="integration-copy">Crie convites de entrevista no Google Calendar '
                'com link do Google Meet.</div>',
                unsafe_allow_html=True
            )
    with col_sheets:
        with st.container(border=True):
            st.markdown('<div class="integration-title">Gestão de candidatos</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="integration-copy">Registre candidatos, vagas e status diretamente '
                'na planilha conectada.</div>',
                unsafe_allow_html=True
            )

    # O formulário aceita pedidos de agendamento, cadastro ou ambos.
    st.markdown("### Nova solicitação")
    st.markdown(
        "Descreva as ações desejadas e inclua os dados do candidato, a vaga e os horários "
        "quando aplicável. Ao agendar uma entrevista, o candidato também é registrado "
        "automaticamente na planilha."
    )

    # O formulário só envia o texto quando o botão é pressionado.
    with st.form("solicitacao_recrutamento"):
        prompt_usuario = st.text_area(
            "Instruções",
            key="prompt_input",
            height=150,
            placeholder=(
                "Ex.: Agende uma entrevista com nome@empresa.com em 30/10/2026, "
                "das 14h às 15h, para a vaga de Analista Financeiro, e registre "
                "o candidato na planilha."
            )
        )
        submitted = st.form_submit_button(
            "Processar solicitação",
            type="primary",
            use_container_width=True
        )

    # A variável submitted informa se o usuário enviou o formulário.
    if submitted:
        if not prompt_usuario.strip():
            # Um pedido vazio não chama o modelo nem os serviços Google.
            st.session_state.pop("resultado_processamento", None)
            st.warning("Escreva uma instrução antes de continuar.")
        else:
            # A função do agente retorna resultados ou erros para serem exibidos.
            with st.spinner("Processando a solicitação..."):
                st.session_state.resultado_processamento = executar_agente_rh(prompt_usuario)

    # O resultado fica na sessão para continuar visível após a atualização da tela.
    if "resultado_processamento" in st.session_state:
        st.markdown("### Resultado da solicitação")
        for tipo, conteudo in st.session_state.resultado_processamento:
            if tipo == "calendar":
                st.success(f"**Google Calendar e Meet**  \n{conteudo}")
            elif tipo in ("sheets", "planilha"):
                st.success(f"**Google Sheets**  \n{conteudo}")
            elif tipo == "texto":
                st.info(conteudo)
            elif tipo == "erro":
                st.error(conteudo)

with tab_dashboard:
    st.markdown("### Histórico de entrevistas")
    st.markdown(
        "Consulte os agendamentos feitos no calendário principal, incluindo entrevistas "
        "futuras, concluídas e canceladas."
    )

    if st.button("Atualizar histórico", type="primary"):
        with st.spinner("Consultando os agendamentos no Google Calendar..."):
            try:
                st.session_state.historico_agendamentos = listar_agendamentos()
                st.session_state.historico_agendamentos_atualizado = datetime.now(
                    ZoneInfo("America/Sao_Paulo")
                )
            except (GoogleAuthError, HttpError, OSError, ValueError) as erro:
                st.error(f"Não foi possível carregar o histórico: {erro}")

    if "historico_agendamentos" not in st.session_state:
        st.info("Selecione **Atualizar histórico** para carregar os agendamentos.")
    else:
        eventos = st.session_state.historico_agendamentos
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        linhas = []

        for evento in eventos:
            inicio_evento = evento.get("start") or evento.get("originalStartTime", {})
            fim_evento = evento.get("end", {})
            inicio_valor = inicio_evento.get("dateTime") or inicio_evento.get("date")
            fim_valor = fim_evento.get("dateTime") or fim_evento.get("date")

            inicio = (
                datetime.fromisoformat(inicio_valor.replace("Z", "+00:00"))
                if inicio_valor
                else None
            )
            fim = (
                datetime.fromisoformat(fim_valor.replace("Z", "+00:00"))
                if fim_valor
                else None
            )
            if inicio and inicio.tzinfo is None:
                inicio = inicio.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
            if fim and fim.tzinfo is None:
                fim = fim.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
            if inicio:
                inicio = inicio.astimezone(ZoneInfo("America/Sao_Paulo"))
            if fim:
                fim = fim.astimezone(ZoneInfo("America/Sao_Paulo"))

            if evento.get("status") == "cancelled":
                status = "Cancelada"
            elif fim and fim <= agora:
                status = "Concluída"
            elif inicio and inicio <= agora:
                status = "Em andamento"
            else:
                status = "Agendada"

            resumo = evento.get("summary", "Entrevista")
            candidato = resumo.removeprefix("Entrevista com ").strip()
            emails = ", ".join(
                participante.get("email", "")
                for participante in evento.get("attendees", [])
                if participante.get("email")
            )
            linhas.append(
                {
                    "_inicio": inicio,
                    "Candidato": candidato or "Não informado",
                    "E-mail": emails or "—",
                    "Início": inicio.strftime("%d/%m/%Y %H:%M") if inicio else "—",
                    "Fim": fim.strftime("%d/%m/%Y %H:%M") if fim else "—",
                    "Status": status,
                    "Google Meet": evento.get("hangoutLink", ""),
                    "Google Calendar": evento.get("htmlLink", ""),
                }
            )

        linhas.sort(
            key=lambda linha: linha["_inicio"] or datetime.min.replace(
                tzinfo=ZoneInfo("America/Sao_Paulo")
            ),
            reverse=True,
        )

        futuras = sum(linha["Status"] == "Agendada" for linha in linhas)
        em_andamento = sum(linha["Status"] == "Em andamento" for linha in linhas)
        concluidas = sum(linha["Status"] == "Concluída" for linha in linhas)
        canceladas = sum(linha["Status"] == "Cancelada" for linha in linhas)
        (
            metrica_total,
            metrica_futuras,
            metrica_andamento,
            metrica_concluidas,
            metrica_canceladas,
        ) = st.columns(5)
        metrica_total.metric("Total de entrevistas", len(linhas))
        metrica_futuras.metric("Agendadas", futuras)
        metrica_andamento.metric("Em andamento", em_andamento)
        metrica_concluidas.metric("Concluídas", concluidas)
        metrica_canceladas.metric("Canceladas", canceladas)

        atualizado = st.session_state.get("historico_agendamentos_atualizado")
        if atualizado:
            st.caption(f"Última atualização: {atualizado:%d/%m/%Y às %H:%M}")

        filtro_status = st.selectbox(
            "Filtrar por status",
            ["Todos", "Agendada", "Em andamento", "Concluída", "Cancelada"],
        )
        busca = st.text_input("Buscar por candidato ou e-mail").strip().casefold()
        linhas_filtradas = [
            linha
            for linha in linhas
            if (filtro_status == "Todos" or linha["Status"] == filtro_status)
            and (
                not busca
                or busca in linha["Candidato"].casefold()
                or busca in linha["E-mail"].casefold()
            )
        ]

        if linhas_filtradas:
            st.dataframe(
                [
                    {chave: valor for chave, valor in linha.items() if not chave.startswith("_")}
                    for linha in linhas_filtradas
                ],
                column_config={
                    "Google Meet": st.column_config.LinkColumn(
                        "Google Meet", display_text="Entrar"
                    ),
                    "Google Calendar": st.column_config.LinkColumn(
                        "Google Calendar", display_text="Abrir evento"
                    ),
                },
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Nenhum agendamento corresponde aos filtros selecionados.")