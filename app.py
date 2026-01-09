import streamlit as st
import google.generativeai as genai
from PIL import Image

st.set_page_config(page_title="模型偵測模式", layout="wide")
st.title("🧪 模型偵測與測試")

# 1. 設定 API Key
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("❌ 尚未設定 API Key")
    st.stop()

# 2. 自動詢問 Google 有哪些模型可用
st.subheader("步驟一：偵測可用模型")
available_models = []
try:
    # 嘗試列出所有支援「內容生成」的模型
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
except Exception as e:
    st.error(f"無法連線至 Google 查詢模型清單: {e}")

# 3. 顯示下拉選單讓您選擇
if available_models:
    st.success(f"🎉 成功連線！您的帳號可以使用以下 {len(available_models)} 種模型：")
    
    # 預設嘗試幫您選一個有 flash 的，如果沒有就選第一個
    default_index = 0
    for i, name in enumerate(available_models):
        if "flash" in name:
            default_index = i
            break
            
    selected_model_name = st.selectbox(
        "請從清單中選擇一個模型來測試：", 
        available_models, 
        index=default_index
    )
    st.info(f"您目前選擇的是：{selected_model_name}")
else:
    st.error("⚠️ 偵測不到任何可用模型。這通常代表 API Key 的專案沒有啟用 'Generative Language API'，或是帳號權限受限。")
    selected_model_name = None

# 4. 上傳與測試
st.markdown("---")
st.subheader("步驟二：測試照片")
uploaded_file = st.file_uploader("上傳照片測試", type=["jpg", "png", "jpeg"])

if uploaded_file and selected_model_name and st.button("開始測試"):
    image = Image.open(uploaded_file)
    st.image(image, width=300, caption="測試圖片")
    
    with st.spinner(f"正在使用 {selected_model_name} 讀取..."):
        try:
            model = genai.GenerativeModel(selected_model_name)
            response = model.generate_content(["請告訴我這張圖片裡有什麼？(請用繁體中文回答)", image])
            st.success("測試成功！")
            st.markdown("### AI 回答：")
            st.write(response.text)
        except Exception as e:
            st.error(f"測試失敗: {e}")
