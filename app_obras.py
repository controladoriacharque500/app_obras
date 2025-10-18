import streamlit as st
import pandas as pd
from gspread import service_account_from_dict
from datetime import datetime, timedelta
import json

# --- Configurações da Nova Planilha ---
PLANILHA_NOME = "Controle_Obras" # O nome da sua nova planilha
ABA_INFO = "Obras_Info"
ABA_DESPESAS = "Despesas_Semanas"

# --- Funções de Autenticação e Conexão ---

@st.cache_resource(ttl=None) # Cache eterno para o objeto de conexão
def get_gspread_client():
    """Conecta e retorna o cliente GSpread usando st.secrets."""
    try:
        if "gcp_service_account" not in st.secrets:
             raise ValueError("Nenhuma seção [gcp_service_account] encontrada no st.secrets.")

        secrets_dict = dict(st.secrets["gcp_service_account"])
        private_key_corrompida = secrets_dict["private_key"]

        # Lógica de limpeza da chave (necessária para chaves quebradas)
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

# --- Funções de Leitura de Dados (Banco de Dados) ---
# Adicionado tratamento para int64/float64 na limpeza
@st.cache_data(ttl=600)
def load_data():
    """Carrega dados de ambas as abas e retorna dois DataFrames."""
    # CHAMA A FUNÇÃO DE CONEXÃO CACHEADA INTERNAMENTE
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
            # Garante que Semana_Ref é int nativo
            df_despesas['Semana_Ref'] = pd.to_numeric(df_despesas['Semana_Ref'], errors='coerce').fillna(0).astype(int)

        return df_info, df_despesas

    except Exception as e:
        st.error(f"Erro ao carregar dados: Verifique se a planilha '{PLANILHA_NOME}' e as abas '{ABA_INFO}' e '{ABA_DESPESAS}' existem e se as colunas estão corretas. Detalhe: {e}")
        return pd.DataFrame(), pd.DataFrame()


# --- Funções de Escrita de Dados (INSERT E UPDATE) ---

def insert_new_obra(gc, data):
    """Insere uma nova obra na aba Obras_Info."""
    try:
        planilha = gc.open(PLANILHA_NOME)
        aba_info = planilha.worksheet(ABA_INFO)
        aba_info.append_row(data)
        st.toast("✅ Nova obra cadastrada com sucesso!")
        load_data.clear() # Limpa o cache para forçar recarga dos dados
    except Exception as e:
        st.error(f"Erro ao inserir nova obra: {e}")

def insert_new_despesa(gc, data):
    """Insere uma nova despesa semanal na aba Despesas_Semanas."""
    try:
        planilha = gc.open(PLANILHA_NOME)
        aba_despesas = planilha.worksheet(ABA_DESPESAS)
        
        # CORREÇÃO: Converter todos os elementos para tipos nativos antes de enviar
        data_nativa = [str(data[0]), int(data[1]), data[2], float(data[3])]

        aba_despesas.append_row(data_nativa)
        st.toast("✅ Despesa semanal registrada com sucesso!")
        load_data.clear() # Limpa o cache para forçar recarga dos dados
    except Exception as e:
        st.error(f"Erro ao registrar despesa: {e}. Verifique se todos os valores numéricos são floats ou ints nativos.")


def update_despesa(gc, obra_id, semana_ref, novo_gasto, nova_data):
    """Atualiza o gasto e a data de uma semana de referência específica."""
    try:
        planilha = gc.open(PLANILHA_NOME)
        aba_despesas = planilha.worksheet(ABA_DESPESAS)
        
        # 1. Obter todos os registros (incluindo o cabeçalho)
        data = aba_despesas.get_all_values()
        
        sheets_row_index = -1
        
        # Iterar a partir da segunda linha (dados)
        for i, row in enumerate(data[1:]):
            # Assumindo que Obra_ID está na coluna 0 e Semana_Ref na coluna 1
            if str(row[0]) == str(obra_id) and str(row[1]) == str(semana_ref):
                # O índice da linha no Sheets é i + 2 (cabeçalho + índice 0 do Python)
                sheets_row_index = i + 2 
                break
        
        if sheets_row_index == -1:
            st.warning("Linha de despesa não encontrada para atualização.")
            return

        # 3. Criar os novos dados da linha (na ordem das colunas do Sheets)
        # CORREÇÃO: Converte valores numéricos para tipos nativos
        new_row_data = [
            str(obra_id),
            int(semana_ref), # Garante que é int nativo
            nova_data.strftime('%Y-%m-%d'),
            float(novo_gasto) # Garante que é float nativo
        ]
        
        # 4. Atualizar a linha (da primeira coluna 'A' até a última coluna 'D')
        range_to_update = f'A{sheets_row_index}:D{sheets_row_index}'
        aba_despesas.update(range_to_update, [new_row_data], value_input_option='USER_ENTERED')
        
        st.toast(f"✅ Semana {semana_ref} da Obra {obra_id} atualizada com sucesso!")
        load_data.clear() # Limpa o cache para recarregar os dados
        
    except Exception as e:
        st.error(f"Erro ao atualizar despesa: {e}. Verifique se os valores numéricos são válidos.")

# --- O RESTANTE DO CÓDIGO PERMANECE O MESMO ---
# (show_cadastro_obra, show_registro_despesa, show_consulta_dados e main)


# --- Interface do Usuário (Streamlit) ---

def show_cadastro_obra(gc):
    st.header("1. Cadastrar Nova Obra")
    df_info, _ = load_data()

    # Gera o próximo ID de forma mais segura
    next_id = 1
    if not df_info.empty and 'Obra_ID' in df_info.columns:
        try:
            # Tenta pegar o máximo ID, se a coluna for limpa e numérica
            max_id = df_info['Obra_ID'].astype(str).str.replace(r'[^0-9]', '', regex=True).astype(int).max()
            next_id = max_id + 1
        except Exception as e:
            # Se a limpeza falhar, apenas usa a contagem de linhas
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

    # CRIA O SELECTBOX
    obra_selecionada_str = st.selectbox("Selecione a Obra:", list(opcoes_obras.keys()), key="select_obra_registro")

    if obra_selecionada_str:
        obra_id = opcoes_obras[obra_selecionada_str]
        
        # --- FILTRAGEM DE DADOS PARA A OBRA SELECIONADA ---
        # Garantir que o Obra_ID é string para o filtro
        despesas_obra = df_despesas[df_despesas['Obra_ID'].astype(str) == str(obra_id)].copy()
        
        # ----------------------------------------------------
        # --- LAYOUT PRINCIPAL: Coluna 1 (Novo Registro) e Coluna 2 (Edição)
        # ----------------------------------------------------
        col1_reg, col2_edit = st.columns([1, 1.2]) 

        with col1_reg:
            st.subheader(f"Novo Gasto (Obra: {obra_id})")
            
            if despesas_obra.empty:
                proxima_semana = 1
            else:
                # O load_data já garante que Semana_Ref é numérica
                proxima_semana = despesas_obra['Semana_Ref'].max() + 1
                
            st.info(f"Próxima semana de referência a ser registrada: **Semana {proxima_semana}**")

            with st.form("form_despesa"):
                gasto = st.number_input("Gasto Total na Semana (R$)", min_value=0.0, format="%.2f", key="new_gasto")
                data_semana = st.date_input("Data de Referência da Semana", key="new_data")
                
                submitted = st.form_submit_button("Registrar Novo Gasto")
                
                if submitted:
                    if gasto > 0:
                        data_list = [obra_id, proxima_semana, data_semana.strftime('%Y-%m-%d'), gasto]
                        insert_new_despesa(gc, data_list)
                    else:
                        st.warning("O valor do gasto deve ser maior que R$ 0,00.")


        with col2_edit:
            st.subheader(f"Detalhes e Edição ({len(despesas_obra)} Semanas)")
            
            if despesas_obra.empty:
                st.info("Nenhum gasto registrado para esta obra.")
                # Não é um return, pois a coluna 1 já executou.
            else:
                # Formata o DataFrame para exibição
                despesas_display = despesas_obra.sort_values('Semana_Ref', ascending=False).copy()
                despesas_display['Gasto_Semana'] = despesas_display['Gasto_Semana'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "#").replace(".", ",").replace("#", "."))
                despesas_display = despesas_display.rename(columns={'Semana_Ref': 'Semana', 'Data_Semana': 'Data Ref.', 'Gasto_Semana': 'Gasto'})

                # ----------------------------------------------------
                # Menu de Seleção para Edição
                # ----------------------------------------------------
                
                semanas_opcoes = despesas_obra['Semana_Ref'].sort_values(ascending=False).tolist()
                semana_selecionada = st.selectbox(
                    "Selecione a Semana para Detalhar/Editar:", 
                    semanas_opcoes, 
                    format_func=lambda x: f"Semana {x}",
                    key="select_semana_edicao"
                )
                
                # --- DETALHAMENTO E FORMULÁRIO DE EDIÇÃO ---
                if semana_selecionada:
                    # Pega a linha da semana selecionada
                    linha_edicao = despesas_obra[despesas_obra['Semana_Ref'] == semana_selecionada].iloc[0]
                    
                    # Converte os valores atuais para os tipos de input do Streamlit
                    data_atual = datetime.strptime(linha_edicao['Data_Semana'], '%Y-%m-%d').date()
                    gasto_atual = float(linha_edicao['Gasto_Semana'])

                    with st.expander(f"Editar Detalhes da Semana {semana_selecionada}", expanded=True):
                        with st.form(f"form_edicao_semana_{semana_selecionada}"):
                            
                            st.markdown(f"**Editando: Obra {obra_id} - Semana {semana_selecionada}**")
                            
                            novo_gasto = st.number_input(
                                "Novo Gasto Total (R$)", 
                                min_value=0.0, 
                                value=gasto_atual, 
                                format="%.2f", 
                                key="edit_gasto"
                            )
                            nova_data = st.date_input(
                                "Nova Data de Referência", 
                                value=data_atual, 
                                key="edit_data"
                            )
                            
                            submitted_edit = st.form_submit_button("Salvar Alterações")
                            
                            if submitted_edit:
                                if novo_gasto >= 0:
                                    # Chama a nova função de atualização
                                    update_despesa(gc, obra_id, semana_selecionada, novo_gasto, nova_data)
                                else:
                                    st.warning("O valor do gasto não pode ser negativo.")
                            
                    # Exibe a tabela de todos os gastos abaixo do formulário de edição
                    st.markdown("---")
                    st.markdown("**Histórico de Gastos:**")
                    st.dataframe(
                        despesas_display[['Semana', 'Data Ref.', 'Gasto', 'Obra_ID']], 
                        use_container_width=True,
                        hide_index=True
                    )


def show_consulta_dados(df_info, df_despesas):
    st.header("3. Status Financeiro das Obras")
    
    if df_info.empty:
        st.info("Nenhuma obra cadastrada para consultar.")
        return

    # 1. Agrega o gasto total por obra de forma segura
    if not df_despesas.empty and 'Obra_ID' in df_despesas.columns and 'Gasto_Semana' in df_despesas.columns:
        # Garante que a coluna Gasto_Semana é numérica (o load_data já tenta fazer isso, mas esta é uma segurança extra)
        df_despesas['Gasto_Semana'] = pd.to_numeric(df_despesas['Gasto_Semana'], errors='coerce').fillna(0)
        
        # Tenta a agregação
        try:
            gastos_totais = df_despesas.groupby('Obra_ID')['Gasto_Semana'].sum().reset_index()
            gastos_totais.rename(columns={'Gasto_Semana': 'Gasto_Total_Acumulado'}, inplace=True)
        except Exception as e:
            # Caso o groupby falhe (ex: tipos mistos), cria um DataFrame vazio de gastos
            st.error(f"Erro na agregação de gastos. Detalhe: {e}")
            gastos_totais = pd.DataFrame({'Obra_ID': df_info['Obra_ID'].unique(), 'Gasto_Total_Acumulado': 0.0})
    else:
        # Cria um DataFrame de gastos zerado se o df_despesas estiver vazio ou sem as colunas chave
        gastos_totais = pd.DataFrame({'Obra_ID': df_info['Obra_ID'].unique(), 'Gasto_Total_Acumulado': 0.0})

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
    
    gc = get_gspread_client()
    
    if not gc:
        st.stop() # Parar se a autenticação falhar
        
    # Recarrega os dados a cada execução/interação (CHAMADO SEM PARÂMETROS)
    df_info, df_despesas = load_data() 
    
    # Layout de colunas para as páginas de ação
    col_cadastro, col_registro = st.columns(2)
    
    with col_cadastro:
        show_cadastro_obra(gc) # gc é passado para a função de ESCRITA
        
    with col_registro:
        show_registro_despesa(gc, df_info, df_despesas)
        
    st.markdown("---")
    show_consulta_dados(df_info, df_despesas)

if __name__ == "__main__":
    main()





