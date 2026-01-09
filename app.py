import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
import io
import time
import concurrent.futures # 引入平行運算模組

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
    st.subheader("評量系統 v2.1 (Pro平行加速版)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 批次上傳與辨識", "📄 產生整合評量報告"])

# --- 3. 核心功能函式 (升級：Pro模型 + 平行處理) ---

def get_best_model():
    """
    強制使用 Gemini 1.5 Pro (或更高級)，確保視力最好。
    不再使用 Flash，因為準確度優先。
    """
    try:
        # 優先尋找 Pro 模型
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini-1.5-pro' in m.name:
                    return genai.GenerativeModel(m.name), 'Gemini 1.5 Pro (高精準)'
    except:
        pass
    # 萬一真的沒有 Pro，才用 Flash 墊檔
    return genai.GenerativeModel('gemini-1.5-flash'), 'Flash (備用)'

def analyze_single_image(image_file):
    """
    單張圖片分析函式 (給平行運算呼叫用)
    """
    model, model_name = get_best_model()
    image = Image.open(image_file)
    
    prompt = """
    你是一位精準的資料輸入員。這是一張幼兒園的評量表。
    
    【任務一：判斷學習區】
    請看表頭文字，判斷這是哪個學習區？(如：語文區、數學區、美勞區...)。
    將結果放入 "area" 欄位。

    【任務二：讀取指標】
    讀取表格上方那 4 個欄位標題文字。

    【任務三：讀取資料 (關鍵：座標定位)】
    每個指標格子裡都有印好的 "1 2 3 4"。老師會圈選其中一個。
    請**非常仔細**地判斷「圓圈圈在哪個數字上」：
    - 圈在 1 -> "A"
    - 圈在 2 -> "R"
    - 圈在 3 -> "D"
    - 圈在 4 -> "N"
    
    【備註欄】
    將格子內所有文字合併，保留編號。

    【輸出 JSON】
    {
      "area": "語文區",
      "headers": ["指標1", "指標2", "指標3", "指標4"],
      "students": [
        {"name": "幼兒一", "scores": ["A", "R", "A", "R"], "note": "備註..."},
        ...
      ]
    }
    """
    
    config = genai.types.GenerationConfig(temperature=0.0, response_mime_type="application/json")
    try:
        response = model.generate_content([prompt, image], generation_config=config)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error analyzing image: {e}")
        return None

def process_images_in_parallel(uploaded_files):
    """
    平行處理核心：同時發送所有照片給 AI
    """
    results = []
    # 使用 ThreadPoolExecutor 同時處理最多 10 張照片 (可依 API 限制調整)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # 送出所有任務
        future_to_file = {executor.submit(analyze_single_image, file): file for file in uploaded_files}
        
        # 建立進度條
        progress_bar = st.progress(0)
        completed_count = 0
        total_files = len(uploaded_files)
        
        for future in concurrent.futures.as_completed(future_to_file):
            file = future_to_file[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
            except Exception as e:
                st.error(f"處理照片 {file.name} 時發生錯誤: {e}")
            
            # 更新進度
            completed_count += 1
            progress_bar.progress(completed_count / total_files)
            
    return results

def generate_teacher_comments(student_name, records):
    """AI 寫手 (Pro版)"""
    model, _ = get_best_model()
    
    data_summary = f"幼兒姓名：{student_name}\n"
    for r in records:
        data_summary += f"--- {r['area']} ---\n"
        details_text = ", ".join([f"{d['idx']}: {d['score']}" for d in r['details']])
        data_summary += f"表現：{details_text}\n"
        data_summary += f"備註：{r['note']}\n"
    
    prompt = f"""
    你是一位幼兒園園長。請撰寫一份給家長的「A4精簡版」評語。
    
    【資料】
    {data_summary}
    
    【限制】
    總字數請嚴格控制在 200 字以內，以免 A4 紙塞不下。
    分兩段：
    1. 【老師的觀察】
    2. 【居家互動小撇步】
    
    【格式 JSON】
    {{
        "observation": "簡短觀察...",
        "suggestion": "簡短建議..."
    }}
    """
    config = genai.types.GenerationConfig(temperature=0.7, response_mime_type="application/json")
    try:
        response = model.generate_content(prompt, generation_config=config)
        return json.loads(response.text)
    except:
        return {"observation": "AI 撰寫中...", "suggestion": "建議親師保持密切聯繫。"}

def create_integrated_word(grouped_data):
    """產生 A4 報告 (修復表格消失問題)"""
    doc = Document()
    
    # 1. 設定窄邊界
    section = doc.sections[0]
    section.top_margin = Cm(1.27)
    section.bottom_margin = Cm(1.27)
    section.left_margin = Cm(1.27)
    section.right_margin = Cm(1.27)
    
    style = doc.styles['Normal']
    style.font.name = 'Microsoft JhengHei'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft JhengHei')
    style.font.size = Pt(10)
    
    # 進度顯示 (平行處理寫評語)
    # 注意：寫評語也可以平行處理，這裡為了穩定性先維持序列，但因為數量少(依人數)，應該還好
    # 如果人數多，這裡也可以改成平行
    
    progress_text = "正在撰寫報告..."
    my_bar = st.progress(0, text=progress_text)
    total_students = len(grouped_data)
    
    for idx, (name, records) in enumerate(grouped_data.items()):
        my_bar.progress((idx + 1) / total_students, text=f"正在為 {name} 製作報告...")
        
        if idx > 0: doc.add_page_break()
        
        # 標題
        head = doc.add_heading('篤行非營利幼兒園  幼兒學習區個別評量報告', 0)
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        head.style.font.size = Pt(16)
        
        p_info = doc.add_paragraph()
        p_info.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_info.add_run(f"幼兒姓名：{name}     日期：2026年___月___日")
        run.bold = True
        run.font.size = Pt(12)
        p_info.paragraph_format.space_after = Pt(6)
        
        # 表格 (修復版：不強制鎖死寬度，讓 Word 自動調整)
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        # table.autofit = True # 預設就是 True，我們不要手動關掉它
        
        hdr = table.rows[0].cells
        hdr[0].text = "各區學習指標內容"
        hdr[1].text = "結果"
        
        # 設定第一欄稍微寬一點，第二欄窄一點 (透過百分比概念，但不強制鎖死)
        # Word Python 對欄寬控制比較微妙，最穩定的方法是讓它自動，或者只給建議值
        table.columns[0].width = Cm(14) 
        table.columns[1].width = Cm(4) # 給足夠空間顯示 A/R/D/N
        
        for cell in hdr:
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            cell.paragraphs[0].runs[0].bold = True
        
        for record in records:
            # 區域標題
            row_area = table.add_row().cells
            row_area[0].merge(row_area[1])
            p_area = row_area[0].paragraphs[0]
            run_area = p_area.add_run(f"■ {record['area']}")
            run_area.bold = True
            run_area.font.color.rgb = RGBColor(0, 51, 102)
            
            for item in record['details']:
                row = table.add_row().cells
                # 左欄
                row[0].text = item['idx']
                row[0].paragraphs[0].paragraph_format.left_indent = Cm(0.5)
                # 右欄
                row[1].text = item['score']
                row[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph("")
        
        # AI 評語
        ai_comments = generate_teacher_comments(name, records)
        
        p_obs_title = doc.add_paragraph()
        p_obs_title.add_run("【老師的觀察】").bold = True
        doc.add_paragraph(ai_comments['observation'])
        
        p_sug_title = doc.add_paragraph()
        p_sug_title.add_run("【居家互動小撇步】").bold = True
        doc.add_paragraph(ai_comments['suggestion'])
        
        footer = doc.add_paragraph("評量代號：A(主動熟練)  R(表現良好)  D(發展中/需示範)  N(未觀察/需協助)")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.style.font.size = Pt(9)
        footer.runs[0].font.color.rgb = RGBColor(100, 100, 100)

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
    st.title("📝 評量表批次處理 (v2.1 平行Pro版)")
    st.info("💡 系統已啟用「平行運算技術」，您可以一次上傳全班 24 張照片，處理速度將大幅提升！")
    
    uploaded_files = st.file_uploader("請選擇評量表照片 (建議一次全選)", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True)
    
    if uploaded_files and st.button("🚀 開始極速分析"):
        
        # 呼叫平行處理函式
        json_results = process_images_in_parallel(uploaded_files)
        
        if json_results:
            all_data = []
            raw_records = []
            
            for result in json_results:
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
            
            st.session_state['class_df'] = pd.DataFrame(all_data)
            st.session_state['raw_records'] = raw_records
            st.success(f"✅ 全數處理完成！共 {len(uploaded_files)} 張照片。")

    if 'class_df' in st.session_state:
        st.divider()
        st.subheader("📊 資料檢視")
        st.dataframe(st.session_state['class_df'], use_container_width=True)

elif menu == "📄 產生整合評量報告":
    st.title("📄 整合報告生成")
    if 'raw_records' in st.session_state:
        grouped_data = {}
        for r in st.session_state['raw_records']:
            name = r['name']
            if name not in grouped_data: grouped_data[name] = []
            grouped_data[name].append(r)
            
        if st.button("✨ 產生報告 (Word)"):
            doc_file = create_integrated_word(grouped_data)
            st.download_button(
                label="📥 下載 Word 報告",
                data=doc_file,
                file_name="篤行幼兒園_全班評量報告_v2.1.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
