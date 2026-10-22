# web_app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from openai import OpenAI

# ================= 配置區 =================
try:
    RAW_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    RAW_API_KEY = "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" # 本地測試用

GROQ_API_KEY = RAW_API_KEY.encode("ascii", errors="ignore").decode("ascii").strip()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)
MODEL_NAME = "openai/gpt-oss-120b"

# 【商業設定】付款連結
PAYMENT_LINK = "https://your-payment-link.com" 

# 【商業設定】授權碼與對應的到期日 (YYYY-MM-DD)
# 未來客戶付款後，你可以手動在這裡新增一組，或者用腳本自動生成
VALID_LICENSES = {
    "PRO-TRIAL-7DAY": "2026-11-01", # 測試用：7天試用
    "PRO-MONTH-2026": "2026-12-31", # 測試用：一個月
    "VIP-DATA-2026": "2027-01-01"
}
# ==========================================

st.set_page_config(page_title="Data Analyzer | 智能數據分析", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    .stApp { max-width: 1100px; margin: 0 auto; }
    .stButton>button { width: 100%; border-radius: 8px; height: 50px; font-weight: bold; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("📊 Data Analyzer | 智能數據分析工具")
st.markdown("🔒 **Local Computing · Data Privacy Guaranteed** | **本地端計算 · 數據絕對安全**")
st.markdown("*No raw data is sent to the cloud. | 原始數據不會上傳至雲端。*")
st.divider()

# 初始化狀態
if "df" not in st.session_state:
    st.session_state.df = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "usage_count" not in st.session_state:
    st.session_state.usage_count = 0
if "is_pro" not in st.session_state:
    st.session_state.is_pro = False
if "expiry_date" not in st.session_state:
    st.session_state.expiry_date = None

FREE_LIMIT = 3

# 檢查訂閱是否過期
def check_subscription():
    if st.session_state.is_pro and st.session_state.expiry_date:
        today = datetime.now().date()
        expiry = datetime.strptime(st.session_state.expiry_date, "%Y-%m-%d").date()
        if today > expiry:
            st.session_state.is_pro = False
            st.session_state.expiry_date = None
            return False
    return st.session_state.is_pro

is_subscribed = check_subscription()

# 側邊欄 (包含上傳與訂閱)
with st.sidebar:
    st.header("1. Upload Data | 上傳數據")
    
    # 【訂閱狀態顯示】
    if is_subscribed:
        st.success(f"👑 **Pro Member | 專業版會員**\nValid until | 到期日：{st.session_state.expiry_date}\nUnlimited usage | 無限次數")
    else:
        st.info(f"🎁 **Free Trial | 免費試用**\nRemaining: {max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} times\n剩餘次數：{max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} 次")
    
    uploaded_file = st.file_uploader("Upload Excel or CSV | 選擇 Excel 或 CSV", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                try:
                    df = pd.read_csv(uploaded_file, encoding='utf-8')
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='big5')
            
            df.columns = df.columns.str.strip()
            st.session_state.df = df
            st.success(f"✅ Loaded | 已載入：{uploaded_file.name} ({len(df)} rows)")
            
            with st.expander("Preview Data | 預覽數據"):
                st.dataframe(df.head(), use_container_width=True)
        except Exception as e:
            st.error(f"Error | 讀取失敗：{e}")
            
    if st.session_state.df is not None:
        if st.button("🗑️ Clear Data | 清除數據"):
            st.session_state.df = None
            st.session_state.messages = []
            st.session_state.usage_count = 0
            st.rerun()

    st.divider()
    
    # 【付費解鎖區塊】
    if not is_subscribed:
        st.markdown("### 🔓 Upgrade to Pro | 升級專業版")
        st.markdown("Unlock unlimited analyses.\n解鎖無限次數分析。")
        st.link_button("💳 Pay Now | 立即付款", PAYMENT_LINK)
        
        license_input = st.text_input("Enter License Key | 輸入授權碼", type="password")
        if st.button("Activate | 啟用"):
            key = license_input.strip()
            if key in VALID_LICENSES:
                expiry_str = VALID_LICENSES[key]
                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                if expiry_date >= datetime.now().date():
                    st.session_state.is_pro = True
                    st.session_state.expiry_date = expiry_str
                    st.success("✅ Activated! | 啟用成功！")
                    st.rerun()
                else:
                    st.error("❌ Key Expired | 此授權碼已過期，請續費。")
            else:
                st.error("❌ Invalid Key | 授權碼錯誤")


# 核心計算函數 (泛用防呆版)
def execute_local(df, plan):
    d = df.copy()
    op = plan.get("operator")
    gb = plan.get("group_by")
    target = plan.get("target_col")
    
    if isinstance(gb, list): gb = gb[0] if len(gb) > 0 else None
    if isinstance(gb, str):
        gb = gb.strip()
        if gb in ["null", "None", "無", ""]: gb = None
        
    if isinstance(target, list): target = target[0] if len(target) > 0 else None
    if isinstance(target, str):
        target = target.strip()
        if target in ["null", "None", "無", ""]: target = None

    if not target:
        num_cols = d.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols: target = num_cols[0]
        else: return pd.DataFrame([{"提示": "找不到可計算的數值欄位"}]), None

    if target not in d.columns:
        raise ValueError(f"找不到欄位：{target}")

    if not gb or gb not in d.columns:
        if op in ["groupby_mean", "rank"]:
            return pd.DataFrame([{f"{target} 平均值": d[target].mean()}]), None
        elif op == "groupby_sum":
            return pd.DataFrame([{f"{target} 總和": d[target].sum()}]), None
        else:
            return pd.DataFrame([{f"{target} 總數": d[target].count()}]), None

    if op == "groupby_mean":
        agg = d.groupby(gb)[target].mean().reset_index()
        return agg.sort_values(by=target, ascending=False).head(10), gb
    elif op == "groupby_sum":
        agg = d.groupby(gb)[target].sum().reset_index()
        return agg.sort_values(by=target, ascending=False).head(10), gb
    elif op == "groupby_count":
        agg = d.groupby(gb)[target].count().reset_index()
        return agg.sort_values(by=target, ascending=False).head(10), gb
    elif op == "rank":
        agg = d.groupby(gb)[target].mean().reset_index()
        return agg.sort_values(by=target, ascending=False).head(10), gb
    else:
        return d.head(10), None

# 主畫面
if st.session_state.df is not None:
    # 顯示歷史對話
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            if "chart_data" in message:
                chart_data = pd.DataFrame(message["chart_data"])
                if message.get("x_col") and message.get("target_col"):
                    st.bar_chart(data=chart_data, x=message["x_col"], y=message["target_col"], color="#2FA572")
            
            if "whitebox_plan" in message and "whitebox_df" in message:
                with st.expander("🔍 White Box | 白箱計算依據"):
                    st.markdown("**第一步：AI 分析計畫**")
                    st.json(message["whitebox_plan"])
                    st.markdown("**第二步：本地端執行計算**")
                    st.dataframe(pd.DataFrame(message["whitebox_df"]), use_container_width=True)

    # 【付費阻擋邏輯】
    if not is_subscribed and st.session_state.usage_count >= FREE_LIMIT:
        st.warning("⚠️ **Free trial limit reached. | 免費試用次數已達上限。**\n\nPlease upgrade to Pro to continue analyzing. | 請升級至 Pro 版本以繼續分析。")
        st.markdown(f"👈 **請在左側選單付款並輸入授權碼解鎖。**\n\n[👉 Click here to Pay | 點此前往付款]({PAYMENT_LINK})")
    else:
        # 輸入框
        if question := st.chat_input("Ask a question... | 輸入您的問題"):
            # 如果不是 Pro，才增加次數
            if not is_subscribed:
                st.session_state.usage_count += 1 
                
            with st.chat_message("user"):
                st.markdown(question)
            st.session_state.messages.append({"role": "user", "content": question})
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing | 正在理解問題並計算..."):
                    try:
                        columns = list(st.session_state.df.columns)
                        
                        prompt_part1 = "表列名：" + str(columns) + "\n"
                        prompt_part2 = "用戶的問題：" + question + "\n"
                        prompt_part3 = "請判斷要用哪種分析。只能選這五個英文單字之一：groupby_mean (分組算平均), groupby_sum (分組加總), groupby_count (分組算數量), trend (看時間趨勢), rank (排名)。\n"
                        prompt_part4 = '只返回嚴格的 JSON 格式，包含欄位：operator, group_by, target_col (要計算的數值欄位), assumptions, plain_explanation。請全部使用繁體中文填寫解釋部分。'
                        
                        full_prompt = prompt_part1 + prompt_part2 + prompt_part3 + prompt_part4
                        
                        resp = client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=[{"role": "user", "content": full_prompt}],
                            response_format={"type": "json_object"}
                        )
                        plan = json.loads(resp.choices[0].message.content)

                        result_df, x_col = execute_local(st.session_state.df, plan)
                        
                        if result_df is not None and not result_df.empty:
                            target_col = plan.get("target_col")
                            if not target_col or target_col not in result_df.columns:
                                if len(result_df.columns) > 1:
                                    target_col = result_df.columns[-1] 
                            
                            conc_part1 = "用戶問：" + question + "\n"
                            conc_part2 = "計算邏輯：" + str(plan.get('plain_explanation', '')) + "\n"
                            conc_part3 = "結果數據：\n" + result_df.head(10).to_string() + "\n"
                            conc_part4 = "請寫出老闆能看懂的三段話，總字數不超過 150 字：發現(帶數字)、依據、建議。請使用繁體中文回答。"
                            
                            full_conc_prompt = conc_part1 + conc_part2 + conc_part3 + conc_part4
                            
                            resp2 = client.chat.completions.create(
                                model=MODEL_NAME,
                                messages=[{"role": "user", "content": full_conc_prompt}]
                            )
                            conclusion = resp2.choices[0].message.content.strip()
                            
                            st.markdown(conclusion)
                            
                            chart_data = result_df.to_dict(orient="records")
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": conclusion,
                                "chart_data": chart_data,
                                "x_col": x_col,
                                "target_col": target_col,
                                "whitebox_plan": plan,
                                "whitebox_df": chart_data
                            })
                            
                            if x_col and target_col and target_col in result_df.columns:
                                st.bar_chart(data=result_df, x=x_col, y=target_col, color="#2FA572")
                            
                            with st.expander("🔍 White Box | 白箱計算依據", expanded=False):
                                st.markdown("**第一步：AI 分析計畫**")
                                st.json(plan)
                                st.markdown("**第二步：本地端執行計算**")
                                st.dataframe(result_df, use_container_width=True)
                        else:
                            st.error("No results generated | 無法生成結果")
                    except Exception as e:
                        st.error(f"Error: {e}")
else:
    st.info("👈 Please upload a file to start | 請先在左側上傳檔案開始分析。")
##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
