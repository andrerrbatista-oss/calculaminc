import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E IDENTIDADE ---
st.set_page_config(page_title="Simulador Salarial MINC/IPHAN", layout="wide", page_icon="🏛️")

# Título fixo no topo
st.title("🏛️ Simulador Salarial MINC/IPHAN")

def formatar_br(valor):
    """Formata valores para o padrão brasileiro"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. MOTOR DE CÁLCULO ---

def calcular_pss(base_contribuicao, vinculo):
    """Cálculo progressivo conforme Portaria 6/2025"""
    teto_rgps = 8157.41
    if vinculo != "Ativo":
        if base_contribuicao <= teto_rgps: return 0.0
        base_calculo = base_contribuicao - teto_rgps
    else:
        base_calculo = base_contribuicao

    faixas = [
        (1518.00, 0.075), (2793.88, 0.09), (4190.83, 0.12), (8157.41, 0.14),
        (13969.49, 0.145), (27938.95, 0.165), (54480.97, 0.19), (float('inf'), 0.22)
    ]
    
    total_pss = 0.0
    limite_anterior = 0.0
    for limite, aliquota in faixas:
        if base_calculo > limite_anterior:
            base_na_faixa = min(base_calculo, limite) - limite_anterior
            total_pss += base_na_faixa * aliquota
            limite_anterior = limite
        else: break
    return total_pss

def calcular_irpf(base_mensal, cenario_nome):
    """Tabela IRPF com isenção da Lei 15.270/2025"""
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
    reducao = 0.0
    if "2026" in cenario_nome or "PL" in cenario_nome:
        if base_mensal <= 5000.00: reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))
    
    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    sufixos = {"-2025": "Tabela Vigente 01/01/2025", "-2026": "Tabela Vigente 01/04/2026", "-PL": "Proposta PL 01/04/2026"}
    dfs = []
    for nome_n, prefixo in niveis.items():
        for suf, cenario in sufixos.items():
            path = f"tabela_{prefixo}{suf}.csv"
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
                df['nivel_ref'], df['cenario_ref'] = nome_n, cenario
                for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                    if col in df.columns: df[col] = df[col].apply(limpar_valor)
                dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else None

df_total = carregar_dados()

if df_total is not None:
    # --- 4. BARRA LATERAL ---
    st.sidebar.header("⚙️ Parâmetros")
    vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
    nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])
    
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    cenarios_ordem = ["Tabela Vigente 01/01/2025", "Tabela Vigente 01/04/2026", "Proposta PL 01/04/2026"]
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento (Aba 1)", cenarios_ordem)
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    func_input = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01, format="%.2f")
    saude_input = st.sidebar.number_input("Ressarcimento Saúde (R$)", min_value=0.0, step=0.01, format="%.2f")

    num_filhos, pre_input = 0, 0.0
    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
        num_filhos = st.sidebar.number_input("Número de dependentes (Auxílio Pré-escolar)", min_value=0, max_value=5, value=0)
        pre_input = num_filhos * 484.90
    else: pontos = 50

    # --- 5. CÁLCULO ---
    def calcular(nome_cenario):
        try:
            linha = df_nivel[(df_nivel['cenario_ref'] == nome_cenario) & (df_nivel['classe'] == classe_sel) & (df_nivel['padrao'] == padrao_sel)].iloc[0]
            vb, gdac = linha['vb'], (linha['gdac_80'] if pontos == 80 else (linha['gdac_100'] if pontos == 100 else linha['gdac_50']))
            alim = 1175.0 if vinculo == "Ativo" else 0.0
            
            base_pss = vb + gdac + func_input
            base_irpf = vb + gdac + func_input + saude_input # Alimentação e Pré-escolar são isentos de IRPF
            
            pss_v = calcular_pss(base_pss, vinculo)
            ir_v, aliq_v, red_v = calcular_irpf(base_irpf, nome_cenario)
            
            bruto_v = vb + gdac + alim + func_input + pre_input + saude_input
            liq_v = bruto_v - ir_v - pss_v
            
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func_input, "PRE": pre_input, 
                    "SAUDE": saude_input, "BRUTO": bruto_v, "IR": ir_v, "PSS": pss_v, "LIQ": li_v, 
                    "RED": red_v, "ALIQ": aliq_v, "BASE_IR": base_irpf}
        except: return None

    res_25, res_26, res_pl = calcular(cenarios_ordem[0]), calcular(cenarios_ordem[1]), calcular(cenarios_ordem[2])

    # --- 6. ABAS ---
    tab1, tab2, tab3 = st.tabs(["🎯 Calculadora Individual", "⚖️ Comparativo Cronológico", "📜 Legislação Aplicada"])

    with tab1:
        res = {"Tabela Vigente 01/01/2025": res_25, "Tabela Vigente 01/04/2026": res_26, "Proposta PL 01/04/2026": res_pl}[cenario_foco]
        if res:
            st.subheader(f"Detalhamento: {cenario_foco}")
            # MÉTRICAS DE RESUMO (Restauradas)
            m1, m2, m3 = st.columns(3)
            m1.metric("Bruto Total", f"R$ {formatar_br(res['BRUTO'])}")
            m2.metric("Total Deduções", f"R$ {formatar_br(res['IR'] + res['PSS'])}")
            m3.metric("Líquido Final", f"R$ {formatar_br(res['LIQ'])}")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Composição da Remuneração:**")
                st.write(f"Vencimento Básico: **R$ {formatar_br(res['VB'])}**")
                st.write(f"GDAC ({pontos} pts): **R$ {formatar_br(res['GDAC'])}**")
                if res['ALIM'] > 0: st.write(f"Auxílio Alimentação: **R$ {formatar_br(res['ALIM'])}**")
                if res['FUNC'] > 0: st.write(f"Função Comissionada: **R$ {formatar_br(res['FUNC'])}**")
                if res['PRE'] > 0: st.success(f"Auxílio Pré-Escolar ({num_filhos} dep.): **R$ {formatar_br(res['PRE'])}**")
                if res['SAUDE'] > 0: st.write(f"Ressarcimento Saúde: **R$ {formatar_br(res['SAUDE'])}**")
            with col_b:
                st.write("**Deduções (Impostos e Previdência):**")
                st.write(f"Contribuição PSS: **R$ {formatar_br(res['PSS'])}**")
                st.caption("Valor aproximado tendo em vista o valor ser progressivo, podendo ser um pouco maior que o valor atual de seu desconto em folha.")
                st.write(f"Imposto de Renda (IRPF): **R$ {formatar_br(res['IR'])}**")
                st.caption(f"Alíquota efetiva: {res['ALIQ']}% (Base tributável: R$ {formatar_br(res['BASE_IR'])})")
                if res['RED'] > 0: st.info(f"Redução Lei 15.270 aplicada: **R$ {formatar_br(res['RED'])}**")

    with tab2:
        st.subheader("Evolução: 01/01/2025 ➔ 01/04/2026 ➔ Proposta PL")
        if res_25 and res_26 and res_pl:
            def s_ex(r): return r['ALIM'] + r['PRE'] + r['SAUDE'] + r['FUNC']
            tabela = [
                ["Vencimento Básico", formatar_br(res_25['VB']), formatar_br(res_26['VB']), formatar_br(res_pl['VB'])],
                ["GDAC", formatar_br(res_25['GDAC']), formatar_br(res_26['GDAC']), formatar_br(res_pl['GDAC'])],
                ["Auxílios/Saúde/Função", formatar_br(s_ex(res_25)), formatar_br(s_ex(res_26)), formatar_br(s_ex(res_pl))],
                ["---", "---", "---", "---"],
                ["TOTAL BRUTO", formatar_br(res_25['BRUTO']), formatar_br(res_26['BRUTO']), formatar_br(res_pl['BRUTO'])],
                ["PSS (Previdência)", f"- {formatar_br(res_25['PSS'])}", f"- {formatar_br(res_26['PSS'])}", f"- {formatar_br(res_pl['PSS'])}"],
                ["IRPF Retido", f"- {formatar_br(res_25['IR'])}", f"- {formatar_br(res_26['IR'])}", f"- {formatar_br(res_pl['IR'])}"],
                ["LÍQUIDO FINAL", f"**{formatar_br(res_25['LIQ'])}**", f"**{formatar_br(res_26['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
            ]
            st.table(pd.DataFrame(tabela, columns=["Item", "01/01/2025", "01/04/2026", "PL 01/04/2026"]))

    with tab3:
        st.subheader("Base Normativa")
        legislação = [
            ["Decreto nº 977/1993", "Assistência pré-escolar federal.", "https://www.planalto.gov.br/ccivil_03/decreto/antigos/d0977.htm"],
            ["Lei nº 11.233/2005", "PEC da Cultura.", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2005/lei/L11233.htm"],
            ["Decreto nº 11.178/2022", "Estrutura IPHAN.", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11178.htm"],
            ["Decreto nº 11.336/2023", "Estrutura MinC.", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11336.htm"],
            ["Portaria MPS/MF nº 6/2025", "Alíquotas PSS.", "https://www.in.gov.br/en/web/dou/-/portaria-interministerial-mps/mf-n-6-de-10-de-janeiro-de-2025-606526848"],
            ["Lei nº 15.270/2025", "Isenção IRPF até R$ 5k.", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15270.htm"],
            ["PL nº 5.874/2025", "Reestruturação remuneratória.", "https://www25.senado.leg.br/web/atividade/materias/-/materia/172946"]
        ]
        for item in legislação: st.markdown(f"**[{item[0]}]({item[2]})** — {item[1]}")

    # --- 7. RODAPÉ ---
    st.markdown("---")
    st.markdown("<div style='text-align: center; color: gray; font-size: 0.8em;'>Elaborado por GT de Elaboração das Emendas e Comando Nacional de Acompanhamento</div>", unsafe_allow_html=True)
