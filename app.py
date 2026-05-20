import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
import plotly.express as px

# Configuração da página do Portal
st.set_page_config(page_title="GlobalTrade Hub", page_icon="🌐", layout="wide")

# --- BANCO DE USUÁRIOS ---
USUARIOS = {
    "master": {"senha": "123", "perfil": "dono", "nome": "Diretor Comercial"},
    "mg": {"senha": "mg123", "perfil": "cliente", "nome": "M&G ASSET MANAGEMENT"},
    "triplay": {"senha": "tr123", "perfil": "cliente", "nome": "TRIPLAY Y TECAMAC"},
    "ricardo": {"senha": "rjs2026", "perfil": "dono", "nome": "RICARDO J. SANTOS"},
    "evandro": {"senha": "em2026", "perfil": "dono", "nome": "EVANDRO MARINI"}
}

LINK_GOOGLE_SHEETS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQd4qDmhLei9TiIuEb7n5kULXdYgmlsVGjGKDtXKuCzU5untJYDCnngCxoZ10dHnvSFVz2E1opKyb4s/pub?gid=416260151&single=true&output=csv"

MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

ORDEM_STATUS_LOGICO = [
    "Aguardando fábrica confirmar produção", "Booking foi solicitado, aguardando confirmação",
    "Aguardando coleta de container para estufagem", "Container vazio coletado para a estufagem da carga",
    "Containers entregues no porto. Aguardando embarque", "Embarcado",
    "Chegou no destino. Aguardando entrega", "Carga entregue no destino",
    "Autorizado", "Embarque finalizado", "Não Informado"
]

DICIONARIO_STATUS = {
    "Aguardando prontidão": "Aguardando fábrica confirmar produção",
    "Aguardando booking": "Booking foi solicitado, aguardando confirmação",
    "Aguardando coleta": "Aguardando coleta de container para estufagem",
    "Coletado": "Container vazio coletado para a estufagem da carga",
    "Aguardando embarque": "Containers entregues no porto. Aguardando embarque",
    "Embarcado": "Embarcado", "Desembarcado": "Chegou no destino. Aguardando entrega",
    "Aguardando entrega": "Chegou no destino. Aguardando entrega",
    "Entregue": "Carga entregue no destino", "Autorizado": "Autorizado", "Finalizado": "Embarque finalizado"
}

def traduzir_status(status_original):
    if pd.isna(status_original): return "Não Informado"
    status_limpo = str(status_original).strip().replace(".", "")
    for chave, traducao in DICIONARIO_STATUS.items():
        if chave.lower() in status_limpo.lower(): return traducao
    return status_limpo

def limpar_e_converter_numero(valor):
    if pd.isna(valor): return 0.0
    try:
        if isinstance(valor, str): valor = valor.replace('.', '').replace(',', '.')
        return float(valor)
    except: return 0.0

def calcular_status_cobranca(linha):
    cobranca_excel = str(linha.get('Cobrança enviada', '')).strip().upper()
    if "RECEBIDO" in cobranca_excel: return "Tudo Recebido"
    elif "SIM" in cobranca_excel: return "Cobrança Enviada"
    else: return "Previsão Futura"

def calcular_financeiro_estrito(linha):
    status_cobranca = calcular_status_cobranca(linha)
    venda = limpar_e_converter_numero(linha.get('Venda USD', 0.0))
    recebido = limpar_e_converter_numero(linha.get('Venda Recebida USD', 0.0))
    saldo_calculado = max(0.0, venda - recebido)
    
    if status_cobranca == "Tudo Recebido": return pd.Series([venda, recebido, 0.0, 0.0])
    elif status_cobranca == "Cobrança Enviada": return pd.Series([venda, recebido, saldo_calculado, 0.0])
    else: return pd.Series([venda, recebido, 0.0, saldo_calculado])

def auditoria_custos_pagar(linha):
    status_custo = str(linha.get('Status processo', '')).strip().lower()
    frete_total = limpar_e_converter_numero(linha.get('Frete USD', 0.0))
    dut_total = limpar_e_converter_numero(linha.get('Dut/Despacho USD', 0.0))
    
    if frete_total == 0.0: frete_a_pagar = 0.0
    else:
        if any(x in status_custo for x in ['tudo pago', 'falta pagar as locais', 'falta pagar dut e locais']): frete_a_pagar = 0.0
        else: frete_a_pagar = frete_total

    if dut_total == 0.0: dut_a_pagar = 0.0
    else:
        if any(x in status_custo for x in ['tudo pago', 'falta pagar as locais', 'falta pagar frete e locais']): dut_a_pagar = 0.0
        else: dut_a_pagar = dut_total
            
    return pd.Series([frete_a_pagar, dut_a_pagar])

def formatar_semana_com_datas(ano, semana):
    try:
        segunda = datetime.strptime(f"{ano}-W{int(semana)}-1", "%G-W%V-%u")
        sexta = segunda + timedelta(days=4)
        return f"Week {int(semana):02d} - De {segunda.strftime('%d/%m')} a {sexta.strftime('%d/%m')}"
    except: return f"Week {int(semana):02d}"

def calcular_vencimento_e_alertas(linha):
    frete_a_pagar = linha.get('Falta Pagar Frete USD', 0.0)
    dut_a_pagar = linha.get('Falta Pagar DUT USD', 0.0)
    data_chegada = linha.get('ETA/ATA')
    
    if frete_a_pagar == 0.0 and dut_a_pagar == 0.0: return pd.Series([pd.NaT, 0, "", "Pago / Sem pendência"])
    if pd.isna(data_chegada): return pd.Series([pd.NaT, 0, "", "Vencimento Indefinido (Sem ETA)"])
        
    try:
        dt_chegada = pd.to_datetime(data_chegada)
        dt_vencimento = dt_chegada - timedelta(days=7)
        if dt_vencimento.weekday() == 5: dt_vencimento -= timedelta(days=1)
        elif dt_vencimento.weekday() == 6: dt_vencimento -= timedelta(days=2)
            
        ano_venc, semana_ano, _ = dt_vencimento.isocalendar()
        texto_prazo_semana = formatar_semana_com_datas(ano_venc, semana_ano)
        dias_ate_chegada = (dt_chegada - datetime.now()).days
        alerta = "🚨 Pagar urgente, carga chegando!" if dias_ate_chegada < 7 else "Aguardando pagamento"
            
        return pd.Series([dt_vencimento, semana_ano, texto_prazo_semana, alerta])
    except: return pd.Series([pd.NaT, 0, "", "Erro ao calcular data"])

def carregar_dados():
    try:
        df = pd.read_csv(LINK_GOOGLE_SHEETS)
        df.columns = df.columns.str.strip()
        for col in ['Mercadoria', 'Nº. Booking', 'País destino', 'Destino', 'Ref. cliente']:
            if col not in df.columns: df[col] = "-" if col == 'Ref. cliente' else "Não Informado"
        
        df['Qtde. volumes'] = df['Qtde. volumes'].apply(limpar_e_converter_numero).astype(int)
        df['Total container 40\''] = df['Total container 40\''].apply(limpar_e_converter_numero).astype(int)
        df['Metros cúbicos'] = df['Metros cúbicos'].apply(limpar_e_converter_numero)
        
        df[['Venda USD', 'Venda Recebida USD', 'Saldo a Receber Real USD', 'Previsão Cobrança Futura USD']] = df.apply(calcular_financeiro_estrito, axis=1)
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
    st.session_state.logado, st.session_state.perfil, st.session_state.nome_usuario = False, None, None

if not st.session_state.logado:
    st.title("🌐 GlobalTrade Hub | Login")
    with st.form("form_login"):
        usuario = st.text_input("Usuário:")
        senha = st.text_input("Senha:", type="password")
        if st.form_submit_button("Entrar no Portal"):
            if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
                st.session_state.logado = True
                st.session_state.perfil = USUARIOS[usuario]["perfil"]
                st.session_state.nome_usuario = USUARIOS[usuario]["nome"]
                st.rerun()
            else: st.error("Usuário ou senha incorretos.")
else:
    df = carregar_dados()
    if df is not None:
        # ==========================================
        # PERFIL INTERNO: DONO / DIRETORIA
        # ==========================================
        if st.session_state.perfil == "dono":
            aba_painel, aba_logout = st.tabs(["📊 Painel Controle Gerencial", "🚪 Sair / Logout"])
            
            with aba_logout:
                st.markdown(f"### Olá, **{st.session_state.nome_usuario}**")
                if st.button("Confirmar Saída"):
                    st.session_state.logado = False
                    st.rerun()
            
            with aba_painel:
                st.title("📊 Controle Gerencial de Processos")
                if st.button("🔄 Atualizar Dados do Google Sheets"): st.rerun()
                
                st.markdown("### 🎛️ Filtros Rápidos")
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                cliente_selecionado = col_f1.selectbox("Filtrar por Cliente:", ["Todos"] + list(df['Cliente'].dropna().unique()))
                status_selected = col_f2.selectbox("Status do embarque:", ["Todos"] + list(df['Situação embarque amigável'].unique()))
                pais_selecionado = col_f3.selectbox("País de destino:", ["Todos"] + list(df['País destino'].dropna().unique()))
                porto_selecionado = col_f4.selectbox("Porto de Destino:", ["Todos"] + list(df['Destino'].dropna().unique()))
                
                df_filtrado = df.copy()
                if cliente_selecionado != "Todos": df_filtrado = df_filtrado[df_filtrado['Cliente'] == cliente_selecionado]
                if status_selected != "Todos": df_filtrado = df_filtrado[df_filtrado['Situação embarque amigável'] == status_selected]
                if pais_selecionado != "Todos": df_filtrado = df_filtrado[df_filtrado['País destino'] == pais_selecionado]
                if porto_selecionado != "Todos": df_filtrado = df_filtrado[df_filtrado['Destino'] == porto_selecionado]
                    
                st.markdown("---")
                st.markdown("### 🚢 Cronograma e Gestão de Pagamentos (Frete / DUT)")
                df_custos_ativos = df_filtrado[(df_filtrado['Falta Pagar Frete USD'] > 0) | (df_filtrado['Falta Pagar DUT USD'] > 0)].copy()
                
                col_c1, col_c2 = st.columns([1.7, 1.3])
                with col_c1:
                    st.markdown("#### 📅 Próximos Pagamentos de Frete ou DUT")
                    if not df_custos_ativos.empty:
                        df_agenda = df_custos_ativos[['Data Vencimento Custo', 'Nº processo house', 'Cliente', 'Falta Pagar Frete USD', 'Falta Pagar DUT USD', 'Alerta Custo']].copy()
                        df_agenda['Total Necessário USD'] = df_agenda['Falta Pagar Frete USD'] + df_agenda['Falta Pagar DUT USD']
                        df_agenda = df_agenda.sort_values(by='Data Vencimento Custo')
                        df_agenda['Pagar Até'] = df_agenda['Data Vencimento Custo'].dt.strftime('%d/%m/%Y')
                        df_agenda['FRETE USD'] = df_agenda['Falta Pagar Frete USD'].map('$ {:,.2f}'.format)
                        df_agenda['DUT USD'] = df_agenda['Falta Pagar DUT USD'].map('$ {:,.2f}'.format)
                        df_agenda['Total'] = df_agenda['Total Necessário USD'].map('$ {:,.2f}'.format)
                        
                        df_agenda_exibir = df_agenda[['Nº processo house', 'Cliente', 'FRETE USD', 'DUT USD', 'Total', 'Pagar Até', 'Alerta Custo']]
                        df_agenda_exibir.columns = ['Processo', 'Cliente', 'Frete (USD)', 'Duty (USD)', 'Total', 'Pagar Até', 'Status / Alerta']
                        st.dataframe(df_agenda_exibir, use_container_width=True, hide_index=True)
                        st.markdown(f"**Total Geral em Aberto: :green[$ {df_agenda['Total Necessário USD'].sum():,.2f}]**")
                    else: st.success("🎉 Tudo em dia! Nenhum pagamento pendente.")
                        
                with col_c2:
                    st.markdown("#### 🗓️ Pagamentos por Semana do Ano")
                    if not df_custos_ativos.empty:
                        df_semanas = df_custos_ativos.groupby(['Semana Vencimento', 'Prazo Pagamento Texto']).agg(F_Semana=('Falta Pagar Frete USD', 'sum'), D_Semana=('Falta Pagar DUT USD', 'sum')).reset_index()
                        df_semanas['T_Semana'] = df_semanas['F_Semana'] + df_semanas['D_Semana']
                        df_semanas = df_semanas[df_semanas['Semana Vencimento'] > 0].sort_values(by='Semana Vencimento')
                        df_semanas_exibir = df_semanas[['Prazo Pagamento Texto', 'F_Semana', 'D_Semana', 'T_Semana']].copy()
                        df_semanas_exibir.columns = ['Prazo para pagamento', 'Frete (USD)', 'Duty (USD)', 'Total']
                        df_semanas_exibir['Frete (USD)'] = df_semanas_exibir['Frete (USD)'].map('$ {:,.2f}'.format)
                        df_semanas_exibir['Duty (USD)'] = df_semanas_exibir['Duty (USD)'].map('$ {:,.2f}'.format)
                        df_semanas_exibir['Total'] = df_semanas_exibir['Total'].map('$ {:,.2f}'.format)
                        st.dataframe(df_semanas_exibir, use_container_width=True, hide_index=True)
                    else: st.info("Sem saídas previstas.")
                        
                st.markdown("---")
                st.markdown("### 🗂️ Resumo por Status e Vendas")
                col_tabela1, col_tabela2 = st.columns(2)
                
                with col_tabela1:
                    st.markdown("#### 📋 Volumes Por Status De Processos")
                    df_agrupado_status = df_filtrado.groupby('Situação embarque amigável').agg(Q_Proc=('Nº processo house', 'count'), T_Cnt=('Total container 40\'', 'sum'), T_Pal=('Qtde. volumes', 'sum'), T_M3=('Metros cúbicos', 'sum')).reset_index()
                    df_agrupado_status.columns = ['Status do Processo', 'Processos', 'Containers', 'Pallets', 'M3']
                    df_resumo_status = pd.merge(pd.DataFrame({'Status do Processo': ORDEM_STATUS_LOGICO}), df_agrupado_status, on='Status do Processo', how='left').fillna(0)
                    df_resumo_status = df_resumo_status[df_resumo_status['Processos'] > 0]
                    df_total_status = pd.DataFrame([{'Status do Processo': '**TOTAL GERAL**', 'Processos': df_resumo_status['Processos'].sum(), 'Containers': df_resumo_status['Containers'].sum(), 'Pallets': df_resumo_status['Pallets'].sum(), 'M3': df_resumo_status['M3'].sum()}])
                    
                    st.dataframe(pd.concat([df_resumo_status, df_total_status], ignore_index=True), use_container_width=True, hide_index=True, column_config={"Processos": st.column_config.NumberColumn(format="%d"), "Containers": st.column_config.NumberColumn(format="%d"), "Pallets": st.column_config.NumberColumn(format="%d"), "M3": st.column_config.NumberColumn(format="%.2f m³")})
                    
                with col_tabela2:
                    st.markdown("#### 💵 Posição Financeira por Cliente")
                    df_resumo_financeiro = df_filtrado.groupby('Cliente').agg(Q_P=('Nº processo house', 'count'), T_Rec=('Venda Recebida USD', 'sum'), S_Rec=('Saldo a Receber Real USD', 'sum'), P_Fut=('Previsão Cobrança Futura USD', 'sum')).reset_index()
                    df_resumo_financeiro.columns = ['Cliente', 'Processos', 'Já Recebido', 'Falta Receber', 'Valores Futuros']
                    for c in ['Já Recebido', 'Falta Receber', 'Valores Futuros']: df_resumo_financeiro[c] = df_resumo_financeiro[c].map('$ {:,.2f}'.format)
                    st.dataframe(df_resumo_financeiro, use_container_width=True, hide_index=True)
                    
                    val_recebido, val_a_receber, val_futuro = df_filtrado['Venda Recebida USD'].sum(), df_filtrado['Saldo a Receber Real USD'].sum(), df_filtrado['Previsão Cobrança Futura USD'].sum()
                    st.markdown(f"""
                    <div style="display: flex; gap: 15px; justify-content: space-between; flex-wrap: wrap; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #0066cc;">
                        <div style="flex: 1;"><span style="font-size: 13px; color: #555;">Total Já Recebido</span><br><span style="font-size: 18px; font-weight: bold; color: #2e7d32;">$ {val_recebido:,.2f}</span></div>
                        <div style="flex: 1;"><span style="font-size: 13px; color: #555;">Contas a Receber Real</span><br><span style="font-size: 18px; font-weight: bold; color: #c62828;">$ {val_a_receber:,.2f}</span></div>
                        <div style="flex: 1;"><span style="font-size: 13px; color: #555;">Previsão Futura</span><br><span style="font-size: 18px; font-weight: bold; color: #1565c0;">$ {val_futuro:,.2f}</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("---")
                df_base_datas = df_filtrado.copy()
                if 'ETD/ATD' in df_base_datas.columns:
                    df_base_datas['Data_Embarque'] = pd.to_datetime(df_base_datas['ETD/ATD'], errors='coerce')
                    df_base_datas = df_base_datas.dropna(subset=['Data_Embarque']).copy()
                    if not df_base_datas.empty:
                        df_base_datas['Ano_Mes_Chave'] = df_base_datas['Data_Embarque'].dt.to_period('M')
                        df_base_datas['Mês_PT'] = df_base_datas['Data_Embarque'].apply(lambda d: f"{MESES_PT[d.month]}/{d.year}")
                        lista_meses_ordenados = df_base_datas.sort_values('Ano_Mes_Chave')['Mês_PT'].unique()
                        
                        st.markdown("### 🌐 Volume Mensal Por País De Destino")
                        col_m1, col_m2 = st.columns([1.3, 1.7])
                        with col_m1:
                            t_m_p = st.radio("Métrica País:", ["Volume M³", "Containers 40HC", "Qtd Processos"], horizontal=True, label_visibility="collapsed", key="m_p")
                            c_a_p = 'Metros cúbicos' if t_m_p == "Volume M³" else ('Total container 40\'' if t_m_p == "Containers 40HC" else 'Nº processo house')
                            f_a_p = 'sum' if t_m_p != "Qtd Processos" else 'count'
                            df_pivot_p = df_base_datas.pivot_table(index='País destino', columns='Mês_PT', values=c_a_p, aggfunc=f_a_p, fill_value=0)
                            df_pivot_p = df_pivot_p[[c for c in lista_meses_ordenados if c in df_pivot_p.columns]]
                            df_pivot_p.loc['TOTAL'] = df_pivot_p.sum(axis=0)
                            st.dataframe(df_pivot_p, use_container_width=True)
                        with col_m2:
                            df_pizza_p = df_base_datas.groupby('País destino')[c_a_p].agg(f_a_p).reset_index(name='V')
                            st.plotly_chart(px.pie(df_pizza_p, values='V', names='País destino', hole=0.35).update_layout(margin=dict(t=20,b=20,l=20,r=20), height=280), use_container_width=True)
                            
                        st.markdown("### 👥 Volume Mensal Por Cliente")
                        col_cli1, col_cli2 = st.columns([1.3, 1.7])
                        with col_cli1:
                            t_m_c = st.radio("Métrica Cliente:", ["Volume M³", "Containers 40HC", "Qtd Processos"], horizontal=True, label_visibility="collapsed", key="m_c")
                            c_a_c = 'Metros cúbicos' if t_m_c == "Volume M³" else ('Total container 40\'' if t_m_c == "Containers 40HC" else 'Nº processo house')
                            f_a_c = 'sum' if t_m_c != "Qtd Processos" else 'count'
                            df_pivot_c = df_base_datas.pivot_table(index='Cliente', columns='Mês_PT', values=c_a_c, aggfunc=f_a_c, fill_value=0)
                            df_pivot_c = df_pivot_c[[c for c in lista_meses_ordenados if c in df_pivot_c.columns]]
                            df_pivot_c.loc['TOTAL'] = df_pivot_c.sum(axis=0)
                            st.dataframe(df_pivot_c, use_container_width=True)
                        with col_cli2:
                            df_pizza_c = df_base_datas.groupby('Cliente')[c_a_c].agg(f_a_c).reset_index(name='V')
                            st.plotly_chart(px.pie(df_pizza_c, values='V', names='Cliente', hole=0.35).update_layout(margin=dict(t=20,b=20,l=20,r=20), height=280), use_container_width=True)
                
                st.markdown("---")
                st.markdown("### 📈 Listagem Geral de Embarques")
                busca_tabela = st.text_input("🔍 Pesquisar Cliente, Processo ou Mercadoria (Estilo Excel):")
                df_tab = df_filtrado[['Nº processo house', 'Cliente', 'Ref. cliente', 'Nº. Booking', 'Mercadoria', 'Total container 40\'', 'Qtde. volumes', 'Metros cúbicos', 'Situação embarque amigável', 'Diagnóstico de Cobrança', 'País destino']].copy()
                df_tab.columns = ['Nº Processo', 'Cliente', 'PO#', 'Booking', 'Mercadoria', '40HC', 'Pallets', 'M3', 'Status do Embarque', 'Status da Cobrança', 'País de Destino']
                
                if busca_tabela:
                    df_tab = df_tab[df_tab['Cliente'].astype(str).str.lower().str.contains(busca_tabela.lower()) | df_tab['Nº Processo'].astype(str).str.lower().str.contains(busca_tabela.lower()) | df_tab['Mercadoria'].astype(str).str.lower().str.contains(busca_tabela.lower())]
                
                st.dataframe(df_tab, use_container_width=True, hide_index=True, column_config={"40HC": st.column_config.NumberColumn(format="%d"), "Pallets": st.column_config.NumberColumn(format="%d"), "M3": st.column_config.NumberColumn(format="%.2f m³")})
                
                df_subtotal_excel = pd.DataFrame([{"Métrica": "🧮 SUBTOTAL DINÂMICO", "Nº Processos": f"{len(df_tab)} ativos", "Total 40HC": f"{int(df_tab['40HC'].sum())} cont.", "Total Pallets": f"{int(df_tab['Pallets'].sum())} un.", "Volume M3": f"{df_tab['M3'].sum():,.2f} m³"}])
                st.dataframe(df_subtotal_excel, use_container_width=True, hide_index=True)

        # ==========================================
        # PERFIL EXTERNO: PORTAL DO CLIENTE
        # ==========================================
        elif st.session_state.perfil == "cliente":
            cliente_atual = st.session_state.nome_usuario
            aba_cliente, aba_logout_c = st.tabs([f"📦 Portal do Cliente | {cliente_atual}", "🚪 Sair / Logout"])
            
            with aba_logout_c:
                if st.button("Confirmar Saída", key="btn_logout_c"):
                    st.session_state.logado = False
                    st.rerun()
                    
            with aba_cliente:
                st.title(f"📦 Painel de Acompanhamento - {cliente_atual}")
                df_cliente = df[df['Cliente'] == cliente_atual].copy()
                
                if not df_cliente.empty:
                    col_card1, col_card2, col_card3, col_card4 = st.columns(4)
                    col_card1.metric("📋 Total Processos", f"{len(df_cliente)} ativos")
                    
                    # Evitando o erro das aspas duplas usando o método .get() de forma limpa:
                    total_containers_40hc = int(df_cliente.get("Total container 40'", pd.Series([0])).sum())
                    col_card2.metric("🚢 Containers (40HC)", f"{total_containers_40hc} un.")
                    
                    col_card3.metric("📦 Volumes / Pallets", f"{int(df_cliente['Qtde. volumes'].sum())} un.")
                    col_card4.metric("📐 Volume Total (M³)", f"{df_cliente['Metros cúbicos'].sum():,.2f} m³")
                    
                    st.markdown("---")
                    busca_cliente = st.text_input("🔍 Pesquisar por Nº de Processo, Mercadoria ou PO#:")
                    df_exib_c = df_cliente[['Nº processo house', 'Ref. cliente', 'Nº. Booking', 'Mercadoria', "Total container 40'", 'Qtde. volumes', 'Metros cúbicos', 'Situação embarque amigável']].copy()
                    df_exib_c.columns = ['Nº Processo', 'PO#', 'Booking', 'Mercadoria', '40HC', 'Pallets', 'Volume (M³)', 'Status do Embarque']
                    
                    if busca_cliente:
                        df_exib_c = df_exib_c[df_exib_c['Nº Processo'].astype(str).str.lower().str.contains(busca_cliente.lower()) | df_exib_c['Mercadoria'].astype(str).str.lower().str.contains(busca_cliente.lower()) | df_exib_c['PO#'].astype(str).str.lower().str.contains(busca_cliente.lower())]
                    
                    st.dataframe(df_exib_c, use_container_width=True, hide_index=True, column_config={"40HC": st.column_config.NumberColumn(format="%d"), "Pallets": st.column_config.NumberColumn(format="%d"), "Volume (M³)": st.column_config.NumberColumn(format="%.2f m³")})
                else: st.info("Nenhum processo ativo encontrado para a sua conta no momento.")
