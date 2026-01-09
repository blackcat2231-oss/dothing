import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
from docx import Document # 用來製作 Word 檔
from docx.shared import Pt
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
    st.subheader("評量系統 v1.6 (量產版)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 批次上傳與辨識", "📄 匯出 Word 報告"])

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
    """AI 辨識核心 (v1.5版邏輯)"""
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

def generate_word_doc(df):
    """將資料轉為 Word 檔"""
    doc = Document()
    doc.add_heading('篤行幼兒園 - 學習區觀察評量報告', 0)
    
    # 建立表格
    table = doc.add_table(rows=1, cols=len(df.columns))
    table.style = 'Table Grid'
    
    # 填寫表頭
    hdr_cells = table.rows[0].cells
    for i, col_name in enumerate(df.columns):
        hdr_cells[i].text = col_name
    
    # 填寫內容
    for index, row in df.iterrows():
        row_cells = table.add_row().cells
        for i, value in enumerate(row):
            row_cells[i].text = str(value) if value else ""
            
    # 存到記憶體中
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
    
    # 允許上傳多個檔案 (accept_multiple_files=True)
    uploaded_files = st.file_uploader("請選擇評量表照片 (可多選)", type=['jpg', 'png', 'jpeg', 'heic'], accept_multiple_files=True)
    
    if uploaded_files:
        st.write(f"共選擇了 {len(uploaded_files)} 張照片")
        
        if st.button("🚀 開始批次辨識"):
            # 進度條
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            all_processed_data = []
            headers_cache = ["指標1", "指標2", "指標3", "指標4"] # 預設值

            for i, file in enumerate(uploaded_files):
                status_text.text(f"正在分析第 {i+1} 張照片：{file.name} ...")
                
                image = Image.open(file)
                result_json = analyze_image(image)
                
                if result_json:
                    # 更新表頭 (以第一張或最新一張為準)
                    current_headers = result_json.get("headers", [])
                    if len(current_headers) >= 4:
                        headers_cache = current_headers[:4]

                    # 處理學生資料
                    for s in result_json.get("students", []):
                        row = {"幼兒姓名": s.get("name", "")}
                        scores = s.get("scores", [])
                        for idx, score in enumerate(scores):
                            if idx < 4:
                                # 這裡暫時用指標1,2,3,4當Key，顯示時再換成文字，避免不同頁表頭文字些微差異導致無法合併
                                row[f"指標{idx+1}"] = score 
                        row["備註"] = s.get("note", "")
                        all_processed_data.append(row)
                
                # 更新進度條
                progress_bar.progress((i + 1) / len(uploaded_files))
                time.sleep(1) # 避免太快撞到 API 限制

            status_text.text("✅ 所有照片分析完成！")
            
            if all_processed_data:
                # 轉成 DataFrame
                df = pd.DataFrame(all_processed_data)
                
                # 將欄位名稱換成真正的文字
                rename_map = {f"指標{i+1}": name for i, name in enumerate(headers_cache)}
                df = df.rename(columns=rename_map)
                
                # 存入 Session
                st.session_state['class_data'] = df
                st.success(f"已成功彙整 {len(df)} 筆資料！")

    # 顯示編輯區 (如果 Session 有資料)
    if 'class_data' in st.session_state:
        st.divider()
        st.subheader("📊 資料檢視與修訂")
        
        df = st.session_state['class_data']
        # 找出指標欄位用於上色
        score_cols = [c for c in df.columns if c not in ["幼兒姓名", "備註"]]
        
        edited_df = st.data_editor(
            df.style.map(color_grade, subset=score_cols),
            use_container_width=True,
            num_rows="dynamic",
            height=600
        )
        
        # 更新 Session
        st.session_state['class_data'] = edited_df.data

elif menu == "📄 匯出 Word 報告":
    st.title("📄 報告匯出中心")
    
    if 'class_data' in st.session_state and not st.session_state['class_data'].empty:
        df = st.session_state['class_data']
        st.write("目前系統內有以下資料：")
        st.dataframe(df.head())
        
        st.write("---")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.info("點擊下方按鈕下載 Word 檔")
            
            # 產生 Word 檔
            doc_file = generate_word_doc(df)
            
            st.download_button(
                label="📥 下載 Word 評量報告",
                data=doc_file,
                file_name="篤行幼兒園_評量報告.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
    else:
        st.warning("⚠️ 目前還沒有資料，請先去「批次上傳」頁面分析照片。")
