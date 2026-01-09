import streamlit as st
import google.generativeai as genai
from PIL import Image

st.set_page_config(page_title="系統診斷模式", layout="wide")
st.title("🏥 系統診斷模式 (連線至 dothing)")

# 顯示目前版本
try:
    sdk_version = genai.__version__
except:
    sdk_version = "未知"

st.warning(f"📊 目前軟體版本: {sdk_version}")
st.info("目標版本應該要是 0.8.3 或更高")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    st.success("API Key 設定成功")
else:
    st.error("尚未設定 API Key")

uploaded_file = st.file_uploader("上傳照片測試", type=["jpg", "png"])
if uploaded_file and st.button("開始測試"):
    image = Image.open(uploaded_file)
    st.image(image, width=300)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(["讀取這張圖", image])
        st.write(response.text)
    except Exception as e:
        st.error(f"錯誤: {e}")
