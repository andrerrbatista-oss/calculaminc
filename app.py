import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E SUPORTE ---
st.set_page_config(page_title="Simulador Salarial IPHAN", layout="wide", page_icon="🏛️")

def formatar_br(valor):
    """Formata valores para R$ 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. CÁLCULOS TRIBUTÁRIOS (IRPF & REDUÇÃO LEI 15.270) ---
def calcular_irpf(base_mensal, cenario_nome):
    # Tabela Progressiva Padrão
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
    reducao = 0.0
    # Redução de base só se aplica a partir de 2026 (Vigente e PL)
    if "2026" in cenario_nome or "PL" in cenario_nome:
        if base_mensal <= 5000.00: reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))
    
    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DOS DADOS ---
@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    # Ordem definida aqui para o carregamento
    sufixos = {"-2025": "Vigente 2025", "-2026": "Vigente 2026", "-PL": "Proposta PL"}
    dfs = []
    for nome_n, prefixo in niveis.items():
        for suf, cenario in sufixos.items():
            path = f"tabela_{prefixo}{suf}.csv"
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
                df['nivel_ref'] = nome_n
                df['cenario_ref'] = cenario
                for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                    if col in df.columns: df[col] = df[col].apply(limpar_valor)
                dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else None

df_total = carregar_dados()

# --- 4. BARRA LATERAL (PARÂMETROS) ---
st.sidebar.header("⚙️ Configurações")
vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

if df_total is not None:
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    
    # ORDEM PRIORITÁRIA DEFINIDA AQUI: 2025 -> 2026 -> PL
    cenarios_ordem = ["Vigente 2025", "Vigente 2026", "Proposta PL"]
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento", cenarios_ordem)
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    func = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01, format="%.2f")
    saude = st.sidebar.number_input("Ressarcimento Saúde (R$)", min_value=0.0, step=0.01, format="%.2f")

    pre = 0.0
    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
        if st.sidebar.checkbox("Auxílio Pré-Escolar (+321,00)"): pre = 321.0
    else:
        pontos = 50

    # --- 5. CÁLCULO DOS TRÊS MOMENTOS ---
    def calcular(nome_cenario):
        try:
            linha = df_nivel[(df_nivel['cenario_ref'] == nome_cenario) & 
                             (df_nivel['classe'] == classe_sel) & 
                             (df_nivel['padrao'] == padrao_sel)].iloc[0]
            vb = linha['vb']
            gdac = linha['gdac_80'] if pontos == 80 else (linha['gdac_100'] if pontos == 100 else linha['gdac_50'])
            alim = 1175.0 if vinculo == "Ativo" else 0.0
            
            base_irpf = vb + gdac + func
            ir, aliq, red = calcular_irpf(base_irpf, nome_cenario)
            bruto = vb + gdac + alim + func + pre + saude
            
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func, "PRE": pre, 
                    "SAUDE": saude, "BRUTO": bruto, "IR": ir, "LIQ": bruto - ir, "RED": red, "ALIQ": aliq}
        except: return None

    res_25 = calcular("Vigente 2025")
    res_26 = calcular("Vigente 2026")
    res_pl = calcular("Proposta PL")

    # --- 6. INTERFACE COM ABAS ---
    st.title("🏛️ Simulador Salarial MINC/IPHAN")

    tab1, tab2 = st.tabs(["🎯 Calculadora Individual", "⚖️ Comparativo Cronológico"])

    with tab1:
        # Busca o resultado baseado na escolha da sidebar
        res = {"Vigente 2025": res_25, "Vigente 2026": res_26, "Proposta PL": res_pl}[cenario_foco]
        
        if res:
            st.subheader(f"Visão Detalhada: {cenario_foco}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Bruto", f"R$ {formatar_br(res['BRUTO'])}")
            m2.metric("IRPF (Estimado)", f"R$ {formatar_br(res['IR'])}", 
                      delta=f"- R$ {formatar_br(res['RED'])}" if res['RED'] > 0 else None, delta_color="inverse")
            m3.metric("Líquido", f"R$ {formatar_br(res['LIQ'])}")
            
            st.markdown("---")
            c_a, c_b = st.columns(2)
            with c_a:
                st.write("**Composição da Remuneração:**")
                st.write(f"Vencimento Básico: R$ {formatar_br(res['VB'])}")
                st.write(f"GDAC ({pontos} pts): R$ {formatar_br(res['GDAC'])}")
                if res['ALIM'] > 0: st.write(f"Auxílio Alimentação: R$ {formatar_br(res['ALIM'])}")
            with c_b:
                st.write("**Tributação:**")
                st.write(f"Alíquota Efetiva: {res['ALIQ']}%")
                if res['RED'] > 0: st.info(f"Redução Lei 15.270 aplicada: R$ {formatar_br(res['RED'])}")
        else:
            st.error("Dados não encontrados para o cenário selecionado.")

    with tab2:
        st.subheader("Evolução: 2025 → 2026 → PL")
        if res_25 and res_26 and res_pl:
            # Tabela organizada por colunas temporais
            tabela = [
                ["Vencimento Básico", formatar_br(res_25['VB']), formatar_br(res_26['VB']), formatar_br(res_pl['VB'])],
                ["GDAC", formatar_br(res_25['GDAC']), formatar_br(res_26['GDAC']), formatar_br(res_pl['GDAC'])],
                ["Função/Saúde/Auxílios", 
                 formatar_br(res_25['ALIM']+res_25['PRE']+res_25['FUNC']+res_25['SAUDE']), 
                 formatar_br(res_26['ALIM']+res_26['PRE']+res_26['FUNC']+res_26['SAUDE']), 
                 formatar_br(res_pl['ALIM']+res_pl['PRE']+res_pl['FUNC']+res_pl['SAUDE'])],
                ["---", "---", "---", "---"],
                ["TOTAL BRUTO", formatar_br(res_25['BRUTO']), formatar_br(res_26['BRUTO']), formatar_br(res_pl['BRUTO'])],
                ["LÍQUIDO FINAL", f"**{formatar_br(res_25['LIQ'])}**", f"**{formatar_br(res_26['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
            ]
            st.table(pd.DataFrame(tabela, columns=["Item", "Atual (2025)", "Garantido (2026)", "Proposta PL"]))
            
            # Cálculo de ganhos
            ganho_26 = res_26['LIQ'] - res_25['LIQ']
            ganho_pl = res_pl['LIQ'] - res_26['LIQ']
            
            c1, c2 = st.columns(2)
            c1.info(f"Ganho 2025 ➔ 2026: R$ {formatar_br(ganho_26)}")
            c2.success(f"Impacto Adicional PL: R$ {formatar_br(ganho_pl)}")
