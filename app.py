import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json

# --- 1. 網頁基本設定 ---
st.set_page_config(page_title="篤行幼兒園評量系統", layout="wide", page_icon="🌱")

st.markdown("""
    <style>
    .main {background-color: #f9f9f9;}
    .stHeader {color: #2c3e50;}
    /* 讓表格標題列(Headers)自動換行，避免指標文字太長被切掉 */
    th {
        white-space: normal !important;
        min-width: 120px;
        vertical-align: top !important;
        background-color: #f0f2f6 !important;
    }
    td {text-align: center !important; vertical-align: middle !important;}
    /* 讓備註欄位靠左對齊，方便閱讀多行文字 */
    td:last-child {text-align: left !important;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄與 API 設定 ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2231/2231649.png", width=100)
    st.title("🌱 篤行幼兒園")
    st.subheader("評量整合系統 v1.5 (完整圖文版)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定，請聯絡管理員")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 評量表批次辨識", "📊 班級熱圖分析"])

# --- 3. 核心功能 (v1.5：加入表頭辨識與多行備註處理) ---

def get_gemini_model():
    """尋找最強模型 (Gemini 3/2.5 > Pro)"""
    model_list = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_list.append(m.name)
        
        # 依照強度順序尋找
        priority_keywords = ['gemini-3', 'gemini-2.5', 'pro', 'flash']
        for keyword in priority_keywords:
            for name in model_list:
                if keyword in name and '1.5' in name if keyword == 'flash' else True:
                    # Flash 必須是 1.5 以上，其他版本則抓最新
                    return genai.GenerativeModel(name), name
                    
    except Exception as e:
        st.error(f"模型偵測失敗: {e}")
    
    return genai.GenerativeModel('gemini-1.5-flash'), 'fallback-flash'

def analyze_image(image):
    model, model_name = get_gemini_model()
    
    with st.sidebar:
        st.info(f"🚀 辨識引擎：\n{model_name}")
        st.caption("⚡ 已啟用：\n1. 表頭文字提取\n2. 多行備註整合")
    
    # v1.5 Prompt：強調結構化資料與文字完整性
    prompt = """
    你是一位細心的資料輸入員。請分析這張幼兒園評量表。

    【步驟一：讀取表頭指標】
    請先讀取表格最上方、位於「幼兒姓名」與「備註」中間的那 4 個欄位標題文字（例如：「能閱讀並理解...」、「能說出連貫...」等）。
    
    【步驟二：讀取幼兒資料】
    請依序讀取每一列幼兒的資料。
    
    **關於「備註」欄位的特別指示：**
    1. 備註欄位經常包含多行文字或列點（如 ①... ②...）。
    2. 請務必將**同一個格子內的所有文字**合併成一個字串。
    3. **嚴禁**將備註裡的換行誤判為下一位幼兒。請確認該備註是屬於同一水平列的幼兒。
    4. 如果備註有分點，請保留編號（如 1. 或 ①）。

    **關於「分數」的判斷：**
    - 圈選 1 -> "A"
    - 圈選 2 -> "R"
    - 圈選 3 -> "D"
    - 圈選 4 -> "N"

    【輸出格式】
    請回傳一個包含 Metadata 和 Data 的 JSON 物件：
    {
      "headers": ["指標1的標題文字", "指標2的標題文字", "指標3的標題文字", "指標4的標題文字"],
      "students": [
        {
          "name": "幼兒一",
          "scores": ["A", "R", "A", "R"],
          "note": "備註內容(包含完整多行文字)"
        },
        ...
      ]
    }
    """
    
    config = genai.types.GenerationConfig(
        temperature=0.0, # 保持理性
        response_mime_type="application/json"
    )
    
    with st.spinner(f'🔍 AI 正在解讀表頭文字與手寫備註...'):
        try:
            response = model.generate_content([prompt, image], generation_config=config)
            data = json.loads(response.text)
            return data
        except Exception as e:
            st.error(f"AI 辨識失敗。\n錯誤訊息: {e}")
            return None

def color_grade(val):
    if val == 'A': return 'background-color: #d4edda; color: green; font-weight: bold;'
    if val == 'R': return 'background-color: #fff3cd; color: #856404; font-weight: bold;'
    if val == 'D': return 'background-color: #ffeeba; color: orange; font-weight: bold;'
    if val == 'N': return 'background-color: #f8d7da; color: red; font-weight: bold;'
    return ''

# --- 4. 主頁面邏輯 ---

if menu == "📝 評量表批次辨識":
    st.title("📝 評量表辨識 (v1.5 完整圖文版)")
    st.info("💡 此版本會自動抓取表頭的指標文字，並修正多行備註被切斷的問題。")
    
    uploaded_file = st.file_uploader("請選擇評量表照片", type=['jpg', 'png', 'jpeg', 'heic'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption='預覽照片', width=400)
        
        if st.button("🚀 開始辨識"):
            result_json = analyze_image(image)
            
            if result_json:
                # 1. 處理表頭 (Indicators)
                headers = result_json.get("headers", ["指標1", "指標2", "指標3", "指標4"])
                # 確保只有4個，避免格式跑掉
                if len(headers) < 4: headers += [f"指標{i+1}" for i in range(len(headers), 4)]
                
                # 2. 處理學生資料
                students = result_json.get("students", [])
                
                # 轉換為 DataFrame 格式
                processed_data = []
                for s in students:
                    row = {"幼兒姓名": s.get("name", "")}
                    scores = s.get("scores", [])
                    # 填入分數
                    for i, score in enumerate(scores):
                        if i < 4:
                            # 欄位名稱直接使用 AI 抓到的表頭
                            row[headers[i]] = score
                    row["備註"] = s.get("note", "")
                    processed_data.append(row)
                
                df = pd.DataFrame(processed_data)
                
                st.subheader("✅ 辨識結果")
                
                # 3. 顯示表格 (使用提取出的表頭)
                # 設定要上色的欄位 (就是那些指標欄位)
                score_cols = headers[:4]
                
                # 確保 DataFrame 裡面真的有這些欄位 (防止 AI 漏抓)
                valid_score_cols = [c for c in score_cols if c in df.columns]
                
                styler = df.style.map(color_grade, subset=valid_score_cols)
                
                edited_df = st.data_editor(
                    styler, 
                    use_container_width=True, 
                    num_rows="dynamic",
                    height=600,
                    column_config={
                        "備註": st.column_config.TextColumn(
                            "備註",
                            help="雙擊可編輯多行內容",
                            width="large" # 加寬備註欄位
                        )
                    }
                )
                
                if st.button("💾 確認並儲存"):
                    if 'class_data' not in st.session_state:
                        st.session_state['class_data'] = pd.DataFrame()
                    
                    # 儲存時，為了讓資料庫整齊，我們可能要把「落落長」的指標名稱改回 indicator_1, 2, 3, 4
                    # 或是直接存中文也可以，看您需求。這裡示範直接存中文，所見即所得。
                    save_df = edited_df.data
                    st.session_state['class_data'] = pd.concat([st.session_state['class_data'], save_df], ignore_index=True)
                    st.success(f"成功儲存！")

elif menu == "📊 班級熱圖分析":
    st.title("📊 班級學習區診斷熱圖")
    if 'class_data' in st.session_state and not st.session_state['class_data'].empty:
        df = st.session_state['class_data']
        st.dataframe(df.style.map(color_grade), use_container_width=True)
    else:
        st.warning("⚠️ 尚無資料。")
