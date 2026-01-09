import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import io
import time
import concurrent.futures

# --- 1. 網頁基本設定 ---
st.set_page_config(page_title="篤行幼兒園評量系統", layout="wide", page_icon="🌱")

st.markdown("""
    <style>
    .main {background-color: #f9f9f9;}
    .stHeader {color: #2c3e50;}
    /* 讓表格好看一點 */
    th {
        white-space: normal !important;
        background-color: #f0f2f6 !important;
    }
    td {text-align: center !important; vertical-align: middle !important;}
    td:last-child {text-align: left !important;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄 ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2231/2231649.png", width=100)
    st.title("🌱 篤行幼兒園")
    st.subheader("評量系統 v2.2 (Flash戰術版)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 批次上傳與辨識", "📄 產生整合評量報告"])

# --- 3. 核心功能 (速度優先策略) ---

def get_fast_model():
    """
    為了避免 '8分鐘慘劇'，我們強制使用 Flash。
    Flash 的速率限制比 Pro 寬鬆很多 (15 RPM vs 2 RPM)。
    """
    return genai.GenerativeModel('gemini-1.5-flash')

def analyze_single_image(image_file):
    """
    單張分析：使用 v1.4 的「座標定位」邏輯來彌補 Flash 的視力
    """
    model = get_fast_model()
    image = Image.open(image_file)
    
    # 這是您覺得最準的 v1.4 指令
    prompt = """
    你是一位精準的資料輸入員。這是一張幼兒園評量表。
    
    【任務一：判斷學習區】
    看表頭文字，判斷是哪個學習區 (如:語文區,數學區...)。存入 "area"。

    【任務二：讀取指標】
    讀取表格上方那 4 個欄位標題。

    【任務三：判斷分數 (座標定位)】
    每個格子印有 "1 2 3 4"。老師圈選了一個。
    請像玩「找不同」一樣，看圓圈圈在哪裡：
    - 圈在 1 -> "A"
    - 圈在 2 -> "R"
    - 圈在 3 -> "D"
    - 圈在 4 -> "N"
    
    【備註】
    合併格內所有文字，保留編號。

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
    
    # Temperature 0 是準確的關鍵
    config = genai.types.GenerationConfig(temperature=0.0, response_mime_type="application/json")
    
    # 加入重試機制，萬一還是太快被擋，休息一下再試
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, image], generation_config=config)
            return json.loads(response.text)
        except Exception as e:
            if "429" in str(e): # 如果是 Too Many Requests
                time.sleep(2 * (attempt + 1)) # 等待 2, 4, 6 秒
                continue
            else:
                print(f"Error: {e}")
                return None
    return None

def process_images_parallel(files):
    """
    平行處理，但限制同時 4 個，避免塞車
    """
    results = []
    # max_workers=4 是安全值
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {executor.submit(analyze_single_image, f): f for f in files}
        
        # 進度條
        bar = st.progress(0)
        info = st.empty()
        total = len(files)
        done = 0
        
        for future in concurrent.futures.as_completed(future_to_file):
            f = future_to_file[future]
            done += 1
            info.text(f"正在分析 ({done}/{total}): {f.name}")
            bar.progress(done / total)
            
            data = future.result()
            if data: results.append(data)
            
    info.text(f"✅ 完成！共處理 {total} 張照片。")
    time.sleep(1)
    info.empty()
    bar.empty()
    return results

def generate_teacher_comments_fast(student_name, records):
    """
    寫評語也改用 Flash，不然 24 位學生用 Pro 寫會跑 10 分鐘以上。
    """
    model = get_fast_model()
    
    data_text = f"幼兒：{student_name}\n"
    for r in records:
        data_text += f"[{r['area']}] 備註:{r['note']}\n"
        # 簡化分數描述以免 token 太多
        data_text += f"成績:{[d['score'] for d in r['details']]}\n"

    prompt = f"""
    你是幼兒園園長。請為 {student_name} 寫一份【A4精簡版】評語。
    限制：總字數 200 字內。語氣溫暖。
    格式 JSON：
    {{ "observation": "觀察...", "suggestion": "建議..." }}
    """
    config = genai.types.GenerationConfig(temperature=0.7, response_mime_type="application/json")
    try:
        response = model.generate_content(prompt, generation_config=config)
        return json.loads(response.text)
    except:
        return {"observation": "請親師多加溝通。", "suggestion": "陪伴是最好的禮物。"}

def create_word_report(grouped_data):
    doc = Document()
    
    # 設定邊界 (1.27cm)
    section = doc.sections[0]
    section.top_margin = Cm(1.27)
    section.bottom_margin = Cm(1.27)
    section.left_margin = Cm(1.27)
    section.right_margin = Cm(1.27)
    
    style = doc.styles['Normal']
    style.font.name = 'Microsoft JhengHei'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft JhengHei')
    style.font.size = Pt(10)
    
    bar = st.progress(0)
    status = st.empty()
    total = len(grouped_data)
    
    for idx, (name, records) in enumerate(grouped_data.items()):
        status.text(f"正在撰寫報告 ({idx+1}/{total}): {name} ...")
        bar.progress((idx+1)/total)
        
        if idx > 0: doc.add_page_break()
        
        # 標題
        head = doc.add_heading('篤行非營利幼兒園  幼兒學習區個別評量報告', 0)
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        head.style.font.size = Pt(16)
        
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(f"幼兒姓名：{name}     日期：2026年___月___日")
        run.bold = True
        run.font.size = Pt(12)
        
        # 表格 (自動調整寬度)
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        # 不鎖死寬度，讓 Word 自己算，避免消失
        
        hdr = table.rows[0].cells
        hdr[0].text = "各區學習指標內容"
        hdr[1].text = "結果"
        
        # 手動給個大概比例，引導 Word
        table.columns[0].width = Cm(14)
        table.columns[1].width = Cm(3)
        
        for r in records:
            # 區域名稱
            row = table.add_row().cells
            row[0].merge(row[1])
            p_area = row[0].paragraphs[0]
            run_area = p_area.add_run(f"■ {r['area']}")
            run_area.bold = True
            run_area.font.color.rgb = RGBColor(0, 51, 102)
            
            for item in r['details']:
                row_item = table.add_row().cells
                row_item[0].text = item['idx']
                row_item[0].paragraphs[0].paragraph_format.left_indent = Cm(0.5)
                
                row_item[1].text = item['score']
                row_item[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph("")
        
        # 評語
        comments = generate_teacher_comments_fast(name, records)
        
        doc.add_paragraph("【老師的觀察】").runs[0].bold = True
        doc.add_paragraph(comments['observation'])
        
        doc.add_paragraph("【居家互動小撇步】").runs[0].bold = True
        doc.add_paragraph(comments['suggestion'])
        
        footer = doc.add_paragraph("評量代號：A(主動熟練) R(表現良好) D(發展中) N(需協助)")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.runs[0].font.color.rgb = RGBColor(128,128,128)
        footer.runs[0].font.size = Pt(9)

    bar.empty()
    status.empty()
    
    bio = io.BytesIO()
    doc.save(bio)
    return bio

# --- 4. 主頁面 ---

if menu == "📝 批次上傳與辨識":
    st.title("📝 批次處理 (v2.2 極速版)")
    st.info("💡 使用 Flash 引擎 + 座標定位技術，確保速度與準確度的平衡。")
    
    files = st.file_uploader("選擇照片 (全選)", type=['jpg','png','jpeg'], accept_multiple_files=True)
    
    if files and st.button("🚀 開始分析"):
        results = process_images_parallel(files)
        
        if results:
            all_data = []
            raw_records = []
            for res in results:
                area = res.get("area","未知")
                headers = res.get("headers", ["I1","I2","I3","I4"])
                for s in res.get("students", []):
                    # 存檔邏輯
                    row = {"幼兒姓名":s.get("name"), "學習區":area}
                    scores = s.get("scores", [])
                    
                    details = []
                    for i, sc in enumerate(scores):
                        if i < 4: 
                            h_name = headers[i] if i < len(headers) else f"指標{i+1}"
                            row[h_name] = sc
                            details.append({"idx": h_name, "score": sc})
                            
                    row["備註"] = s.get("note")
                    all_data.append(row)
                    
                    raw_records.append({
                        "name": s.get("name"),
                        "area": area,
                        "details": details,
                        "note": s.get("note")
                    })
            
            st.session_state['class_df'] = pd.DataFrame(all_data)
            st.session_state['raw_records'] = raw_records
            st.success(f"處理完成！共 {len(results)} 張照片。")

    if 'class_df' in st.session_state:
        st.dataframe(st.session_state['class_df'])

elif menu == "📄 產生整合評量報告":
    st.title("📄 報告生成")
    if 'raw_records' in st.session_state:
        grouped = {}
        for r in st.session_state['raw_records']:
            name = r['name']
            if name not in grouped: grouped[name] = []
            grouped[name].append(r)
            
        if st.button("✨ 下載 Word"):
            doc = create_word_report(grouped)
            st.download_button("📥 下載", doc, "評量報告_v2.2.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
