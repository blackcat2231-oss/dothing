import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json

# --- 1. 網頁基本設定 ---
st.set_page_config(page_title="篤行幼兒園評量系統", layout="wide", page_icon="🌱")

# 自訂 CSS
st.markdown("""
    <style>
    .main {background-color: #f9f9f9;}
    .stHeader {color: #2c3e50;}
    .reportview-container .main .block-container{padding-top: 2rem;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄與 API 設定 ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2231/2231649.png", width=100)
    st.title("🌱 篤行幼兒園")
    st.subheader("評量整合系統 v1.1")
    
    # API Key 檢查
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定，請聯絡管理員")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 評量表批次辨識", "📊 班級熱圖分析", "👶 個人成長報告(開發中)"])

# --- 3. 核心功能函式 (新增：自動尋找正確模型) ---

def get_gemini_model():
    """自動從 Google 帳號中尋找可用的 Flash 模型，避免名稱錯誤"""
    try:
        # 先列出所有可用模型
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # 優先尋找名字裡有 flash 的模型
                if 'flash' in m.name:
                    return genai.GenerativeModel(m.name)
        
        # 如果沒找到 flash，就用第一個可用的模型 (例如 pro)
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                return genai.GenerativeModel(m.name)
                
    except Exception as e:
        st.error(f"模型偵測失敗: {e}")
    
    # 萬一真的都失敗，才用預設值
    return genai.GenerativeModel('gemini-1.5-flash')

def analyze_image(image):
    """呼叫 AI 辨識圖片中的表格數據"""
    
    # 改用自動偵測的模型，不再寫死名字
    model = get_gemini_model()
    
    # 這是給 AI 的精確指令
    prompt = """
    你是一位專業的資料輸入員。請辨識這張幼兒園評量表的圖片。
    
    【任務目標】
    請提取表格中每一位幼兒的「指標得分」與「備註」。
    表格中的分數通常是圈選的數字：1, 2, 3, 4。
    請依據以下規則轉換分數：
    - 圈選 1 -> 轉換為 "A"
    - 圈選 2 -> 轉換為 "R"
    - 圈選 3 -> 轉換為 "D"
    - 圈選 4 -> 轉換為 "N"
    
    【輸出格式】
    請務必只回傳純粹的 JSON 格式字串，不要有 markdown 標記（不要用 ```json ... ``` 包裹），格式如下：
    [
      {"name": "幼兒姓名", "indicator_1": "A", "indicator_2": "R", "note": "備註內容"},
      {"name": "...", ...}
    ]
    
    如果某個欄位無法辨識，請填入 null。
    """
    
    with st.spinner('🤖 AI 正在用力閱讀老師的手寫字...'):
        try:
            response = model.generate_content([prompt, image])
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_text)
            return data
        except Exception as e:
            st.error(f"AI 辨識失敗，請重試或檢查圖片清晰度。\n錯誤訊息: {e}")
            return []

def color_grade(val):
    """熱圖的顏色設定"""
    if val == 'A': return 'background-color: #d4edda; color: green'
    if val == 'R': return 'background-color: #fff3cd; color: #856404'
    if val == 'D': return 'background-color: #ffeeba; color: orange'
    if val == 'N': return 'background-color: #f8d7da; color: red'
    return ''

# --- 4. 主頁面邏輯 ---

if menu == "📝 評量表批次辨識":
    st.title("📝 學習區評量表上傳")
    st.info("💡 支援手機拍照上傳，AI 會自動辨識手寫圈選的分數 (1,2,3,4) 並轉換為 (A,R,D,N)。")
    
    uploaded_file = st.file_uploader("請選擇評量表照片", type=['jpg', 'png', 'jpeg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption='預覽照片', width=400)
        
        if st.button("🚀 開始智慧辨識"):
            result_data = analyze_image(image)
            
            if result_data:
                df = pd.DataFrame(result_data)
                st.subheader("✅ 辨識結果 (可直接點擊修改)")
                edited_df = st.data_editor(df, use_container_width=True)
                
                if st.button("💾 確認並儲存資料"):
                    if 'class_data' not in st.session_state:
                        st.session_state['class_data'] = pd.DataFrame()
                    st.session_state['class_data'] = pd.concat([st.session_state['class_data'], edited_df], ignore_index=True)
                    st.success(f"已成功儲存 {len(edited_df)} 筆幼兒資料！請前往「班級熱圖分析」查看。")

elif menu == "📊 班級熱圖分析":
    st.title("📊 班級學習區診斷熱圖")
    
    if 'class_data' in st.session_state and not st.session_state['class_data'].empty:
        df = st.session_state['class_data']
        
        col1, col2, col3 = st.columns(3)
        col1.metric("已登錄幼兒數", len(df))
        col2.metric("主要學習區", "語文區")
        col3.metric("待加強 (N) 總數", int((df == 'N').sum().sum()))

        st.markdown("### 🚦 分數分佈熱圖")
        styler = df.style.map(color_grade)
        st.dataframe(styler, use_container_width=True)
        
        if st.button("🤖 請 AI 分析全班狀況"):
            with st.spinner("AI 正在分析全班資料..."):
                n_count = (df == 'N').sum().sum()
                if n_count > 3:
                    st.warning(f"分析：本班在特定指標上有 {n_count} 個「需協助」，建議加強引導故事敘說的活動。")
                else:
                    st.success("分析：全班整體表現良好，大部份幼兒都能掌握核心能力！")
    else:
        st.warning("⚠️ 目前還沒有資料喔！請先去「評量表批次辨識」頁面上傳照片。")

elif menu == "👶 個人成長報告(開發中)":
    st.title("👶 綜合成長故事")
    st.info("🚧 此功能建置中...")
