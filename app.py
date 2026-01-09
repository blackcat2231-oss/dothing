import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import io
import time

# --- 1. 網頁基本設定 ---
st.set_page_config(page_title="篤行幼兒園評量系統", layout="wide", page_icon="🌱")

st.markdown("""
    <style>
    .main {background-color: #f9f9f9;}
    .stHeader {color: #2c3e50;}
    th {
        white-space: normal !important;
        min-width: 120px;
        vertical-align: top !important;
        background-color: #f0f2f6 !important;
    }
    td {text-align: center !important; vertical-align: middle !important;}
    td:last-child {text-align: left !important;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄與 API 設定 ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2231/2231649.png", width=100)
    st.title("🌱 篤行幼兒園")
    st.subheader("評量系統 v1.7 (家長報告版)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 批次上傳與辨識", "📄 匯出家長報告"])

# --- 3. 核心功能函式 ---

def get_gemini_model():
    """尋找最強模型"""
    model_list = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_list.append(m.name)
        priority_keywords = ['gemini-3', 'gemini-2.5', 'pro', 'flash']
        for keyword in priority_keywords:
            for name in model_list:
                if keyword in name and ('1.5' in name if keyword == 'flash' else True):
                    return genai.GenerativeModel(name), name
    except:
        pass
    return genai.GenerativeModel('gemini-1.5-flash'), 'fallback-flash'

def analyze_image(image):
    """AI 辨識核心"""
    model, model_name = get_gemini_model()
    
    prompt = """
    你是一位細心的資料輸入員。請分析這張幼兒園評量表。
    
    【步驟一：讀取表頭指標】
    請讀取表格最上方、位於「幼兒姓名」與「備註」中間的那 4 個欄位標題文字。
    
    【步驟二：讀取幼兒資料】
    請依序讀取每一列幼兒的資料。
    
    **關於「備註」欄位的特別指示：**
    1. 請務必將**同一個格子內的所有文字**合併成一個字串。
    2. **嚴禁**將備註裡的換行誤判為下一位幼兒。
    3. 如果備註有分點，請保留編號（如 1. 或 ①）。

    **關於「分數」的判斷：**
    - 圈選 1 -> "A"
    - 圈選 2 -> "R"
    - 圈選 3 -> "D"
    - 圈選 4 -> "N"

    【輸出格式】
    請回傳 JSON：
    {
      "headers": ["指標1文字", "指標2文字", "指標3文字", "指標4文字"],
      "students": [
        {"name": "幼兒一", "scores": ["A", "R", "A", "R"], "note": "備註內容"},
        ...
      ]
    }
    """
    
    config = genai.types.GenerationConfig(temperature=0.0, response_mime_type="application/json")
    try:
        response = model.generate_content([prompt, image], generation_config=config)
        return json.loads(response.text)
    except:
        return None

def generate_individual_report(df):
    """將資料轉為 Word 檔 (一頁一位幼兒)"""
    doc = Document()
    
    # 設定整份文件的字型 (微軟正黑體)
    style = doc.styles['Normal']
    style.font.name = 'Microsoft JhengHei'
    style.element.rPr.rFonts.set(object.__name__, 'Microsoft JhengHei')
    
    # 取得所有指標欄位名稱 (排除 姓名 和 備註)
    indicator_cols = [c for c in df.columns if c not in ['幼兒姓名', '備註']]

    # 針對每一位幼兒產生一頁報告
    for index, row in df.iterrows():
        # 如果不是第一位，就換頁
        if index > 0:
            doc.add_page_break()
            
        # 1. 標題區
        heading = doc.add_heading('篤行幼兒園 - 幼兒學習評量報告', level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph("") # 空行
        
        # 2. 學生姓名與基本資料
        p = doc.add_paragraph()
        p.add_run(f"幼兒姓名：").bold = True
        p.add_run(f"{row['幼兒姓名']}").bold = True
        p.add_run(f"\t\t\t日期：2026年___月___日") # 預留日期欄位
        
        doc.add_paragraph("") # 空行

        # 3. 評量指標表 (Table)
        # 建立一個表格：左邊是指標內容，右邊是成績
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        
        # 表頭
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "學習指標內容"
        hdr_cells[1].text = "評量結果"
        
        # 設定表頭寬度與樣式
        for cell in hdr_cells:
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            
        # 填入每一個指標
        for col_name in indicator_cols:
            row_cells = table.add_row().cells
            row_cells[0].text = col_name # 左邊放指標文字
            row_cells[1].text = str(row[col_name]) # 右邊放分數 A/R/D/N
            
            # 讓分數置中
            row_cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            
        doc.add_paragraph("") # 空行

        # 4. 老師的話 (備註區)
        doc.add_heading('💡 老師的觀察與建議：', level=2)
        note_content = row['備註'] if row['備註'] else "（本次無特殊備註）"
        doc.add_paragraph(note_content)
        
        doc.add_paragraph("") # 空行
        doc.add_paragraph("") # 空行

        # 5. 頁尾說明
        footer = doc.add_paragraph()
        footer.add_run("--------------------------------------------------").bold = True
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        legend = doc.add_paragraph()
        legend.add_run("評量代號說明：\n").bold = True
        legend.add_run("A (Excellent) - 表現優異，能熟練掌握\n")
        legend.add_run("R (Good) - 表現良好，穩定發展中\n")
        legend.add_run("D (Developing) - 發展中，偶爾需要引導\n")
        legend.add_run("N (Needs Improvement) - 需加強，建議親師共同協助")
        legend.style = 'Quote' # 用引用樣式讓字體稍微變小

    # 存到記憶體
    bio = io.BytesIO()
    doc.save(bio)
    return bio

def color_grade(val):
    if val == 'A': return 'background-color: #d4edda; color: green; font-weight: bold;'
    if val == 'R': return 'background-color: #fff3cd; color: #856404; font-weight: bold;'
    if val == 'D': return 'background-color: #ffeeba; color: orange; font-weight: bold;'
    if val == 'N': return 'background-color: #f8d7da; color: red; font-weight: bold;'
    return ''

# --- 4. 主頁面邏輯 ---

if menu == "📝 批次上傳與辨識":
    st.title("📝 評量表批次處理中心")
    st.info("💡 您現在可以一次選取多張照片，系統會自動排隊處理。")
    
    uploaded_files = st.file_uploader("請選擇評量表照片 (可多選)", type=['jpg', 'png', 'jpeg', 'heic'], accept_multiple_files=True)
    
    if uploaded_files:
        st.write(f"共選擇了 {len(uploaded_files)} 張照片")
        
        if st.button("🚀 開始批次辨識"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            all_processed_data = []
            headers_cache = ["指標1", "指標2", "指標3", "指標4"]

            for i, file in enumerate(uploaded_files):
                status_text.text(f"正在分析第 {i+1} 張照片：{file.name} ...")
                
                image = Image.open(file)
                result_json = analyze_image(image)
                
                if result_json:
                    current_headers = result_json.get("headers", [])
                    if len(current_headers) >= 4:
                        headers_cache = current_headers[:4]

                    for s in result_json.get("students", []):
                        row = {"幼兒姓名": s.get("name", "")}
                        scores = s.get("scores", [])
                        for idx, score in enumerate(scores):
                            if idx < 4:
                                row[f"指標{idx+1}"] = score 
                        row["備註"] = s.get("note", "")
                        all_processed_data.append(row)
                
                progress_bar.progress((i + 1) / len(uploaded_files))
                time.sleep(1)

            status_text.text("✅ 所有照片分析完成！")
            
            if all_processed_data:
                df = pd.DataFrame(all_processed_data)
                rename_map = {f"指標{i+1}": name for i, name in enumerate(headers_cache)}
                df = df.rename(columns=rename_map)
                
                st.session_state['class_data'] = df
                st.success(f"已成功彙整 {len(df)} 筆資料！")

    if 'class_data' in st.session_state:
        st.divider()
        st.subheader("📊 資料檢視")
        df = st.session_state['class_data']
        score_cols = [c for c in df.columns if c not in ["幼兒姓名", "備註"]]
        
        edited_df = st.data_editor(
            df.style.map(color_grade, subset=score_cols),
            use_container_width=True,
            num_rows="dynamic",
            height=600
        )
        st.session_state['class_data'] = edited_df.data

elif menu == "📄 匯出家長報告":
    st.title("📄 家長通知單匯出")
    
    if 'class_data' in st.session_state and not st.session_state['class_data'].empty:
        df = st.session_state['class_data']
        st.success(f"目前準備匯出 {len(df)} 位幼兒的個別報告。")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.info("點擊下方按鈕，下載後的 Word 檔將會是「每位幼兒一頁」，方便您直接列印發放。")
            
            # 產生 Word 檔
            doc_file = generate_individual_report(df)
            
            st.download_button(
                label="📥 下載個別評量報告 (Word)",
                data=doc_file,
                file_name="篤行幼兒園_個別評量報告.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
    else:
        st.warning("⚠️ 目前還沒有資料，請先去「批次上傳」頁面分析照片。")
