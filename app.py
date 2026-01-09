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
    th {
        white-space: normal !important;
        background-color: #f0f2f6 !important;
    }
    td {text-align: center !important; vertical-align: middle !important;}
    td:last-child {text-align: left !important;}
    .stButton button { width: 100%; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 初始化 Session ---
if 'raw_records' not in st.session_state: st.session_state['raw_records'] = []
if 'class_df' not in st.session_state: st.session_state['class_df'] = pd.DataFrame()

# --- 2. 側邊欄 (安全版：無外部圖片) ---
with st.sidebar:
    st.header("🌱 篤行幼兒園") # 改用文字標題
    st.subheader("評量系統 v2.6 (診斷版)")
    
    # 狀態儀表板
    st.markdown("---")
    count = len(st.session_state['raw_records'])
    st.metric("📊 暫存資料數", f"{count} 筆")
    if count > 0:
        st.caption("✅ 資料已保存，可產生報告")
    st.markdown("---")

    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("❌ API Key 未設定")
        st.stop()
        
    menu = st.radio("功能選單", ["📝 批次上傳與辨識", "📄 產生整合評量報告"])

# --- 3. 核心功能 ---

def get_fast_model():
    return genai.GenerativeModel('gemini-1.5-flash')

def analyze_single_image(image_file):
    model = get_fast_model()
    image = Image.open(image_file)
    
    prompt = """
    你是一位精準的資料輸入員。這是一張幼兒園評量表。
    
    【任務一：判斷學習區】
    看表頭文字，判斷是哪個學習區 (如:語文區,數學區...)。存入 "area"。

    【任務二：讀取指標】
    讀取表格上方那 4 個欄位標題。

    【任務三：判斷分數 (座標定位)】
    每個格子印有 "1 2 3 4"。老師圈選了一個。
    請看圓圈圈在哪裡：
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
    
    config = genai.types.GenerationConfig(temperature=0.0)
    
    # 重試機制 (應對 429 錯誤)
    max_retries = 3
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, image], generation_config=config)
            
            # 清潔 JSON
            text = response.text
            if "```json" in text:
                text = text.replace("```json", "").replace("```", "")
            elif "```" in text:
                text = text.replace("```", "")
            
            return {"success": True, "data": json.loads(text.strip())}
            
        except Exception as e:
            last_error = str(e)
            if "429" in last_error: # 塞車了
                time.sleep(3 * (attempt + 1)) # 休息久一點: 3秒, 6秒...
                continue
            else:
                return {"success": False, "error": last_error}
    
    return {"success": False, "error": f"重試 {max_retries} 次後失敗。原因: {last_error}"}

def process_images_parallel(files):
    results = []
    errors = []
    
    # 降低併發數到 2，雖然慢一點點，但保證不塞車
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_file = {executor.submit(analyze_single_image, f): f for f in files}
        
        bar = st.progress(0)
        info = st.empty()
        total = len(files)
        done = 0
        
        for future in concurrent.futures.as_completed(future_to_file):
            f = future_to_file[future]
            done += 1
            info.text(f"正在分析 ({done}/{total}): {f.name}")
            bar.progress(done / total)
            
            outcome = future.result()
            if outcome["success"]:
                results.append(outcome["data"])
            else:
                errors.append(f"{f.name}: {outcome['error']}")
            
            # 每張照片處理完稍微休息一下
            time.sleep(1)
            
    info.empty()
    bar.empty()
    return results, errors

def generate_teacher_comments_fast(student_name, records):
    model = get_fast_model()
    data_text = f"幼兒：{student_name}\n"
    for r in records:
        data_text += f"[{r['area']}] 備註:{r['note']}\n"
        data_text += f"成績:{[d['score'] for d in r['details']]}\n"

    prompt = f"""
    你是幼兒園園長。請為 {student_name} 寫一份【A4精簡版】評語。
    限制：總字數 200 字內。語氣溫暖。
    格式 JSON：
    {{ "observation": "觀察...", "suggestion": "建議..." }}
    """
    config = genai.types.GenerationConfig(temperature=0.7)
    try:
        response = model.generate_content(prompt, generation_config=config)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"observation": "請親師多加溝通。", "suggestion": "陪伴是最好的禮物。"}

def create_word_report(grouped_data):
    doc = Document()
    # 設定邊界
    for section in doc.sections:
        section.top_margin = Cm(1.27)
        section.bottom_margin = Cm(1.27)
        section.left_margin = Cm(1.27)
        section.right_margin = Cm(1.27)
    
    # 設定字型
    style = doc.styles['Normal']
    style.font.name = 'Microsoft JhengHei'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft JhengHei')
    style.font.size = Pt(10)
    
    bar = st.progress(0)
    status = st.empty()
    total = len(grouped_data)
    
    for idx, (name, records) in enumerate(grouped_data.items()):
        status.text(f"撰寫報告 ({idx+1}/{total}): {name} ...")
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
        
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        
        hdr = table.rows[0].cells
        hdr[0].text = "各區學習指標內容"
        hdr[1].text = "結果"
        table.columns[0].width = Cm(14)
        table.columns[1].width = Cm(3)
        
        for r in records:
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
    st.title("📝 批次處理 (v2.6 診斷版)")
    st.info("💡 確保穩定：已降低平行處理數量，避免 API 塞車。")
    
    files = st.file_uploader("選擇照片 (全選)", type=['jpg','png','jpeg'], accept_multiple_files=True)
    
    if files and st.button("🚀 開始分析"):
        results, errors = process_images_parallel(files)
        
        # 1. 處理成功的部分
        if results:
            all_data = []
            raw_records = []
            for res in results:
                area = res.get("area","未知")
                headers = res.get("headers", ["I1","I2","I3","I4"])
                for s in res.get("students", []):
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
            
            # 追加資料
            if 'raw_records' not in st.session_state: st.session_state['raw_records'] = []
            st.session_state['raw_records'].extend(raw_records)
            
            # 更新顯示表格
            if 'class_df' not in st.session_state: st.session_state['class_df'] = pd.DataFrame()
            new_df = pd.DataFrame(all_data)
            st.session_state['class_df'] = pd.concat([st.session_state['class_df'], new_df], ignore_index=True)
            
            st.success(f"✅ 成功處理 {len(results)} 張照片！")
        
        # 2. 處理失敗的部分 (診斷報告)
        if errors:
            st.error(f"⚠️ 有 {len(errors)} 張照片處理失敗，原因如下：")
            for err in errors:
                st.code(err) # 顯示真實錯誤訊息
                if "429" in err:
                    st.warning("👉 提示：429 代表 Google API 忙碌中，請等待 1 分鐘後再試。")

    if not st.session_state['class_df'].empty:
        st.dataframe(st.session_state['class_df'])

elif menu == "📄 產生整合評量報告":
    st.title("📄 報告生成")
    
    if st.session_state['raw_records']:
        grouped = {}
        for r in st.session_state['raw_records']:
            name = r['name']
            if name not in grouped: grouped[name] = []
            grouped[name].append(r)
        
        st.write(f"📚 資料庫就緒：共 {len(grouped)} 位幼兒資料。")

        if st.button("✨ 點擊這裡產生 Word 檔"):
            with st.spinner("AI 園長正在動筆寫評語..."):
                doc_file = create_word_report(grouped)
                st.session_state['generated_doc'] = doc_file.getvalue()
                st.success("報告產生完畢！")
        
        if 'generated_doc' in st.session_state:
            st.download_button(
                label="📥 點我下載 Word 評量報告",
                data=st.session_state['generated_doc'],
                file_name="篤行幼兒園_評量報告_v2.6.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
    else:
        st.warning("⚠️ 暫存區是空的！請先回上一頁上傳並分析照片。")
