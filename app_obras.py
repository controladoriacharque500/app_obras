import streamlit as st
import pandas as pd
from gspread import service_account_from_dict
from datetime import datetime, timedelta
import json

# --- Configurações da Nova Planilha ---
PLANILHA_NOME = "Controle_Obras" # O nome da sua nova planilha
ABA_INFO = "Obras_Info"
ABA_DESPESAS = "Despesas_Semanas"

# --- Funções de Autenticação e Conexão (Reutilizando seu código) ---

@st.cache_resource(ttl=None) # Cache eterno para o objeto de conexão
def get_gspread_client():
    """Conecta e retorna o cliente GSpread usando st.secrets."""
    try:
        if "gcp_service_account" not in st.secrets:
             raise ValueError("Nenhuma seção [gcp_service_account] encontrada no st.secrets.")

        secrets_dict = dict(st.secrets["gcp_service_account"])
        private_key_corrompida = secrets_dict["private_key"]

        # Lógica de limpeza da chave
        private_key_limpa = private_key_corrompida.replace('\n', '').replace(' ', '')
        private_key_limpa = private_key_limpa.replace('-----BEGINPRIVATEKEY-----', '').replace('-----ENDPRIVATEKEY-----', '')
        padding_necessario = len(private_key_limpa) % 4
        if padding_necessario != 0:
            private_key_limpa += '=' * (4 - padding_necessario)
        secrets_dict["private_key"] = f"-----BEGIN PRIVATE KEY-----\n{private_key_limpa}\n-----END PRIVATE KEY-----\n"

        gc = service_account_from_dict(secrets_dict)
        return gc
    except Exception as e:
        st.error(f"Erro de autenticação/acesso: Verifique se a chave no secrets.toml está correta. Detalhe: {e}")
        return None

# --- Funções de Leitura de Dados (Banco de Dados) ---

# Limpar o cache a cada 10 minutos (600s)
@st.cache_data(ttl=600)
def load_data():
    """Carrega dados de ambas as abas e retorna dois DataFrames."""
    gc = get_gspread_client()
    if not gc:
        return pd.DataFrame(), pd.DataFrame()

    try:
        planilha = gc.open(PLANILHA_NOME)

        # 1. Carregar OBRAS_INFO
        aba_info = planilha.worksheet(ABA_INFO)
        df_info = pd.DataFrame(aba_info.get_all_records())

        # 2. Carregar DESPESAS_SEMANAS
        aba_despesas = planilha.worksheet(ABA_DESPESAS)
        df_despesas = pd.DataFrame(aba_despesas.get_all_records())

        # 3. Limpeza e Conversão de Tipos
        if not df_info.empty:
            df_info['Obra_ID'] = df_info['Obra_ID'].astype(str)
            df_info['Valor_Total_Inicial'] = pd.to_numeric(df_info['Valor_Total_Inicial'], errors='coerce')
            df_info['Data_Inicio'] = pd.to_datetime(df_info['Data_Inicio'], errors='coerce')

        if not df_despesas.empty:
            df_despesas['Obra_ID'] = df_despesas['Obra_ID'].astype(str)
            df_despesas['Gasto_Semana'] = pd.to_numeric(df_despesas['Gasto_Semana'], errors='coerce')

        return df_info, df_despesas

    except Exception as e:
        st.error(f"Erro ao carregar dados: Verifique se a planilha '{PLANILHA_NOME}' e as abas '{ABA_INFO}' e '{ABA_DESPESAS}' existem e se as colunas estão corretas. Detalhe: {e}")
        return pd.DataFrame(), pd.DataFrame()


# --- Funções de Escrita de Dados (Simulando INSERT) ---

def insert_new_obra(gc, data):
    """Insere uma nova obra na aba Obras_Info."""
    try:
        planilha = gc.open(PLANILHA_NOME)
        aba_info = planilha.worksheet(ABA_INFO)
        # Os valores devem ser uma lista [ID, Nome, Valor, Data]
        aba_info.append_row(data)
        st.toast("✅ Nova obra cadastrada com sucesso!")
        load_data.clear() # Limpa o cache para recarregar os dados
    except Exception as e:
        st.error(f"Erro ao inserir nova obra: {e}")

def insert_new_despesa(gc, data):
    """Insere uma nova despesa semanal na aba Despesas_Semanas."""
    try:
        planilha = gc.open(PLANILHA_NOME)
        aba_despesas = planilha.worksheet(ABA_DESPESAS)
        # Os valores devem ser uma lista [Obra_ID, Semana_Ref, Data_Semana, Gasto_Semana]
        aba_despesas.append_row(data)
        st.toast("✅ Despesa semanal registrada com sucesso!")
        load_data.clear() # Limpa o cache para recarregar os dados
    except Exception as e:
        st.error(f"Erro ao registrar despesa: {e}")


# --- Interface do Usuário (Streamlit) ---

def show_cadastro_obra(gc):
    st.header("1. Cadastrar Nova Obra")
    df_info, _ = load_data(gc)

    # Gera o próximo ID (Simples, mas funcional)
    next_id = 1
    if not df_info.empty:
        try:
            # Pega o ID máximo e adiciona 1
            next_id = df_info['Obra_ID'].astype(int).max() + 1
        except:
             # Caso a coluna não seja numérica
             next_id = len(df_info) + 1

    next_id_str = str(next_id).zfill(3)
    st.info(f"O próximo ID da Obra será: **{next_id_str}**")

    with st.form("form_obra"):
        nome = st.text_input("Nome da Obra", placeholder="Ex: Casa Alpha")
        valor = st.number_input("Valor Total Inicial (R$)", min_value=0.0, format="%.2f")
        data_inicio = st.date_input("Data de Início da Obra")

        submitted = st.form_submit_button("Cadastrar Obra")

        if submitted:
            if nome and valor > 0:
                data_list = [next_id_str, nome, valor, data_inicio.strftime('%Y-%m-%d')]
                insert_new_obra(gc, data_list)
            else:
                st.warning("Preencha todos os campos corretamente.")

def show_registro_despesa(gc, df_info, df_despesas):
    st.header("2. Registrar Despesa Semanal")

    if df_info.empty:
        st.warning("Cadastre pelo menos uma obra para registrar despesas.")
        return

    # Mapeia obras para o SelectBox: 'Nome_Obra (ID)'
    opcoes_obras = {f"{row['Nome_Obra']} ({row['Obra_ID']})": row['Obra_ID']
                    for index, row in df_info.iterrows()}

    obra_selecionada_str = st.selectbox("Selecione a Obra:", list(opcoes_obras.keys()))

    if obra_selecionada_str:
        obra_id = opcoes_obras[obra_selecionada_str]

        # Filtra despesas da obra selecionada
        despesas_obra = df_despesas[df_despesas['Obra_ID'] == obra_id]

        # Calcula a próxima semana de referência
        if despesas_obra.empty:
            proxima_semana = 1
        else:
            proxima_semana = despesas_obra['Semana_Ref'].astype(int).max() + 1

        st.info(f"Próxima semana de referência a ser registrada: **Semana {proxima_semana}**")

        with st.form("form_despesa"):
            gasto = st.number_input("Gasto Total na Semana (R$)", min_value=0.0, format="%.2f")

            # Data da semana (opcionalmente pode ser a data final da semana)
            data_semana = st.date_input("Data de Referência da Semana (Ex: Domingo)")

            submitted = st.form_submit_button("Registrar Gasto")

            if submitted:
                if gasto > 0:
                    data_list = [obra_id, proxima_semana, data_semana.strftime('%Y-%m-%d'), gasto]
                    insert_new_despesa(gc, data_list)
                else:
                    st.warning("O valor do gasto deve ser maior que R$ 0,00.")


def show_consulta_dados(df_info, df_despesas):
    st.header("3. Status Financeiro das Obras")

    if df_info.empty:
        st.info("Nenhuma obra cadastrada para consultar.")
        return

    # 1. Agrega o gasto total por obra
    gastos_totais = df_despesas.groupby('Obra_ID')['Gasto_Semana'].sum().reset_index()
    gastos_totais.rename(columns={'Gasto_Semana': 'Gasto_Total_Acumulado'}, inplace=True)

    # 2. Junta as informações de obras com os gastos
    df_final = df_info.merge(gastos_totais, on='Obra_ID', how='left').fillna(0)

    # 3. Cálculo da Sobra
    df_final['Gasto_Total_Acumulado'] = df_final['Gasto_Total_Acumulado'].round(2)
    df_final['Sobrando_Financeiro'] = df_final['Valor_Total_Inicial'] - df_final['Gasto_Total_Acumulado']

    # 4. Formatação para exibição
    def formatar_moeda(x):
        return f"R$ {x:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")

    df_display = df_final[[
        'Obra_ID',
        'Nome_Obra',
        'Valor_Total_Inicial',
        'Gasto_Total_Acumulado',
        'Sobrando_Financeiro',
        'Data_Inicio'
    ]].copy()

    df_display['Valor_Total_Inicial'] = df_display['Valor_Total_Inicial'].apply(formatar_moeda)
    df_display['Gasto_Total_Acumulado'] = df_display['Gasto_Total_Acumulado'].apply(formatar_moeda)
    df_display['Sobrando_Financeiro'] = df_display['Sobrando_Financeiro'].apply(formatar_moeda)

    st.dataframe(df_display, use_container_width=True)


# --- Aplicação Principal ---

def main():
    st.set_page_config(page_title="Controle Financeiro de Obras", layout="wide")
    st.title("🚧 Sistema de Gerenciamento de Obras")
    st.markdown("---")

    # 1. Obter o cliente Gspread (cacheado)
    gc = get_gspread_client()

    if not gc:
        st.stop() # Parar se a autenticação falhar

    # 2. Recarrega os dados a cada execução/interação
    # CORREÇÃO CRÍTICA: CHAMAR load_data SEM PARÂMETROS!
    df_info, df_despesas = load_data() 

    # Layout de colunas para as páginas de ação
    col_cadastro, col_registro = st.columns(2)

    with col_cadastro:
        # gc é necessário aqui para a ESCRITA, então ele é passado para show_cadastro_obra
        show_cadastro_obra(gc) 

    with col_registro:
        # gc é necessário aqui para a ESCRITA, então ele é passado para show_registro_despesa
        show_registro_despesa(gc, df_info, df_despesas) 

    st.markdown("---")
    show_consulta_dados(df_info, df_despesas)

if __name__ == "__main__":
    main()

