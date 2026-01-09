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
    .stDataFrame {font-size: 1.1rem;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄與 API 設定 ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2231/2231649.png", width=100)
    st.title("🌱 篤行幼兒園")
    st.subheader("評量整合系統 v1.3 (Gemini 3 Ready)")
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        st.success("API 連線狀態：🟢 線上")
    else:
        st.error("API Key 未設定，請聯絡管理員")
        st.stop()
        
    st.markdown("---")
    menu = st.radio("功能選單", ["📝 評量表批次辨識", "📊 班級熱圖分析", "👶 個人成長報告(開發中)"])

# --- 3. 核心功能函式 (升級：優先尋找 Gemini 3) ---

def get_gemini_model():
    """
    智慧型模型選擇器：
    會自動依照「新 -> 舊」的順序，尋找您帳號可用的最強模型。
    優先順序：Gemini 3 -> Gemini 2.5 -> Gemini 2.0 -> Gemini 1.5
    """
    model_list = []
    try:
        # 1. 取得所有可用模型
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_list.append(m.name)
        
        # 2. 依序過濾最強模型
        # Priority 1: Gemini 3 (最新最強)
        for name in model_list:
            if 'gemini-3' in name:
                return genai.GenerativeModel(name), name
        
        # Priority 2: Gemini 2.5 (目前的穩定主流)
        for name in model_list:
            if 'gemini-2.5' in name:
                return genai.GenerativeModel(name), name

        # Priority 3: Gemini 2.0 (上一代高效能)
        for name in model_list:
            if 'gemini-2.0' in name:
                return genai.GenerativeModel(name), name
        
        # Priority 4: Gemini 1.5 Pro (經典款)
        for name in model_list:
            if 'pro' in name and '1.5' in name:
                return genai.GenerativeModel(name), name

        # Priority 5: Gemini 1.5 Flash (保底款)
        for name in model_list:
            if 'flash' in name and '1.5' in name:
                return genai.GenerativeModel(name), name
             
    except Exception as e:
        st.error(f"模型偵測失敗: {e}")
    
    # 萬一真的什麼都沒抓到，回傳一個預設值避免當機
    return genai.GenerativeModel('gemini-1.5-flash'), 'fallback-flash'

def analyze_image(image):
    """呼叫 AI 辨識圖片中的表格數據"""
    
    # 取得目前最強的模型
    model, model_name = get_gemini_model()
    
    with st.sidebar:
        st.info(f"🚀 目前使用引擎：\n{model_name}")
        if "gemini-3" in model_name:
            st.caption("✨ 已啟用 Gemini 3 最新推理引擎")
    
    prompt = """
    你是一位專業的幼兒園資料輸入員。請分析這張評量表圖片。
    
    【任務目標】
    提取表格中每一位幼兒的「指標得分」與「備註」。
    
    【關鍵辨識規則】
    1. **分數形式**：分數是老師用筆「圈起來」的數字 (1, 2, 3, 或 4)。
    2. **抗干擾**：請專注辨識圓圈「裡面」的數字，不要把圓圈的筆跡誤認為數字的一部分（例如不要把圈起來的4看成D）。
    3. **數值轉換**：
       - 圈選 1 -> 輸出 "A"
       - 圈選 2 -> 輸出 "R"
       - 圈選 3 -> 輸出 "D"
       - 圈選 4 -> 輸出 "N"
    
    【輸出格式】
    請務必只回傳純粹的 JSON 格式字串列表，嚴禁 markdown 標記，格式如下：
    [
      {"name": "幼兒姓名", "indicator_1": "A", "indicator_2": "R", "indicator_3": "D", "indicator_4": "N", "note": "備註內容"},
      {"name": "...", ...}
    ]
    """
    
    with st.spinner(f'🤖 AI ({model_name}) 正在進行深度辨識...'):
        try:
            # Gemini 3 建議使用 temperature=1.0 或預設值
            response = model.generate_content([prompt, image])
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_text)
            return data
        except Exception as e:
            st.error(f"AI 辨識失敗。\n錯誤訊息: {e}")
            return []

def color_grade(val):
    if val == 'A': return 'background-color: #d4edda; color: green; font-weight: bold;'
    if val == 'R': return 'background-color: #fff3cd; color: #856404; font-weight: bold;'
    if val == 'D': return 'background-color: #ffeeba; color: orange; font-weight: bold;'
    if val == 'N': return 'background-color: #f8d7da; color: red; font-weight: bold;'
    return ''

# --- 4. 主頁面邏輯 ---

if menu == "📝 評量表批次辨識":
    st.title("📝 學習區評量表上傳 (v1.3)")
    st.info("💡 系統會自動搜尋您帳號內最強的 AI 模型 (Gemini 3/2.5) 進行辨識。")
    
    uploaded_file = st.file_uploader("請選擇評量表照片", type=['jpg', 'png', 'jpeg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption='預覽照片', width=400)
        
        if st.button("🚀 開始智慧辨識"):
            result_data = analyze_image(image)
            
            if result_data:
                df = pd.DataFrame(result_data)
                st.subheader("✅ 辨識結果")
                
                # 若資料欄位不足4個，自動補齊以避免報錯
                for col in ['indicator_1', 'indicator_2', 'indicator_3', 'indicator_4']:
                    if col not in df.columns:
                        df[col] = None

                styler = df.style.map(color_grade, subset=['indicator_1', 'indicator_2', 'indicator_3', 'indicator_4'])
                edited_df = st.data_editor(styler, use_container_width=True, num_rows="dynamic")
                
                if st.button("💾 確認並儲存資料"):
                    if 'class_data' not in st.session_state:
                        st.session_state['class_data'] = pd.DataFrame()
                    clean_df = edited_df.data
                    st.session_state['class_data'] = pd.concat([st.session_state['class_data'], clean_df], ignore_index=True)
                    st.success(f"已成功儲存 {len(clean_df)} 筆幼兒資料！")

elif menu == "📊 班級熱圖分析":
    st.title("📊 班級學習區診斷熱圖")
    if 'class_data' in st.session_state and not st.session_state['class_data'].empty:
        df = st.session_state['class_data']
        # (保持原有的熱圖邏輯)
        score_cols = [c for c in df.columns if 'indicator' in c]
        styler = df.style.map(color_grade, subset=score_cols)
        st.dataframe(styler, use_container_width=True)
    else:
        st.warning("⚠️ 目前還沒有資料喔！")

elif menu == "👶 個人成長報告(開發中)":
    st.title("👶 綜合成長故事")
    st.info("🚧 此功能建置中...")
