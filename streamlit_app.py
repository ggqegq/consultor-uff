# ==============================================
# CONSULTOR DE QUADRO DE HORÁRIOS UFF
# Versão Streamlit para deploy no Streamlit Cloud
# ==============================================
# 
# INSTRUÇÕES DE DEPLOY:
# 1. Crie uma conta no GitHub (github.com) e Streamlit Cloud (streamlit.io)
# 2. Crie um novo repositório no GitHub
# 3. Faça upload deste arquivo como "streamlit_app.py"
# 4. Crie também o arquivo "requirements.txt" com o conteúdo:
#    streamlit
#    selenium
#    pandas
#    openpyxl
#    beautifulsoup4
#    webdriver-manager
# 5. No Streamlit Cloud, clique em "New app" e conecte seu repositório
# 6. Aguarde o deploy e compartilhe o link gerado!
#
# ==============================================

import streamlit as st
import pandas as pd
import time
import re
import io
from datetime import datetime

# Importações do Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Importações do Excel
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

# ===== CONFIGURAÇÃO DA PÁGINA =====
st.set_page_config(
    page_title="Consultor UFF - Quadro de Horários",
    page_icon="📊",
    layout="wide"
)

# ===== ESTILOS CSS =====
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e3a5f;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        background-color: #d4edda;
        border-radius: 0.5rem;
        border-left: 4px solid #28a745;
    }
    .info-box {
        padding: 1rem;
        background-color: #e7f3ff;
        border-radius: 0.5rem;
        border-left: 4px solid #0066cc;
    }
</style>
""", unsafe_allow_html=True)

# ===== FUNÇÕES AUXILIARES =====
def calcular_periodos_retroativos(periodo_base, qtd=3):
    """Gera lista de períodos a partir de uma base."""
    periodo_base = periodo_base.replace('.', '')
    ano = int(periodo_base[:4])
    semestre = int(periodo_base[4])
    lista_periodos = []
    for _ in range(qtd):
        lista_periodos.append(f"{ano}{semestre}")
        if semestre == 1:
            semestre = 2
            ano -= 1
        else:
            semestre = 1
    return lista_periodos

# ===== CLASSE PRINCIPAL =====
class ConsultorQuadroHorariosUFF:
    def __init__(self, periodos, curso_filtro=None, departamentos_filtro=None):
        self.periodos = periodos
        self.curso_filtro = curso_filtro
        self.departamentos_filtro = departamentos_filtro if departamentos_filtro else []
        self.links_processados = set()
        
        # Configurações do Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-gpu')
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            st.error(f"Erro ao iniciar navegador: {e}")
            raise e
        
        self.ids_cursos = {
            'Química': '28',
            'Química Industrial': '29'
        }

    def construir_url_busca(self, id_curso, departamento=None, periodo='20252'):
        base_url = "https://app.uff.br/graduacao/quadrodehorarios/"
        params = [
            "utf8=%E2%9C%93",
            f"q%5Banosemestre_eq%5D={periodo}",
            "q%5Bdisciplina_cod_departamento_eq%5D=",
            f"q%5Bvagas_turma_curso_idcurso_eq%5D={id_curso}",
        ]
        if departamento and departamento.strip():
            codigo_busca = f"{departamento.strip().upper()}00"
            params.insert(0, f"q%5Bdisciplina_nome_or_disciplina_codigo_cont%5D={codigo_busca}")
        else:
            params.insert(0, "q%5Bdisciplina_nome_or_disciplina_codigo_cont%5D=")
        return base_url + "?" + "&".join(params)

    def extrair_links_turmas_da_pagina(self):
        links = set()
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            for link in soup.find_all('a', href=True):
                if '/turmas/' in link['href']:
                    full_url = f"https://app.uff.br{link['href']}" if not link['href'].startswith('http') else link['href']
                    links.add(full_url.split('?')[0])
        except Exception:
            pass
        return list(links)

    def navegar_todas_paginas(self, url_inicial):
        self.driver.get(url_inicial)
        time.sleep(1.5)
        todos_links = set()
        while True:
            links = self.extrair_links_turmas_da_pagina()
            todos_links.update(links)
            try:
                paginacao = self.driver.find_element(By.CLASS_NAME, 'pagination')
                next_btn = paginacao.find_element(By.CSS_SELECTOR, 'a[rel="next"]')
                if 'disabled' in next_btn.get_attribute('class'):
                    break
                next_btn.click()
                time.sleep(1.5)
            except:
                break
        return list(todos_links)

    def extrair_dados_turma(self, url_turma, periodo, curso_alvo):
        try:
            if url_turma in self.links_processados:
                return None
            self.links_processados.add(url_turma)
            self.driver.get(url_turma)
            time.sleep(0.5)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            titulo = soup.find('h1').get_text(strip=True)
            match = re.search(r'Turma\s+(\S+)\s+de\s+(\S+)\s+-\s+(.+)', titulo)
            if not match:
                return None
            
            turma, codigo, nome = match.group(1), match.group(2), match.group(3)
            depto = codigo[:3]
            
            horario_str = "Não informado"
            try:
                h5_horario = soup.find('h5', string=re.compile('Horários'))
                if h5_horario:
                    trs = h5_horario.find_next('table').find_all('tr')
                    if len(trs) > 1:
                        cols = trs[1].find_all('td')
                        dias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
                        horarios = [f"{dias[i]}: {c.text.strip()}" for i, c in enumerate(cols) if c.text.strip() and i < 6]
                        horario_str = " | ".join(horarios)
            except:
                pass
            
            vagas_info = None
            try:
                h5_vagas = soup.find('h5', string=re.compile('Vagas Alocadas'))
                if h5_vagas:
                    trs = h5_vagas.find_next('table').find_all('tr')[2:]
                    for row in trs:
                        cols = row.find_all('td')
                        curso_nome = cols[0].text.strip()
                        match_curso = False
                        if curso_alvo == 'Química' and ('028' in curso_nome or 'Química' in curso_nome):
                            match_curso = True
                        if curso_alvo == 'Química Industrial' and ('029' in curso_nome or 'Industrial' in curso_nome):
                            match_curso = True
                        if match_curso:
                            vagas_info = {
                                'vagas_reg': int(cols[1].text) if cols[1].text.isdigit() else 0,
                                'vagas_vest': int(cols[2].text) if cols[2].text.isdigit() else 0,
                                'inscritos_reg': int(cols[3].text) if cols[3].text.isdigit() else 0,
                                'inscritos_vest': int(cols[4].text) if cols[4].text.isdigit() else 0,
                            }
                            break
            except:
                pass
            
            if not vagas_info:
                return None
            
            return {
                'periodo': periodo,
                'depto': depto,
                'codigo': codigo,
                'disciplina': nome,
                'turma': turma,
                'horario': horario_str,
                **vagas_info
            }
        except Exception:
            return None

    def executar_consulta(self, progress_bar, status_text):
        dados_brutos = []
        cursos_para_buscar = [self.curso_filtro] if self.curso_filtro else list(self.ids_cursos.keys())
        total_steps = len(self.periodos) * len(cursos_para_buscar)
        step = 0
        
        for periodo in self.periodos:
            for curso in cursos_para_buscar:
                step += 1
                progress = step / total_steps
                progress_bar.progress(progress)
                status_text.text(f"Buscando {curso} em {periodo[:4]}.{periodo[4]}...")
                
                self.links_processados.clear()
                id_curso = self.ids_cursos.get(curso, '28')
                deptos = self.departamentos_filtro if self.departamentos_filtro else [None]
                
                for depto in deptos:
                    url = self.construir_url_busca(id_curso, depto, periodo)
                    links = self.navegar_todas_paginas(url)
                    
                    for link in links:
                        dado = self.extrair_dados_turma(link, periodo, curso)
                        if dado:
                            dados_brutos.append(dado)
        
        self.driver.quit()
        return dados_brutos

    def gerar_excel_comparativo(self, dados):
        if not dados:
            return None
        
        df = pd.DataFrame(dados)
        wb = Workbook()
        ws = wb.active
        ws.title = "Comparativo de Períodos"
        
        blue_fill = PatternFill(start_color="337AB7", end_color="337AB7", fill_type="solid")
        beige_fill = PatternFill(start_color="FDFDF0", end_color="FDFDF0", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        periodos_ordenados = sorted(list(df['periodo'].unique()), reverse=True)
        sub_cols = [
            ('horario', 'Horário'),
            ('vagas_reg', 'Vagas Reg'),
            ('inscritos_reg', 'Insc Reg'),
            ('vagas_vest', 'Vagas Vest'),
            ('inscritos_vest', 'Insc Vest')
        ]
        
        headers_row1 = ["Depto", "Código", "Disciplina", "Turma"]
        for col_idx, text in enumerate(headers_row1, 1):
            cell = ws.cell(row=1, column=col_idx, value=text)
            ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)
            cell.fill = blue_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border
        
        current_col = 5
        for per in periodos_ordenados:
            per_fmt = f"{per[:4]}.{per[4]}"
            cell = ws.cell(row=1, column=current_col, value=per_fmt)
            ws.merge_cells(start_row=1, start_column=current_col, end_row=1, end_column=current_col + len(sub_cols) - 1)
            cell.fill = blue_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border
            
            for _, title in sub_cols:
                sub_cell = ws.cell(row=2, column=current_col, value=title)
                sub_cell.fill = blue_fill
                sub_cell.font = Font(color="FFFFFF", bold=False, size=9)
                sub_cell.alignment = center
                sub_cell.border = border
                current_col += 1
        
        grouped = df.groupby(['depto', 'codigo', 'disciplina', 'turma'])
        row_num = 3
        
        for name, group in grouped:
            for i, val in enumerate(name, 1):
                cell = ws.cell(row=row_num, column=i, value=val)
                cell.border = border
                cell.alignment = center if i != 3 else Alignment(horizontal='left', vertical='center')
            
            col_idx = 5
            for per in periodos_ordenados:
                dados_periodo = group[group['periodo'] == per]
                if not dados_periodo.empty:
                    dado = dados_periodo.iloc[0]
                    vals = [dado[k] for k, _ in sub_cols]
                else:
                    vals = ['-', '-', '-', '-', '-']
                
                for val in vals:
                    cell = ws.cell(row=row_num, column=col_idx, value=val)
                    cell.border = border
                    cell.alignment = center
                    cell.fill = beige_fill
                    col_idx += 1
            row_num += 1
        
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 8
        
        # Salvar em buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer

# ===== INTERFACE PRINCIPAL =====
st.markdown('<p class="main-header">Consultor de Quadro de Horários UFF</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Gere planilhas comparativas de vagas e horários dos cursos de Química</p>', unsafe_allow_html=True)

# Formulário
with st.form("consulta_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        periodo_ref = st.text_input(
            "Período de Referência",
            value="2026.1",
            help="Formato: AAAA.S (ex: 2026.1)"
        )
        
        qtd_periodos = st.slider(
            "Quantidade de Períodos",
            min_value=1,
            max_value=6,
            value=3,
            help="Quantos períodos anteriores incluir na comparação"
        )
    
    with col2:
        curso = st.selectbox(
            "Curso",
            options=["Todos", "Química", "Química Industrial"],
            help="Selecione o curso ou deixe 'Todos'"
        )
        
        deptos = st.text_input(
            "Departamentos (opcional)",
            placeholder="Ex: GQI, MAF",
            help="Separe por vírgula. Deixe vazio para todos."
        )
    
    submitted = st.form_submit_button("Gerar Planilha", use_container_width=True)

# Processamento
if submitted:
    # Validação
    try:
        periodo_clean = periodo_ref.replace('.', '')
        if len(periodo_clean) != 5 or not periodo_clean.isdigit():
            raise ValueError("Formato inválido")
    except:
        st.error("Formato de período inválido. Use AAAA.S (ex: 2026.1)")
        st.stop()
    
    # Configurar parâmetros
    periodos = calcular_periodos_retroativos(periodo_ref, qtd_periodos)
    curso_filtro = curso if curso != "Todos" else None
    deptos_filtro = [d.strip().upper() for d in deptos.split(',')] if deptos.strip() else None
    
    # Mostrar configuração
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.write(f"**Períodos a consultar:** {', '.join([f'{p[:4]}.{p[4]}' for p in periodos])}")
    st.write(f"**Curso:** {curso}")
    st.write(f"**Departamentos:** {deptos if deptos else 'Todos'}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Barra de progresso
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        with st.spinner("Iniciando consulta..."):
            consultor = ConsultorQuadroHorariosUFF(periodos, curso_filtro, deptos_filtro)
            dados = consultor.executar_consulta(progress_bar, status_text)
        
        if dados:
            status_text.text("Gerando planilha Excel...")
            excel_buffer = consultor.gerar_excel_comparativo(dados)
            
            if excel_buffer:
                progress_bar.progress(1.0)
                status_text.text("Concluído!")
                
                st.markdown('<div class="success-box">', unsafe_allow_html=True)
                st.success(f"Planilha gerada com sucesso! {len(dados)} registros encontrados.")
                st.markdown('</div>', unsafe_allow_html=True)
                
                nome_arquivo = f"Comparativo_{periodo_ref.replace('.','')}_e_anteriores.xlsx"
                
                st.download_button(
                    label="Download da Planilha Excel",
                    data=excel_buffer,
                    file_name=nome_arquivo,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        else:
            st.warning("Nenhum dado encontrado para os filtros selecionados.")
            
    except Exception as e:
        st.error(f"Erro durante a consulta: {e}")

# Rodapé
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #888; font-size: 0.9rem;">
    Desenvolvido para consulta ao Quadro de Horários da UFF<br>
    Os dados são extraídos diretamente do sistema oficial da universidade.
</div>
""", unsafe_allow_html=True)
