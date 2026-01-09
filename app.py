def get_pro_model():
    # --- 設定為 Google Gemini 3.0 ---
    # 園長提醒：API 的名稱通常是小寫，且中間有短橫線
    # 這裡優先使用 'gemini-3.0-pro' (若這是最新旗艦版)
    # 備用：'gemini-3.0-flash' (若您想要速度快一點)
    
    target_model_name = 'gemini-3.0-pro' 

    try:
        # 嘗試建立 3.0 模型
        return genai.GenerativeModel(target_model_name)
    except Exception as e:
        # 如果直接呼叫失敗，嘗試加上版本號 (Google 常見的命名規則)
        try:
            return genai.GenerativeModel('gemini-3.0-pro-001')
        except:
            st.error(f"⚠️ 抓不到 {target_model_name}，系統自動切換回穩定的 Flash 版以免當機。")
            return genai.GenerativeModel('gemini-1.5-flash')
