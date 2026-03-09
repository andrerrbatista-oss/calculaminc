import streamlit as st
import pandas as pd
import os

# 1. Configuração da Página e Ícones
st.set_page_config(page_title="Calculadora Salarial MINC/IPHAN", page_icon="🔍", layout="wide")

# --- FUNÇÕES DE SUPORTE ---

def limpar_valor(valor):
    """Trata strings monetárias e converte para float."""
    if isinstance(valor, str):
        # Remove R$, pontos de milhar e troca vírgula por ponto
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try:
            return float(v)
        except ValueError:
            return 0.0
    return float(valor) if valor is not None else 0.0

def formatar_br(valor):
    """Formata para o padrão brasileiro: 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- CÁLCULO DE IRPF (LEI 15.270/2025) ---

def aplicar_reducao_art3a(rendimento, imposto_bruto):
    if rendimento <= 5000.00:
        return min(312.89, imposto_bruto)
    elif 5000.00 < rendimento <= 7350.00:
        reducao = 978.62 - (0.133145 * rendimento)
        return max(0.0, min(reducao, imposto_bruto))
    return 0.0

def calcular_irpf_bruto(base_mensal):
    if base_mensal <= 2259.20: return 0.0, 0.0, 0.0
    elif base_mensal <= 2828.65: return (base_mensal * 0.075) - 169.44, 7.5, 169.44
    elif base_mensal <= 3751.05: return (base_mensal * 0.15) - 381.44, 15.0, 381.44
    elif base_mensal <= 4664.68: return (base_mensal * 0.225) - 662.77, 22.5, 662.77
    else: return (base_mensal * 0.275) - 896.00, 27.5, 896.00

# --- CARREGAMENTO ROBUSTO DOS DADOS ---

@st.cache_data
def carregar_dados_pl():
    # Nomes dos arquivos conforme seu repositório
    arquivos = {
        "SUPERIOR": "tabela_superior(1).csv",
        "INTERMEDIÁRIO": "tabela_intermediario(1).csv",
        "AUXILIAR": "tabela_auxiliar(1).csv"
    }
    
    colunas_padrao = ['classe', 'padrao', 'vb', 'gdac_unit', 'gdac_80', 'gdac_100', 'alim', 'ativo_80', 'ativo_100', 'gdac_50', 'apo_50']
    dfs_finais = []
    
    for nivel, path in arquivos.items():
        if os.path.exists(path):
            try:
                # O segredo: sep=None e engine='python' detecta se é , ou ; sozinho
                df_raw = pd.read_csv(path, sep=None, engine='python', encoding='utf-8-sig', skiprows=1)
                
                # Parte Esquerda (2025) - Colunas 0 a 10
                df_25 = df_raw.iloc[:, 0:11].copy()
                df_25.columns = colunas_padrao
                df_25['vigencia'] = "2025"
                df_25['nivel_data'] = nivel
                
                # Parte Direita (2026) - Colunas 12 a 22 (pulando a coluna vazia do meio)
                df_26 = df_raw.iloc[:, 12:23].copy()
                df_26.columns = colunas_padrao
                df_26['vigencia'] = "2026"
                df_26['nivel_data'] = nivel
                
                for df in [df_25, df_26]:
                    # Limpa as colunas financeiras
                    for col in ['vb', 'gdac_80', 'gdac_100', 'alim']:
                        df[col] = df[col].apply(limpar_valor)
                    dfs_finais.append(df)
            except Exception as e:
                st.error(f"Erro ao ler {path}: {e}")
                
    return pd.concat(dfs_finais, ignore_index=True) if dfs_finais else None

df_pl = carregar_dados_pl()

# --- INTERFACE ---

st.title("🔍 Calculadora Salarial MINC/IPHAN")
st.subheader("Simulador de valores com base PL nº 5.874/2025")

if df_pl is None:
    st.error("Erro crítico: Os arquivos CSV não foram encontrados ou estão com formato inválido.")
    st.stop()

# Sidebar para seleção
st.sidebar.header("Configuração")
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])
ano_base = st.sidebar.radio("Ano de Referência", ["2025", "2026"])

# Filtragem dinâmica
df_filtrado = df_pl[df_pl['nivel_data'] == nivel_sel]
classe_sel = st.sidebar.selectbox("Classe", sorted(df_filtrado['classe'].unique(), reverse=True))
padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_filtrado[df_filtrado['classe'] == classe_sel]['padrao'].unique()))
pontos_gdac = st.sidebar.select_slider("Pontos GDAC", options=[80, 100], value=100) # Padrão 100 para conferência

valor_funcao = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=100.0)
tem_pre = st.sidebar.checkbox("Auxílio Pré-Escolar (+ R$ 321,00)")

# --- CÁLCULO FINAL ---

try:
    # Localiza a linha específica
    dados = df_filtrado[(df_filtrado['classe'] == classe_sel) & 
                        (df_filtrado['padrao'] == padrao_sel) & 
                        (df_filtrado['vigencia'] == ano_base)].iloc[0]
    
    vb = dados['vb']
    gdac = dados['gdac_80'] if pontos_gdac == 80 else dados['gdac_100']
    alim = dados['alim']
    pre = 321.0 if tem_pre else 0.0
    
    # Soma do Bruto
    bruto = vb + gdac + alim + valor_funcao + pre
    
    # Cálculos de Imposto
    imp_bruto, aliq, _ = calcular_irpf_bruto(bruto)
    reducao = aplicar_reducao_art3a(bruto, imp_bruto) if ano_base == "2026" else 0.0
    ir_final = max(0.0, imp_bruto - reducao)
    liquido = bruto - ir_final

    # Exibição dos resultados
    m1, m2, m3 = st.columns(3)
    m1.metric("Valor Mensal Bruto", f"R$ {formatar_br(bruto)}")
    m2.metric("IRPF Mensal Final", f"R$ {formatar_br(ir_final)}", 
              delta=f"-R$ {formatar_br(reducao)}" if reducao > 0 else None, delta_color="inverse")
    m3.metric("Valor Mensal Líquido", f"R$ {formatar_br(liquido)}")

    st.markdown("---")
    col_inf, col_ir = st.columns(2)
    
    with col_inf:
        st.info("**Detalhamento da Remuneração**")
        st.write(f"Vencimento Básico: R$ {formatar_br(vb)}")
        st.write(f"GDAC ({pontos_gdac} pts): R$ {formatar_br(gdac)}")
        st.write(f"Auxílio Alimentação: R$ {formatar_br(alim)}")
        if valor_funcao > 0: st.write(f"Função Comissionada: R$ {formatar_br(valor_funcao)}")
        if tem_pre: st.write(f"Auxílio Pré-Escolar: R$ 321,00")
        st.markdown(f"**Total Bruto Calculado: R$ {formatar_br(bruto)}**")

    with col_ir:
        st.warning("**Detalhamento do Desconto (IRPF)**")
        st.write(f"Alíquota: {aliq}%")
        if ano_base == "2026":
            st.success(f"Dedução Lei 15.270: R$ {formatar_br(reducao)}")
        st.markdown(f"**Imposto Retido na Fonte: R$ {formatar_br(ir_final)}**")

except IndexError:
    st.warning("Dados não encontrados para esta combinação. Verifique os arquivos CSV.")

# Rodapé
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666; font-size: 0.85em;'>Elaboração: GT de Elaboração de Emendas e Comando de Acompanhamento da Negociação</div>", unsafe_allow_html=True)
