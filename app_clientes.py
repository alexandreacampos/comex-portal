import streamlit as st
import pandas as pd
from datetime import datetime

# Configuração da página para modo largo (aproveita 100% da tela)
st.set_page_config(page_title="Customer Tracking Portal", layout="wide")

# =========================================================================
# 1. CONTROLE DE ACESSO (Estrutura nativa com suporte a salvar senha)
# =========================================================================
USUARIOS_PROVEDORES = {
    "mgasset": {"senha": "mg2026", "nome_planilha": "M&G ASSET MANAGEMENT"},
    "viking": {"senha": "vk2026", "nome_planilha": "VIKING"},
    "triplay": {"senha": "tp2026", "nome_planilha": "TRIPLAY Y TECAMAC"},
    "plaut": {"senha": "pt2026", "nome_planilha": "PLAUT"},
    "madesur": {"senha": "ms2026", "nome_planilha": "GL MADESUR"},
    "centralflorida": {"senha": "cf2026", "nome_planilha": "CENTRAL FLORIDA GLOBAL TRADE LLC"}
}

if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['cliente_nome'] = ""

if not st.session_state['logado']:
    st.subheader("🔑 Customer Portal - Login")
    
    with st.form("login_form", clear_on_submit=False):
        # Bloqueia qualquer sugestão de histórico do navegador usando "new-password"
        usuario = st.text_input("Username", autocomplete="new-password").strip().lower()
        senha = st.text_input("Password", type="password", autocomplete="current-password")
        botao_login = st.form_submit_button("Login")
        
        if botao_login:
            if usuario in USUARIOS_PROVEDORES and USUARIOS_PROVEDORES[usuario]["senha"] == senha:
                st.session_state['logado'] = True
                st.session_state['cliente_nome'] = USUARIOS_PROVEDORES[usuario]["nome_planilha"]
                st.rerun()
            else:
                st.error("Invalid Username or Password.")
    st.stop()

cliente_logado = st.session_state['cliente_nome']

# Inicializa o inicializador de filtros se não existir (essencial para o reset visual completo)
if 'refresh_version' not in st.session_state:
    st.session_state['refresh_version'] = 0

# =========================================================================
# 2. DICIONÁRIO DE STATUS
# =========================================================================
DICIONARIO_STATUS_INGLES = {
    "aguardando prontidao da mercadoria": "Waiting cargo readiness",
    "aguardando booking": "Booking requested. Waiting confirmation",
    "aguardando coleta": "Awaiting empty container pickup for stuffing",
    "coletado": "Container collected for cargo stuffing",
    "aguardando embarque": "Delivered at POL. Waiting load confirmation",
    "embarcado": "Shipped/On Water",
    "desembarcado": "Discharged at POD",
    "aguardando entrega": "Discharged at POD. Awaiting delivery at final destination.",
    "entregue": "Delivered at final destination",
    "autorizado": "Authorized",
    "finalizado": "Process finished"
}

DICIONARIO_COBRANCA_INGLES = {
    "sim": "Invoice Sent",
    "yes": "Invoice Sent",
    "tudo recebido": "Fully Paid",
    "fully paid": "Fully Paid"
}

# =========================================================================
# 3. CARREGAMENTO E TRATAMENTO DOS DADOS
# =========================================================================
@st.cache_data(ttl=60)
def carregar_dados_cliente(cliente):
    df = pd.read_csv("https://docs.google.com/spreadsheets/d/e/2PACX-1vQd4qDmhLei9TiIuEb7n5kULXdYgmlsVGjGKDtXKuCzU5untJYDCnngCxoZ10dHnvSFVz2E1opKyb4s/pub?gid=416260151&single=true&output=csv")
    df.columns = df.columns.str.strip()
    df['Cliente'] = df['Cliente'].astype(str).str.strip()
    df = df[df['Cliente'] == cliente].copy()
    return df

df_bruto = carregar_dados_cliente(cliente_logado)

if df_bruto.empty:
    st.title("🚢 Shipping Report M7PLY")
    st.warning(f"No active shipments found for {cliente_logado} at the moment.")
    if st.button("Log Out"):
        st.session_state['logado'] = False
        st.rerun()
    st.stop()

# --- Convertendo explicitamente ambas as colunas para Datetime real ---
df_bruto['ETD_Tratado'] = pd.to_datetime(df_bruto['ETD/ATD'], dayfirst=True, errors='coerce')
df_bruto['ETA_Tratado'] = pd.to_datetime(df_bruto['ETA/ATA'], dayfirst=True, errors='coerce')

# Processamento e Normalizações
coluna_situacao = 'Situação embarque' if 'Situação embarque' in df_bruto.columns else 'Situacao embarque'
df_bruto['status_limpo'] = df_bruto[coluna_situacao].astype(str).str.strip().str.lower()
df_bruto['status_limpo'] = df_bruto['status_limpo'].str.replace('ã', 'a', regex=False).str.replace('ç', 'c', regex=False).str.replace('ó', 'o', regex=False).str.replace('ê', 'e', regex=False)
df_bruto['Shipment Status'] = df_bruto['status_limpo'].map(DICIONARIO_STATUS_INGLES).fillna(df_bruto[coluna_situacao])
df_bruto['POD_Tratado'] = df_bruto['Destino'].fillna("Not Informed").astype(str).str.strip()
df_bruto['Final_Tratado'] = df_bruto['Destino final'].fillna(df_bruto['Destino']).fillna("Not Informed").astype(str).str.strip()
df_bruto['cobranca_limpa'] = df_bruto['Cobrança enviada'].astype(str).str.strip().str.lower()
df_bruto['Billing Status Translated'] = df_bruto['cobranca_limpa'].map(DICIONARIO_COBRANCA_INGLES).fillna("Future Payments")

for col in ['Venda USD', 'Venda Recebida USD', 'Metros cúbicos']:
    df_bruto[col] = df_bruto[col].astype(str).str.replace(',', '.', regex=False).str.replace(r'[^\d.]', '', regex=True)
    df_bruto[col] = pd.to_numeric(df_bruto[col], errors='coerce').fillna(0.0)

df_bruto['Saldo a Receber Real USD'] = df_bruto['Venda USD'] - df_bruto['Venda Recebida USD']
df_bruto['Previsão Cobrança Futura USD'] = df_bruto.apply(lambda r: r['Saldo a Receber Real USD'] if r['cobranca_limpa'] not in ['sim', 'yes', 'tudo recebido', 'fully paid'] else 0.0, axis=1)
df_bruto['Invoice Sent USD'] = df_bruto.apply(lambda r: r['Saldo a Receber Real USD'] if r['cobranca_limpa'] in ['sim', 'yes'] else 0.0, axis=1)
df_bruto['Qtde. volumes'] = pd.to_numeric(df_bruto['Qtde. volumes'], errors='coerce').fillna(0).astype(int)
df_bruto["Total container 40'"] = pd.to_numeric(df_bruto["Total container 40'"], errors='coerce').fillna(0).astype(int)

# =========================================================================
# 4. DESIGN CSS E OCULTAÇÃO DA SIDEBAR
# =========================================================================
st.markdown("""
    <style>
    /* Esconde completamente a barra lateral esquerda antiga */
    [data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* Ajustes finos no botão de Logout inline do topo */
    div.stButton > button {
        padding: 4px 18px !important;
        font-size: 13px !important;
        border-radius: 6px !important;
        height: auto !important;
    }
    
    /* Container para simular o visual dos cards de métrica */
    .metric-container {
        display: flex;
        flex-direction: column;
        padding: 5px 0;
    }
    .metric-label {
        font-size: 13px !important;
        color: rgb(49, 51, 63);
        font-weight: 400;
        margin-bottom: 2px;
        text-transform: uppercase;
    }
    .metric-value {
        font-size: 22px !important;
        font-weight: 700;
        margin: 0;
    }
    .metric-caption {
        font-size: 11.5px;
        color: #555;
        margin-top: 2px;
        font-weight: 500;
    }
    </style>
""", unsafe_allow_html=True)

# Linha do topo: Título à esquerda, Informações de login e Logout alinhados à direita
header_col1, header_col2 = st.columns([0.65, 0.35])

with header_col1:
    st.title("🚢 Shipping Report M7PLY")

with header_col2:
    st.write("") 
    st.write("")
    log_c1, log_c2 = st.columns([0.7, 0.3])
    with log_c1:
        st.markdown(f"<p style='text-align: right; margin-top: 5px; font-size: 14px; color: #444;'>Logged in as: <b>{cliente_logado}</b></p>", unsafe_allow_html=True)
    with log_c2:
        if st.button("Log Out", key="top_logout", type="secondary"):
            st.session_state['logado'] = False
            st.rerun()

st.markdown(f"Real-time supply chain - Create by Alexandre Campos")

# =========================================================================
# 5. DASHBOARD FINANCEIRO COM INJEÇÃO DE COR PRECISA
# =========================================================================
st.markdown("### 💰 Financial Overview")

# Somas financeiras calculadas
val_invoice = df_bruto['Invoice Sent USD'].sum()
val_future = df_bruto['Previsão Cobrança Futura USD'].sum()
val_balance = df_bruto['Saldo a Receber Real USD'].sum()

fm1, fm2, fm3 = st.columns(3)

with fm1:
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Invoice Sent</div>
            <div class="metric-value" style="color: #d32f2f;">$ {val_invoice:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)

with fm2:
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Future Forecast</div>
            <div class="metric-value" style="color: #1976d2;">$ {val_future:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)

with fm3:
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">Balance Due</div>
            <div class="metric-value" style="color: #111111;">$ {val_balance:,.2f}</div>
            <div class="metric-caption">(Sum of Invoice Sent + Future Forecast)</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# =========================================================================
# BOTÃO DE ATUALIZAÇÃO DE DADOS (Limpa planilha e altera o ID dos filtros)
# =========================================================================
col_btn_refresh, _ = st.columns([0.2, 0.8])
with col_btn_refresh:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear() # Limpa o cache da planilha
        
        # Altera o sufixo numérico. Isso força o Streamlit a destruir os selectboxes visuais antigos e recriá-los zerados
        st.session_state['refresh_version'] += 1
                
        st.rerun() # Reinicia a página limpa mantendo o login

# =========================================================================
# 6. FILTROS (Com chaves dinâmicas baseadas na versão do refresh para limpeza visual)
# =========================================================================
st.markdown("### 🔍 Filter Shipments")

# Criamos sufixos dinâmicos baseados no clique do refresh
v = st.session_state['refresh_version']

c1, c2, c3, c4 = st.columns(4)
with c1:
    filtro_status = st.selectbox("Shipment Status", ["All Statuses"] + sorted(list(df_bruto['Shipment Status'].dropna().unique())), key=f"f_status_{v}")
with c2:
    filtro_po = st.selectbox("Customer PO", ["All POs"] + sorted(list(df_bruto['Ref. cliente'].dropna().astype(str).unique())), key=f"f_po_{v}")
with c3:
    filtro_destino = st.selectbox("Destination Port (POD)", ["All Ports"] + sorted(list(df_bruto['POD_Tratado'].dropna().unique())), key=f"f_destino_{v}")
with c4:
    filtro_billing = st.selectbox("Billing Status", ["All Billing", "Fully Paid", "Invoice Sent", "Future Payments"], key=f"f_billing_{v}")

df_filtrado = df_bruto.copy()
if filtro_status != "All Statuses": df_filtrado = df_filtrado[df_filtrado['Shipment Status'] == filtro_status]
if filtro_po != "All POs": df_filtrado = df_filtrado[df_filtrado['Ref. cliente'].astype(str) == filtro_po]
if filtro_destino != "All Ports": df_filtrado = df_filtrado[df_filtrado['POD_Tratado'] == filtro_destino]
if filtro_billing != "All Billing": df_filtrado = df_filtrado[df_filtrado['Billing Status Translated'] == filtro_billing]
df_filtrado = df_filtrado.reset_index(drop=True)

# =========================================================================
# 7. TABELA EXECUTIVA PRINCIPAL E TOTAIS CONSOLIDADOS
# =========================================================================
st.markdown("### Executive Summary Table")
st.caption("💡 Select a row to view containers.")

# Criando a cópia exata para exibição mapeando as colunas reais de datetime para ETD e ETA
df_exibicao = df_filtrado[['Shipment Status', 'Nº processo house', 'Ref. cliente', 'Mercadoria', "Total container 40'", 'Qtde. volumes', 'Metros cúbicos', 'ETD_Tratado', 'ETA_Tratado', 'POD_Tratado', 'Final_Tratado', 'Billing Status Translated', 'Saldo a Receber Real USD', 'Previsão Cobrança Futura USD']].copy()
df_exibicao.columns = ['SHIPMENT STATUS', 'PROCESS', 'PO#', 'CARGO DESCRIPTION', "40HC", 'PALLETS', 'CBM (m³)', 'ETD', 'ETA', 'POD', 'FINAL DESTINATION', 'BILLING STATUS', 'BALANCE', 'FUTURE FORECAST']

# Renderização da Tabela Executiva utilizando a inteligência nativa DateColumn do Streamlit
selecao_tabela = st.dataframe(
    df_exibicao, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
    column_config={
        "40HC": st.column_config.NumberColumn(format="%d"),
        "PALLETS": st.column_config.NumberColumn(format="%d"),
        "CBM (m³)": st.column_config.NumberColumn(format="%.2f m³"),
        "BALANCE": st.column_config.NumberColumn(format="%.2f"),
        "FUTURE FORECAST": st.column_config.NumberColumn(format="%.2f"),
        # CORREÇÃO DA ORDENAÇÃO CRONOLÓGICA: Exibe as datas de forma estruturada internacionalmente sem virar string solta
        "ETD": st.column_config.DateColumn(format="MMM/DD/YYYY"),
        "ETA": st.column_config.DateColumn(format="MMM/DD/YYYY")
    }
)

# --- BLOCO DE TOTAIS EM UMA ÚNICA LINHA ---
tot_40hc = int(df_exibicao["40HC"].sum())
tot_pallets = int(df_exibicao["PALLETS"].sum())
tot_cbm = float(df_exibicao["CBM (m³)"].sum())

# CSS Inline elegante e compacto para alinhar tudo na mesma linha
st.markdown(f"""
    <div style="display: flex; justify-content: flex-end; gap: 40px; background-color: #f8f9fa; padding: 12px 24px; border-radius: 6px; border: 1px solid #e9ecef; margin-top: 10px; font-family: sans-serif;">
        <div style="font-size: 14px; color: #495057;">
            <span style="font-weight: 600; color: #6c757d; text-transform: uppercase; font-size: 12px;">Total 40'HC =</span> 
            <span style="font-weight: 700; color: #212529; font-size: 15px;">{tot_40hc:,}</span>
        </div>
        <div style="font-size: 14px; color: #495057;">
            <span style="font-weight: 600; color: #6c757d; text-transform: uppercase; font-size: 12px;">Total Pallets =</span> 
            <span style="font-weight: 700; color: #212529; font-size: 15px;">{tot_pallets:,}</span>
        </div>
        <div style="font-size: 14px; color: #495057;">
            <span style="font-weight: 600; color: #6c757d; text-transform: uppercase; font-size: 12px;">Total M³ =</span> 
            <span style="font-weight: 700; color: #212529; font-size: 15px;">{tot_cbm:,.2f} m³</span>
        </div>
    </div>
""", unsafe_allow_html=True)

st.markdown("---") 

# Detalhamento de containers ao clicar na linha da tabela
linhas_sel = selecao_tabela.get("selection", {}).get("rows", [])
if linhas_sel:
    dados = df_filtrado.iloc[linhas_sel[0]]
    st.markdown(f"""<div style="background-color: #f4f7f6; padding: 12px; border-left: 5px solid #0066cc; border-radius: 4px;">
        <b>📦 Containers for PO# {dados['Ref. cliente']}</b></div>""", unsafe_allow_html=True)
    txt_c = str(dados.get('Containers', ''))
    if txt_c and txt_c != 'nan':
        cont_list = [c.strip() for c in txt_c.split(',')]
        cols = st.columns(min(len(cont_list), 6))
        for i, u in enumerate(cont_list):
            with cols[i % 6]: st.code(u, language="")
    else:
        st.info("No containers assigned.")
