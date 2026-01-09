import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.oxml.ns import qn
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
    st.subheader("評量系統 v1.9 (A4濃縮版)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 批次上傳與辨識", "📄 產生整合評量報告"])

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
    你是一位專業的資料輸入員。請分析這張幼兒園評量表。
    
    【任務一：判斷學習區】
    請閱讀表頭，判斷這張表屬於哪個學習區？(例如：語文區、數學區、美勞區...)。
    請將結果放入 "area" 欄位。

    【任務二：讀取表頭指標】
    請讀取表格上方那 4 個欄位標題文字。
    
    【任務三：讀取幼兒資料】
    請依序讀取每一列幼兒的資料。
    
    **關於「備註」：**
    1. 將格子內所有文字合併。
    2. 保留換行或編號。

    **關於「分數」：**
    - 圈選 1 -> "A"
    - 圈選 2 -> "R"
    - 圈選 3 -> "D"
    - 圈選 4 -> "N"

    【輸出格式】
    回傳 JSON：
    {
      "area": "語文區",
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

def generate_teacher_comments(student_name, records):
    """AI 寫手核心 (要求更精簡)"""
    model, _ = get_gemini_model()
    
    data_summary = f"幼兒姓名：{student_name}\n"
    for r in records:
        data_summary += f"--- {r['area']} ---\n"
        data_summary += f"指標與成績：{r['details']}\n"
        data_summary += f"老師原始備註：{r['note']}\n"
    
    prompt = f"""
    你是一位幼兒園園長。請根據幼兒在不同學習區的表現撰寫評語。
    
    【重要：版面限制】
    因為要塞進一張 A4 紙，請務必**言簡意賅**，不要寫長篇大論。
    總字數控制在 250 字以內。
    
    【幼兒資料】
    {data_summary}
    
    【撰寫目標】
    1. **【老師的觀察】**：綜合亮點與需協助之處，語氣溫暖專業。
    2. **【居家互動】**：給予 1-2 個具體簡短的建議。
    
    【輸出格式】
    回傳 JSON：
    {{
        "observation": "簡短的觀察段落...",
        "suggestion": "簡短的建議段落..."
    }}
    """
    
    config = genai.types.GenerationConfig(temperature=0.7, response_mime_type="application/json")
    try:
        response = model.generate_content(prompt, generation_config=config)
        return json.loads(response.text)
    except:
        return {"observation": "AI 撰寫中...", "suggestion": "建議親師保持密切聯繫。"}

def create_integrated_word(grouped_data):
    """產生 A4 濃縮版 Word 報告"""
    doc = Document()
    
    # 1. 設定極窄邊界 (Narrow Margins) - 關鍵！
    section = doc.sections[0]
    section.top_margin = Cm(1.27)
    section.bottom_margin = Cm(1.27)
    section.left_margin = Cm(1.27)
    section.right_margin = Cm(1.27)
    
    # 設定中文字型
    style = doc.styles['Normal']
    style.font.name = 'Microsoft JhengHei'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft JhengHei')
    style.font.size = Pt(10) # 預設字體縮小至 10pt
    
    # 進度顯示
    progress_text = "正在撰寫報告..."
    my_bar = st.progress(0, text=progress_text)
    total_students = len(grouped_data)
    
    for idx, (name, records) in enumerate(grouped_data.items()):
        my_bar.progress((idx + 1) / total_students, text=f"正在為 {name} 製作 A4 報告...")
        
        if idx > 0: doc.add_page_break()
        
        # 2. 標題區 (縮小行距)
        head = doc.add_heading('篤行非營利幼兒園  幼兒學習區個別評量報告', 0)
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        head.style.font.size = Pt(16) # 標題稍微縮小
        
        # 基本資料列
        p_info = doc.add_paragraph()
        p_info.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_info.add_run(f"幼兒姓名：{name}     日期：2026年___月___日")
        run.bold = True
        run.font.size = Pt(12)
        p_info.paragraph_format.space_after = Pt(6) # 減少標題下方的空白
        
        # 3. 建立緊湊表格
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        table.autofit = False # 關閉自動調整，改用手動指定寬度
        table.allow_autofit = False
        
        # 設定欄寬 (關鍵：成績欄弄很窄)
        # A4 寬度約 21cm - 邊界 2.54cm = 可用約 18.5cm
        # 指標欄給 16cm, 成績欄給 2.5cm
        table.columns[0].width = Cm(16.0) 
        table.columns[1].width = Cm(2.5)

        # 表頭
        hdr = table.rows[0].cells
        hdr[0].text = "各區學習指標內容"
        hdr[1].text = "結果"
        
        # 表頭樣式
        for cell in hdr:
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = cell.paragraphs[0].runs[0]
            run.bold = True
            run.font.size = Pt(11)
            # 設定背景色為淡灰 (需用 XML，此處省略以保程式碼簡潔)
        
        # 填入各區資料
        for record in records:
            # 區域標題列 (例如：【語文區】) - 合併儲存格
            row_area = table.add_row().cells
            row_area[0].merge(row_area[1])
            p_area = row_area[0].paragraphs[0]
            run_area = p_area.add_run(f"■ {record['area']}")
            run_area.bold = True
            run_area.font.color.rgb = RGBColor(0, 51, 102) # 深藍
            run_area.font.size = Pt(11)
            # 讓區域標題列矮一點
            row_area[0].paragraphs[0].paragraph_format.space_before = Pt(2)
            row_area[0].paragraphs[0].paragraph_format.space_after = Pt(2)
            
            # 指標列
            for item in record['details']:
                row = table.add_row().cells
                
                # 左欄：指標文字
                p_idx = row[0].paragraphs[0]
                p_idx.add_run(item['idx']).font.size = Pt(10)
                p_idx.paragraph_format.left_indent = Cm(0.5) # 稍微縮排
                p_idx.paragraph_format.space_after = Pt(2) # 緊湊行距
                
                # 右欄：成績
                p_score = row[1].paragraphs[0]
                run_score = p_score.add_run(item['score'])
                run_score.font.size = Pt(10)
                run_score.bold = True
                p_score.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_score.paragraph_format.space_after = Pt(2)

        doc.add_paragraph("") # 小空行
        
        # 4. AI 評語區 (呼叫寫手)
        ai_comments = generate_teacher_comments(name, records)
        
        # 老師的觀察
        p_obs_title = doc.add_paragraph()
        run_obs = p_obs_title.add_run("【老師的觀察】")
        run_obs.bold = True
        run_obs.font.size = Pt(11)
        
        p_obs = doc.add_paragraph(ai_comments['observation'])
        p_obs.paragraph_format.space_after = Pt(6) # 段落間距縮小
        
        # 居家互動
        p_sug_title = doc.add_paragraph()
        run_sug = p_sug_title.add_run("【居家互動小撇步】")
        run_sug.bold = True
        run_sug.font.size = Pt(11)
        
        p_sug = doc.add_paragraph(ai_comments['suggestion'])
        p_sug.paragraph_format.space_after = Pt(12)
        
        # 5. 頁尾說明 (置底)
        footer = doc.add_paragraph("評量代號：A(主動熟練)  R(表現良好)  D(發展中/需示範)  N(未觀察/需協助)")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.style.font.size = Pt(9)
        footer.runs[0].font.color.rgb = RGBColor(100, 100, 100) # 灰色

    my_bar.empty()
    
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
    st.title("📝 評量表批次處理 (v1.9)")
    st.info("💡 請上傳不同學習區的照片，系統將自動識別並歸檔。")
    
    uploaded_files = st.file_uploader("請選擇評量表照片", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True)
    
    if uploaded_files and st.button("🚀 開始分析"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_data = []
        raw_records = []

        for i, file in enumerate(uploaded_files):
            status_text.text(f"正在分析第 {i+1} 張照片...")
            image = Image.open(file)
            result = analyze_image(image)
            
            if result:
                area = result.get("area", "未知區域")
                headers = result.get("headers", ["指標1","指標2","指標3","指標4"])[:4]
                
                for s in result.get("students", []):
                    # DataFrame 用
                    row = {"幼兒姓名": s.get("name"), "學習區": area}
                    scores = s.get("scores", [])
                    for idx, score in enumerate(scores):
                        if idx < 4: row[headers[idx]] = score
                    row["備註"] = s.get("note")
                    all_data.append(row)
                    
                    # Word 生成用
                    details = []
                    for idx, score in enumerate(scores):
                        if idx < 4:
                            details.append({"idx": headers[idx], "score": score})
                            
                    raw_records.append({
                        "name": s.get("name"),
                        "area": area,
                        "details": details,
                        "note": s.get("note")
                    })

            progress_bar.progress((i + 1) / len(uploaded_files))
            time.sleep(1)

        if all_data:
            st.session_state['class_df'] = pd.DataFrame(all_data)
            st.session_state['raw_records'] = raw_records
            st.success(f"已成功讀取 {len(uploaded_files)} 張表單！")

    if 'class_df' in st.session_state:
        st.divider()
        st.subheader("📊 資料預覽")
        st.dataframe(st.session_state['class_df'], use_container_width=True)

elif menu == "📄 產生整合評量報告":
    st.title("📄 A4 濃縮報告生成")
    
    if 'raw_records' in st.session_state and len(st.session_state['raw_records']) > 0:
        records = st.session_state['raw_records']
        
        grouped_data = {}
        for r in records:
            name = r['name']
            if name not in grouped_data:
                grouped_data[name] = []
            grouped_data[name].append(r)
            
        st.success(f"目前資料庫中共有 {len(grouped_data)} 位幼兒資料。")
        st.info("按下按鈕後，AI 將撰寫「A4 濃縮版」的整合報告。")
        
        if st.button("✨ 產生報告 (A4濃縮版)"):
            doc_file = create_integrated_word(grouped_data)
            
            st.download_button(
                label="📥 下載 A4 濃縮報告 (Word)",
                data=doc_file,
                file_name="篤行幼兒園_個別評量報告_A4版.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
    else:
        st.warning("⚠️ 尚無資料，請先至「批次上傳」頁面分析照片。")
