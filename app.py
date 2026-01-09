import streamlit as st
import google.generativeai as genai
from PIL import Image
import os

# 1. 網頁設定
st.set_page_config(page_title="篤行幼兒園評量系統", layout="wide")

st.title("🌱 篤行幼兒園 - 學習評量 AI 助手")
st.markdown("---")

# 2. 設定 API Key (從 Streamlit 的秘密金鑰中讀取)
# 這裡會自動讀取您在後台設定的密碼，不需要寫在程式碼裡
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("尚未設定 API Key，請通知管理員。")
    st.stop()

# 3. 側邊欄：功能選單
with st.sidebar:
    st.header("功能模組")
    function_mode = st.selectbox(
        "選擇功能",
        ["學習區照片上傳測試", "分區診斷熱圖 (開發中)", "綜合成長故事 (開發中)"]
    )

# 4. 主畫面邏輯
if function_mode == "學習區照片上傳測試":
    st.subheader("📸 評量表照片辨識測試")
    st.info("請上傳一張評量表照片，AI 將嘗試讀取其中的內容。")
    
    # 檔案上傳器
    uploaded_file = st.file_uploader("請選擇照片 (JPG/PNG)", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        # 顯示圖片
        image = Image.open(uploaded_file)
        st.image(image, caption="您上傳的照片", use_container_width=True)
        
        if st.button("開始 AI 分析"):
            with st.spinner("AI 正在努力閱讀老師的手寫字..."):
                try:
                    # 呼叫 Gemini 1.5 Flash (速度快、便宜)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # 這是給 AI 的指令 (Prompt)
                    prompt = """
                    你是一個幼兒教育專家與資料輸入員。
                    請分析這張評量表圖片，告訴我以下資訊：
                    1. 這看起來是哪個學習區的表格？
                    2. 你看到了哪些評量指標文字？
                    3. 請嘗試讀取上面的手寫分數 (A/R/D/N) 或備註。
                    請用繁體中文回答。
                    """
                    
                    response = model.generate_content([prompt, image])
                    st.success("分析完成！")
                    st.write(response.text)
                    
                except Exception as e:
                    st.error(f"發生錯誤：{e}")
