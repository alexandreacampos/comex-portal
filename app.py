import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
import plotly.express as px

# Configuração da página do Portal - Forçando o uso de toda a largura da tela com o novo nome
st.set_page_config(page_title="RMA ASSESSORIA EM COMEX", page_icon="🌐", layout="wide")

# --- BANCO DE USUÁRIOS DO PORTAL ---
USUARIOS = {
    "master": {"senha": "123", "perfil": "dono", "nome": "Diretor Comercial"},
    "mg": {"senha": "mg123", "perfil": "cliente", "nome": "M&G ASSET MANAGEMENT"},
    "triplay": {"senha": "tr123", "perfil": "cliente", "nome": "TRIPLAY Y TECAMAC"},
    "ricardo": {"senha": "rjs2026", "perfil": "dono", "nome": "RICARDO J. SANTOS"},
    "evandro": {"senha": "em2026", "perfil": "dono", "nome": "EVANDRO MARINI"}
}

# --- CONFIGURAÇÃO DO LINK DO GOOGLE SHEETS ---
LINK_GOOGLE_SHEETS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQd4qDmhLei9TiIuEb7n5kULXdYgmlsVGjGKDtXKuCzU5untJYDCnngCxoZ10dHnvSFVz2E1opKyb4s/pub?gid=416260151&single=true&output=csv"

# Dicionário auxiliar para tradução dos meses abreviados para Português
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

# --- SEQUÊNCIA LÓGICA OPERACIONAL DE STATUS ---
ORDEM_STATUS_LOGICO = [
    "Aguardando fábrica confirmar produção",
    "Booking foi solicitado, aguardando confirmação",
    "Aguardando coleta de container para estufagem",
    "Container vazio coletado para a estufagem da carga",
    "Containers entregues no porto. Aguardando embarque",
    "Embarcado",
    "Chegou no destino. Aguardando entrega",
    "Carga entregue no destino",
    "Autorizado",
    "Embarque finalizado",
    "Não Informado"
]

DICIONARIO_STATUS = {
    "Aguardando prontidão": "Aguardando fábrica confirmar produção",
    "Aguardando booking": "Booking foi solicitado, aguardando confirmação",
    "Aguardando coleta": "Aguardando coleta de container para estufagem",
    "Coletado": "Container vazio coletado para a estufagem da carga",
    "Aguardando embarque": "Containers entregues no porto. Aguardando embarque",
    "Embarcado": "Embarcado",
    "Desembarcado": "Chegou no destino. Aguardando entrega",
    "Aguardando entrega": "Chegou no destino. Aguardando entrega",
    "Entregue": "Carga entregue no destino",
    "Autorizado": "Autorizado",
    "Finalizado": "Embarque finalizado"
}

def traduzir_status(status_original):
    if pd.isna(status_original):
        return "Não Informado"
    status_limpo = str(status_original).strip().replace(".", "")
    for chave, traducao in DICIONARIO_STATUS.items():
        if chave.lower() in status_limpo.lower():
            return traducao
    return status_limpo

def limpar_e_converter_numero(valor):
    if pd.isna(valor):
        return 0.0
    try:
        if isinstance(valor, str):
            valor = valor.replace('.', '').replace(',', '.')
        return float(valor)
    except:
        return 0.0

def calcular_status_cobranca(linha):
    cobranca_excel = str(linha.get('Cobrança enviada', '')).strip().upper()
    booking_excel = str(linha.get('Nº. Booking', '')).strip()
    
    # Buscamos a situação original para não ter erro de leitura
    situacao_original = str(linha.get('Situação embarque', '')).strip().lower()
    status_traduzido = traduzir_status(linha.get('Situação embarque', ''))
    
    has_booking = pd.notna(linha.get('Nº. Booking')) and booking_excel != "" and booking_excel != "-" and booking_excel != "Não Informado"
    is_aguardando_prontidao = "confirmar produção" in status_traduzido.lower()

    # 🌟 NOVA REGRA: Se o status for "Aguardando Booking", capturamos aqui
    is_aguardando_booking = "aguardando booking" in situacao_original or "booking foi solicitado" in status_traduzido.lower()

    if "RECEBIDO" in cobranca_excel:
        return "Tudo Recebido"
    elif "SIM" in cobranca_excel:
        return "Cobrança Enviada"
    else:
        # AJUSTADO: Se tiver número de booking OU se o status for "Aguardando Booking", vai para Draft!
        if (has_booking or is_aguardando_booking) and not is_aguardando_prontidao:
            return "Aguardando Draft"
        else:
            return "Previsão Futura"

def calcular_financeiro_estrito(linha):
    status_cobranca = calcular_status_cobranca(linha)
    venda = limpar_e_converter_numero(linha.get('Venda USD', 0.0))
    recebido = limpar_e_converter_numero(linha.get('Venda Recebida USD', 0.0))
    
    saldo_calculado = max(0.0, venda - recebido)
    
    # Retorna: [Venda, Já Recebido, Contas a Receber, Aguarda Draft, Previsão Futura]
    if status_cobranca == "Tudo Recebido":
        realmente_recebido = max(venda, recebido)
        return pd.Series([venda, realmente_recebido, 0.0, 0.0, 0.0])
    elif status_cobranca == "Cobrança Enviada":
        return pd.Series([venda, recebido, saldo_calculado, 0.0, 0.0])
    elif status_cobranca == "Aguardando Draft":
        return pd.Series([venda, recebido, 0.0, saldo_calculado, 0.0])
    else:
        return pd.Series([venda, recebido, 0.0, 0.0, saldo_calculado])

def auditoria_custos_pagar(linha):
    status_custo = str(linha.get('Status processo', '')).strip().lower()
    frete_total = limpar_e_converter_numero(linha.get('Frete USD', 0.0))
    dut_total = limpar_e_converter_numero(linha.get('Dut/Despacho USD', 0.0))
    
    if frete_total == 0.0:
        frete_a_pagar = 0.0
    else:
        # Adicionado apenas o critério 'falta pagar dut' no final
        if 'tudo pago' in status_custo or 'falta pagar as locais' in status_custo or 'falta pagar dut e locais' in status_custo or 'falta pagar dut' in status_custo:
            frete_a_pagar = 0.0
        else:
            frete_a_pagar = frete_total

    if dut_total == 0.0:
        dut_a_pagar = 0.0
    else:
        # Adicionado apenas o critério 'falta pagar frete' no final
        if 'tudo pago' in status_custo or 'falta pagar as locais' in status_custo or 'falta pagar frete e locais' in status_custo or 'falta pagar frete' in status_custo:
            dut_a_pagar = 0.0
        else:
            dut_a_pagar = dut_total
            
    return pd.Series([frete_a_pagar, dut_a_pagar])

def formatar_semana_com_datas(ano, semana):
    try:
        segunda = datetime.strptime(f"{ano}-W{int(semana)}-1", "%G-W%V-%u")
        sexta = segunda + timedelta(days=4)
        return f"Week {int(semana):02d} - De {segunda.strftime('%d/%m')} a {sexta.strftime('%d/%m')}"
    except:
        return f"Week {int(semana):02d}"

def calcular_vencimento_e_alertas(linha):
    frete_a_pagar = linha.get('Falta Pagar Frete USD', 0.0)
    dut_a_pagar = linha.get('Falta Pagar DUT USD', 0.0)
    data_chegada = linha.get('ETA/ATA')
    
    if frete_a_pagar == 0.0 and dut_a_pagar == 0.0:
        return pd.Series([pd.NaT, 0, "", "Pago / Sem pendência"])
        
    if pd.isna(data_chegada):
        return pd.Series([pd.NaT, 0, "", "Vencimento Indefinido (Sem ETA)"])
        
    try:
        # ----------------------------------------------------------------------
        # TRAVA DE SEGURANÇA: dayfirst=True FORÇA O FORMATO BRASILEIRO (DD/MM/AAAA)
        # ----------------------------------------------------------------------
        dt_chegada = pd.to_datetime(data_chegada, dayfirst=True, errors='coerce')
        
        # Se a data falhar por algum motivo e virar NaT, evita cálculo errado
        if pd.isna(dt_chegada):
            return pd.Series([pd.NaT, 0, "", "Erro no formato da data"])
            
        dt_vencimento = dt_chegada - timedelta(days=7)
        
        if dt_vencimento.weekday() == 5:
            dt_vencimento = dt_vencimento - timedelta(days=1)
        elif dt_vencimento.weekday() == 6:
            dt_vencimento = dt_vencimento - timedelta(days=2)
            
        ano_venc, semana_ano, _ = dt_vencimento.isocalendar()
        texto_prazo_semana = formatar_semana_com_datas(ano_venc, semana_ano)
        
        hoje = datetime.now()
        dias_ate_chegada = (dt_chegada - hoje).days
        
        if dias_ate_chegada < 7:
            alerta = "🚨 Pagar urgente, carga chegando no destino!"
        else:
            alerta = "Aguardando pagamento"
            
        return pd.Series([dt_vencimento, semana_ano, texto_prazo_semana, alerta])
    except:
        return pd.Series([pd.NaT, 0, "", "Erro ao calcular data"])

def carregar_dados():
    try:
        df = pd.read_csv(LINK_GOOGLE_SHEETS)
        df.columns = df.columns.str.strip()
        
        if 'Mercadoria' not in df.columns: df['Mercadoria'] = "Não especificado"
        if 'Nº. Booking' not in df.columns: df['Nº. Booking'] = "Não Informado"
        if 'País destino' not in df.columns: df['País destino'] = "Não Informado"
        if 'Destino' not in df.columns: df['Destino'] = "Não Informado"
        if 'Ref. cliente' not in df.columns: df['Ref. cliente'] = "-"
        
        df['Qtde. volumes'] = df['Qtde. volumes'].apply(limpar_e_converter_numero).astype(int)
        df['Total container 40\''] = df['Total container 40\''].apply(limpar_e_converter_numero).astype(int)
        df['Metros cúbicos'] = df['Metros cúbicos'].apply(limpar_e_converter_numero)
        
        # Mapeamento estrito das 5 colunas financeiras incluindo o Draft estruturado
        df[['Venda USD', 'Venda Recebida USD', 'Saldo a Receber Real USD', 'Aguarda Draft USD', 'Previsão Cobrança Futura USD']] = df.apply(calcular_financeiro_estrito, axis=1)
        df[['Falta Pagar Frete USD', 'Falta Pagar DUT USD']] = df.apply(auditoria_custos_pagar, axis=1)
        df[['Data Vencimento Custo', 'Semana Vencimento', 'Prazo Pagamento Texto', 'Alerta Custo']] = df.apply(calcular_vencimento_e_alertas, axis=1)
        
        df['Situação embarque amigável'] = df['Situação embarque'].apply(traduzir_status)
        df['Diagnóstico de Cobrança'] = df.apply(calcular_status_cobranca, axis=1)
        
        return df
    except Exception as e:
        st.error(f"Erro ao ler os dados do Google Sheets: {e}")
        return None

# --- CONTROLE DE LOGIN ---
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.perfil = None
    st.session_state.nome_usuario = None

if not st.session_state.logado:
    st.title("🌐 RMA ASSESSORIA EM COMEX | Login")
    with st.form("form_login"):
        usuario = st.text_input("Usuário:")
        senha = st.text_input("Senha:", type="password")
        if st.form_submit_button("Entrar no Portal"):
            if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
                st.session_state.logado = True
                st.session_state.perfil = USUARIOS[usuario]["perfil"]
                st.session_state.nome_usuario = USUARIOS[usuario]["nome"]
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
else:
    df = carregar_dados()

    if df is not None:
        if st.session_state.perfil == "dono":
            aba_painel, aba_logout = st.tabs(["📊 Painel Controle Gerencial", "🚪 Sair / Logout"])
            
            with aba_logout:
                st.markdown(f"### Olá, **{st.session_state.nome_usuario}**")
                st.write("Clique no botão abaixo para encerrar sua sessão com segurança no portal.")
                if st.button("Confirmar Saída"):
                    st.session_state.logado = False
                    st.rerun()
            
            with aba_painel:
                st.title("📊 Controle Gerencial de Processos")
                st.markdown(f"*Usuário ativo: {st.session_state.nome_usuario}*")
                st.markdown("---")
                
                if st.button("🔄 Atualizar Dados do Google Sheets"):
                    st.rerun()
                
                # --- FILTROS RÁPIDOS ---
                st.markdown("### 🎛️ Filtros Rápidos")
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                
                clientes_disponiveis = ["Todos"] + list(df['Cliente'].dropna().unique())
                cliente_selecionado = col_f1.selectbox("Filtrar por Cliente:", clientes_disponiveis)
                
                status_disponiveis = ["Todos"] + list(df['Situação embarque amigável'].unique())
                status_selected = col_f2.selectbox("Status do embarque:", status_disponiveis)
                
                paises_disponiveis = ["Todos"] + list(df['País destino'].dropna().unique())
                pais_selecionado = col_f3.selectbox("País de destino:", paises_disponiveis)
                
                portos_disponiveis = ["Todos"] + list(df['Destino'].dropna().unique())
                porto_selecionado = col_f4.selectbox("Porto de Destino:", portos_disponiveis)
                
                df_filtrado = df.copy()
                if cliente_selecionado != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['Cliente'] == cliente_selecionado]
                if status_selected != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['Situação embarque amigável'] == status_selected]
                if pais_selecionado != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['País destino'] == pais_selecionado]
                if porto_selecionado != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['Destino'] == porto_selecionado]
                    
                st.markdown("---")
                
                # --- SEÇÃO DE GESTÃO DE PAGAMENTOS (FRETE / DUT) ---
                st.markdown("### 🚢 Cronograma e Gestão de Pagamentos (Frete / DUT)")
                df_custos_ativos = df_filtrado[(df_filtrado['Falta Pagar Frete USD'] > 0) | (df_filtrado['Falta Pagar DUT USD'] > 0)].copy()
                
                col_c1, col_c2 = st.columns([1.7, 1.3])
                with col_c1:
                    st.markdown("#### 📅 Próximos Pagamentos de Frete ou DUT")
                    if not df_custos_ativos.empty:
                        df_agenda = df_custos_ativos[[
                            'Data Vencimento Custo', 'Nº processo house', 'Cliente', 'Falta Pagar Frete USD', 'Falta Pagar DUT USD', 'Alerta Custo'
                        ]].copy()
                        df_agenda['Total Necessário USD'] = df_agenda['Falta Pagar Frete USD'] + df_agenda['Falta Pagar DUT USD']
                        df_agenda = df_agenda.sort_values(by='Data Vencimento Custo', ascending=True)
                        
                        df_agenda['Pagar Até'] = df_agenda['Data Vencimento Custo'].dt.strftime('%d/%m/%Y')
                        df_agenda['FRETE USD'] = df_agenda['Falta Pagar Frete USD'].map('$ {:,.2f}'.format)
                        df_agenda['DUT USD'] = df_agenda['Falta Pagar DUT USD'].map('$ {:,.2f}'.format)
                        df_agenda['Total'] = df_agenda['Total Necessário USD'].map('$ {:,.2f}'.format)
                        
                        df_agenda_exibir = df_agenda[['Nº processo house', 'Cliente', 'FRETE USD', 'DUT USD', 'Total', 'Pagar Até', 'Alerta Custo']]
                        df_agenda_exibir.columns = ['Processo', 'Cliente', 'Frete (USD)', 'Duty (USD)', 'Total', 'Pagar Até', 'Status / Alerta']
                        
                        st.dataframe(df_agenda_exibir, use_container_width=True, hide_index=True)
                        st.markdown(f"**Total Geral Necessário em Aberto: :green[$ {df_agenda['Total Necessário USD'].sum():,.2f}]**")
                    else:
                        st.success("🎉 Tudo em dia! Nenhum pagamento de Frete ou DUT pendente.")
                        
                with col_c2:
                    st.markdown("#### 🗓️ Pagamentos necessários por Semana do Ano")
                    if not df_custos_ativos.empty:
                        df_semanas = df_custos_ativos.groupby(['Semana Vencimento', 'Prazo Pagamento Texto']).agg(
                            Frete_Semana=('Falta Pagar Frete USD', 'sum'),
                            Dut_Semana=('Falta Pagar DUT USD', 'sum')
                        ).reset_index()
                        
                        df_semanas['Total_Semana'] = df_semanas['Frete_Semana'] + df_semanas['Dut_Semana']
                        df_semanas = df_semanas[df_semanas['Semana Vencimento'] > 0].sort_values(by='Semana Vencimento')
                        
                        df_semanas_exibir = df_semanas[['Prazo Pagamento Texto', 'Frete_Semana', 'Dut_Semana', 'Total_Semana']].copy()
                        df_semanas_exibir.columns = ['Prazo para pagamento', 'Frete (USD)', 'Duty (USD)', 'Total']
                        
                        df_semanas_exibir['Frete (USD)'] = df_semanas_exibir['Frete (USD)'].map('$ {:,.2f}'.format)
                        df_semanas_exibir['Duty (USD)'] = df_semanas_exibir['Duty (USD)'].map('$ {:,.2f}'.format)
                        df_semanas_exibir['Total'] = df_semanas_exibir['Total'].map('$ {:,.2f}'.format)
                        
                        st.dataframe(df_semanas_exibir, use_container_width=True, hide_index=True)
                    else:
                        st.info("Sem saídas previstas.")
                        
                st.markdown("---")
                
                # --- RESUMOS CONSOLIDADOS DE FATURAMENTO ---
                st.markdown("### 🗂️ Resumo consolidado de processos por status e vendas")
                col_tabela1, col_tabela2 = st.columns(2)
                
                with col_tabela1:
                    st.markdown("#### 📋 Volumes Por Status De Processos")
                    df_agrupado_status = df_filtrado.groupby('Situação embarque amigável').agg(
                        Qtd_Processos=('Nº processo house', 'count'),
                        Total_Containers=('Total container 40\'', 'sum'),
                        Total_Pallets=('Qtde. volumes', 'sum'),
                        Total_M3=('Metros cúbicos', 'sum')
                    ).reset_index()
                    df_agrupado_status.columns = ['Status do Processo', 'Processos', 'Containers', 'Pallets', 'M3']
                    
                    df_base_ordem = pd.DataFrame({'Status do Processo': ORDEM_STATUS_LOGICO})
                    df_resumo_status = pd.merge(df_base_ordem, df_agrupado_status, on='Status do Processo', how='left').fillna(0)
                    df_resumo_status['Processos'] = df_resumo_status['Processos'].astype(int)
                    df_resumo_status['Containers'] = df_resumo_status['Containers'].astype(int)
                    df_resumo_status['Pallets'] = df_resumo_status['Pallets'].astype(int)
                    df_resumo_status = df_resumo_status[df_resumo_status['Processos'] > 0]
                    
                    df_total_status = pd.DataFrame([{
                        'Status do Processo': '**TOTAL GERAL**',
                        'Processos': df_resumo_status['Processos'].sum(),
                        'Containers': df_resumo_status['Containers'].sum(),
                        'Pallets': df_resumo_status['Pallets'].sum(),
                        'M3': df_resumo_status['M3'].sum()
                    }])
                    df_resumo_status_com_total = pd.concat([df_resumo_status, df_total_status], ignore_index=True)
                    
                    st.dataframe(
                        df_resumo_status_com_total, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Processos": st.column_config.NumberColumn(format="%d"),
                            "Containers": st.column_config.NumberColumn(format="%d"),
                            "Pallets": st.column_config.NumberColumn(format="%d"),
                            "M3": st.column_config.NumberColumn(format="%.2f m³")
                        }
                    )
                    
                with col_tabela2:
                    st.markdown("#### 💵 Posição Financeira por Cliente")
                    
                    # 1. REMOVIDO: Tiramos o 'Total_Recebido' de dentro do agg()
                    df_resumo_financeiro = df_filtrado.groupby('Cliente').agg(
                        Qtd_Processos=('Nº processo house', 'count'),
                        Saldo_A_Receber_Real=('Saldo a Receber Real USD', 'sum'),
                        Aguarda_Draft=('Aguarda Draft USD', 'sum'),
                        Previsao_Futura=('Previsão Cobrança Futura USD', 'sum')
                    ).reset_index()
                    
                    # 2. AJUSTADO: Removido o nome 'Recebido' da lista para bater com o novo tamanho da tabela
                    df_resumo_financeiro.columns = ['Cliente', 'Qtd Proc', 'À Receber(Já Cobrado)', 'Aguarda Draft', 'Ag. Prev. Fábrica']
                    
                    df_resumo_financeiro['Qtd Proc'] = df_resumo_financeiro['Qtd Proc'].astype(int)
                    # REMOVIDO: A linha que formatava a coluna 'Recebido' com o cifrão $
                    df_resumo_financeiro['À Receber(Já Cobrado)'] = df_resumo_financeiro['À Receber(Já Cobrado)' ] .map('$ {:,.2f}'.format)
                    df_resumo_financeiro['Aguarda Draft'] = df_resumo_financeiro['Aguarda Draft'].map('$ {:,.2f}'.format)
                    df_resumo_financeiro['Ag. Prev. Fábrica'] = df_resumo_financeiro['Ag. Prev. Fábrica'].map('$ {:,.2f}'.format)
                    
                    st.dataframe(df_resumo_financeiro, use_container_width=True, hide_index=True)
                    
                    st.markdown("<br><h5 style='margin-bottom:12px; color: #333;'>📐 Indicadores Financeiros (Subtotal do Filtro)</h5>", unsafe_allow_html=True)
                    
                    # Mantemos o cálculo aqui caso precise usar em outro lugar, mas removemos do bloco visual
                    val_a_receber = df_filtrado['Saldo a Receber Real USD'].sum()
                    val_draft = df_filtrado['Aguarda Draft USD'].sum()
                    val_futuro = df_filtrado['Previsão Cobrança Futura USD'].sum()
                    
                    # 3. AJUSTADO: O bloco HTML agora só tem as 3 colunas de valores a entrar
                    html_indicadores = f"""
                    <div style="display: flex; gap: 15px; justify-content: space-between; flex-wrap: wrap; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #0066cc;">
                        <div style="flex: 1; min-width: 130px; display: flex; flex-direction: column; justify-content: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #555; margin-bottom: 4px;">Falta Receber, cobrança já enviada</span>
                            <span style="font-size: 18px; font-weight: bold; color: #c62828;">$ {val_a_receber:,.2f}</span>
                        </div>
                        <div style="flex: 1; min-width: 130px; display: flex; flex-direction: column; justify-content: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #555; margin-bottom: 4px;">Aguarda Draft p/ Cobrar</span>
                            <span style="font-size: 18px; font-weight: bold; color: #ef6c00;">$ {val_draft:,.2f}</span>
                        </div>
                        <div style="flex: 1; min-width: 130px; display: flex; flex-direction: column; justify-content: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #555; margin-bottom: 4px;">Previsão Futura</span>
                            <span style="font-size: 18px; font-weight: bold; color: #1565c0;">$ {val_futuro:,.2f}</span>
                        </div>
                    </div>
                    """
                    st.markdown(html_indicadores, unsafe_allow_html=True)
                
                st.markdown("---")
                
                # --- PREPARAÇÃO DE DATAS CRONOLÓGICAS EM PORTUGUÊS ---
                df_base_datas = df_filtrado.copy()
                if 'ETD/ATD' in df_base_datas.columns:
                    df_base_datas['Data_Embarque'] = pd.to_datetime(df_base_datas['ETD/ATD'], errors='coerce')
                    df_base_datas = df_base_datas.dropna(subset=['Data_Embarque']).copy()
                    
                    if not df_base_datas.empty:
                        df_base_datas['Ano_Mes_Chave'] = df_base_datas['Data_Embarque'].dt.to_period('M')
                        df_base_datas['Mês_PT'] = df_base_datas['Data_Embarque'].apply(lambda d: f"{MESES_PT[d.month]}/{d.year}")
                        lista_meses_ordenados = df_base_datas.sort_values('Ano_Mes_Chave')['Mês_PT'].unique()
                        
                        # --- 1º QUADRANTE: VOLUME MENSAL POR PAÍS DE DESTINO ---
                        st.markdown("### 🌐 Volume Mensal Por País De Destino")
                        col_m1, col_m2 = st.columns([1.3, 1.7])
                        
                        with col_m1:
                            st.write("**Selecione a opção de métrica:**")
                            tipo_metrica_pais = st.radio(
                                "Escolha a métrica - País:", ["Volume M³", "Containers 40HC", "Qtd Processos"],
                                horizontal=True, label_visibility="collapsed", key="metrica_pais"
                            )
                            
                            col_alvo_p = 'Metros cúbicos' if tipo_metrica_pais == "Volume M³" else ('Total container 40\'' if tipo_metrica_pais == "Containers 40HC" else 'Nº processo house')
                            funcao_alvo_p = 'sum' if tipo_metrica_pais != "Qtd Processos" else 'count'
                            
                            df_pivot_p = df_base_datas.pivot_table(
                                index='País destino', columns='Mês_PT', values=col_alvo_p, aggfunc=funcao_alvo_p, fill_value=0
                            )
                            colunas_p_existentes = [c for c in lista_meses_ordenados if c in df_pivot_p.columns]
                            df_pivot_p = df_pivot_p[colunas_p_existentes]
                            df_pivot_p.loc['TOTAL'] = df_pivot_p.sum(axis=0)
                            
                            st.dataframe(df_pivot_p, use_container_width=True)
                            
                        with col_m2:
                            st.markdown(f"#### Participação Total por País (%) - {tipo_metrica_pais}")
                            df_pizza_p = df_base_datas.groupby('País destino')[col_alvo_p].agg(funcao_alvo_p).reset_index()
                            df_pizza_p.columns = ['País de Destino', 'Valor Total']
                            
                            fig_pizza_p = px.pie(df_pizza_p, values='Valor Total', names='País de Destino', hole=0.35, color_discrete_sequence=px.colors.qualitative.Bold)
                            fig_pizza_p.update_traces(textinfo='percent+label', textposition='outside', insidetextorientation='radial')
                            fig_pizza_p.update_layout(
                                showlegend=True, uniformtext_minsize=10, uniformtext_mode='hide',
                                margin=dict(t=40, b=40, l=40, r=40), height=380
                            )
                            st.plotly_chart(fig_pizza_p, use_container_width=True)
                            
                        st.markdown("---")
                        
                        # --- 2º QUADRANTE: VOLUME MENSAL POR CLIENTE ---
                        st.markdown("### 👥 Volume Mensal Por Cliente")
                        col_cli1, col_cli2 = st.columns([1.3, 1.7])
                        
                        with col_cli1:
                            st.write("**Selecione a opção de métrica:**")
                            tipo_metrica_cli = st.radio(
                                "Escolha a métrica - Cliente:", ["Volume M³", "Containers 40HC", "Qtd Processos"],
                                horizontal=True, label_visibility="collapsed", key="metrica_cli"
                            )
                            
                            col_alvo_c = 'Metros cúbicos' if tipo_metrica_cli == "Volume M³" else ('Total container 40\'' if tipo_metrica_cli == "Containers 40HC" else 'Nº processo house')
                            funcao_alvo_c = 'sum' if tipo_metrica_cli != "Qtd Processos" else 'count'
                            
                            df_pivot_c = df_base_datas.pivot_table(
                                index='Cliente', columns='Mês_PT', values=col_alvo_c, aggfunc=funcao_alvo_c, fill_value=0
                            )
                            colunas_c_existentes = [c for c in lista_meses_ordenados if c in df_pivot_c.columns]
                            df_pivot_c = df_pivot_c[colunas_c_existentes]
                            df_pivot_c.loc['TOTAL'] = df_pivot_c.sum(axis=0)
                            
                            st.dataframe(df_pivot_c, use_container_width=True)
                            
                        with col_cli2:
                            st.markdown(f"#### Participação Total por Cliente (%) - {tipo_metrica_cli}")
                            df_pizza_c = df_base_datas.groupby('Cliente')[col_alvo_c].agg(funcao_alvo_c).reset_index()
                            df_pizza_c.columns = ['Cliente', 'Valor Total']
                            
                            fig_pizza_c = px.pie(df_pizza_c, values='Valor Total', names='Cliente', hole=0.35, color_discrete_sequence=px.colors.qualitative.Pastel)
                            fig_pizza_c.update_traces(textinfo='percent+label', textposition='outside', insidetextorientation='radial')
                            fig_pizza_c.update_layout(
                                showlegend=True, uniformtext_minsize=10, uniformtext_mode='hide',
                                margin=dict(t=40, b=40, l=40, r=40), height=380
                            )
                            st.plotly_chart(fig_pizza_c, use_container_width=True)
                            
                    else:
                        st.info("Nenhuma data de embarque válida para gerar as matrizes e gráficos de pizza.")
                else:
                    st.warning("Coluna 'ETD/ATD' não encontrada.")
                
                st.markdown("---")
                
                # --- LISTAGEM GERAL DE EMBARQUES ---
st.markdown("### 📈 Listagem Geral de Embarques")
busca_tabela = st.text_input("🔍 Digite o nome do Cliente ou Nº de Processo para filtrar a tabela abaixo instantaneamente (Estilo Excel):", "")

# --- TRATAMENTO E LIMPEZA DOS NOVOS VALORES FINANCEIROS ---
# Criando uma cópia segura a partir do df_filtrado para manipulação de dados
df_processado = df_filtrado.copy()

colunas_financeiras_novas = ['Venda USD', 'Frete USD', 'Dut/Despacho USD', 'Metros cúbicos']
for col in colunas_financeiras_novas:
    if col in df_processado.columns:
        # Garante que seja tratado como texto antes de substituir caracteres de milhar/decimal
        df_processado[col] = df_processado[col].astype(str).str.replace(',', '.', regex=False).str.replace(r'[^\d.]', '', regex=True)
        df_processado[col] = pd.to_numeric(df_processado[col], errors='coerce').fillna(0.0)
    else:
        # Cria a coluna zerada caso ela falte temporariamente na planilha online para evitar quebras
        df_processado[col] = 0.0

# --- APLICAÇÃO DOS NOVOS CÁLCULOS SOLICITADOS ---
# Valor SK USD = M3 * 6
df_processado['Valor SK USD'] = df_processado['Metros cúbicos'] * 6.0

# Valor FOB = Venda USD - Frete USD - Dut/Despacho USD - Valor SK USD
df_processado['Valor FOB'] = (
    df_processado['Venda USD'] - 
    df_processado['Frete USD'] - 
    df_processado['Dut/Despacho USD'] - 
    df_processado['Valor SK USD']
)

# Seleção das colunas incluindo as antigas operacionais e as 5 novas colunas financeiras
df_tabela_operacional = df_processado[[
    'Nº processo house', 'Cliente', 'Ref. cliente', 'Nº. Booking', 'Mercadoria', 
    'Total container 40\'', 'Qtde. volumes', 'Metros cúbicos', 'Situação embarque amigável', 
    'Diagnóstico de Cobrança', 'País destino',
    'Venda USD', 'Frete USD', 'Dut/Despacho USD', 'Valor SK USD', 'Valor FOB'
]].copy()

# Renomeando as colunas para o cabeçalho de exibição da tabela
df_tabela_operacional.columns = [
    'Nº Processo', 'Cliente', 'PO#', 'Booking', 'Mercadoria', 
    '40HC', 'Pallets', 'M3', 'Status do Embarque', 
    'Status da Cobrança', 'País de Destino',
    'Venda USD', 'Frete USD', 'Dut/Despacho USD', 'Valor SK USD', 'Valor FOB'
]

# Filtro dinâmico da tabela (barra de pesquisa)
if busca_tabela:
    df_tabela_operacional = df_tabela_operacional[
        df_tabela_operacional['Cliente'].astype(str).str.lower().str.contains(busca_tabela.lower()) |
        df_tabela_operacional['Nº Processo'].astype(str).str.lower().str.contains(busca_tabela.lower()) |
        df_tabela_operacional['Mercadoria'].astype(str).str.lower().str.contains(busca_tabela.lower())
    ]

# Renderização da Tabela com as configurações de colunas e formatos numéricos ajustados
st.dataframe(
    df_tabela_operacional, 
    use_container_width=True, 
    hide_index=True,
    column_config={
        "Nº Processo": st.column_config.TextColumn(width="small"),
        "Cliente": st.column_config.TextColumn(width="medium"),
        "40HC": st.column_config.NumberColumn(format="%d"),
        "Pallets": st.column_config.NumberColumn(format="%d"),
        "M3": st.column_config.NumberColumn(format="%.2f m³"),
        # Formatação das novas colunas de valores em USD
        "Venda USD": st.column_config.NumberColumn(format="%.2f"),
        "Frete USD": st.column_config.NumberColumn(format="%.2f"),
        "Dut/Despacho USD": st.column_config.NumberColumn(format="%.2f"),
        "Valor SK USD": st.column_config.NumberColumn(format="%.2f"),
        "Valor FOB": st.column_config.NumberColumn(format="%.2f")
    }
)

# Mapeia e gera o subtotal dinâmico com base no que está visível na tela
total_processos_f = len(df_tabela_operacional)
total_40hc_f = df_tabela_operacional['40HC'].sum()
total_pallets_f = df_tabela_operacional['Pallets'].sum()
total_m3_f = df_tabela_operacional['M3'].sum()

df_subtotal_excel = pd.DataFrame([{
    "Métrica": "🧮 SUBTOTAL DINÂMICO (Excel)",
    "Nº Processos": f"{total_processos_f} ativos",
    "Total 40HC": f"{int(total_40hc_f)} cont.",
    "Total Pallets": f"{int(total_pallets_f)} un.",
    "Volume M3": f"{total_m3_f:,.2f} m³"
}])

st.dataframe(df_subtotal_excel, use_container_width=True, hide_index=True)


# --- CORREÇÃO DA SINTAXE MUDANDO DE ELIF PARA IF ---
if st.session_state.perfil == "cliente":
    cliente_atual = st.session_state.nome_usuario
    aba_cliente, aba_logout_c = st.tabs([f"📦 Portal do Cliente | {cliente_atual}", "🚪 Sair / Logout"])
    
    with aba_logout_c:
        if st.button("Confirmar Saída"):
            st.session_state.logado = False
            st.rerun()
            
    with aba_cliente:
        df_cliente = df[df['Cliente'] == cliente_atual]
        if not df_cliente.empty:
            st.dataframe(df_cliente[['Nº processo house', 'Situação embarque amigável', 'Qtde. volumes', 'Metros cúbicos']], use_container_width=True, hide_index=True)
