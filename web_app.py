# web_app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
from datetime import datetime
from openai import OpenAI

# ================= 配置區 =================
# 1. Groq API Key
try:
    RAW_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    RAW_API_KEY = "gsk_你的Groq密钥" 

client = OpenAI(api_key=RAW_API_KEY.strip(), base_url="https://api.groq.com/openai/v1")
MODEL_NAME = "openai/gpt-oss-120b"

# 2. 金流付款連結
PAYMENT_LINK = "https://your-payment-link.com" 

# 3. 【付費會員名單】對應的 Email 與到期日 (YYYY-MM-DD)
PAID_USERS = {
    "boss@example.com": "2026-12-31", 
}
FREE_LIMIT = 3
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
st.divider()

# ================= 會員狀態與登入邏輯 =================
# 檢查是否已登入 (使用 Streamlit 原生 OIDC)
is_logged_in = st.user.is_logged_in if hasattr(st.user, "is_logged_in") else False
user_email = st.user.email if is_logged_in else None

# 初始化 Session State
if "usage_count" not in st.session_state:
    st.session_state.usage_count = 0
if "df" not in st.session_state:
    st.session_state.df = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_login_email" not in st.session_state:
    st.session_state.last_login_email = None

# 如果換了帳號登入，重置使用次數與資料
if is_logged_in and user_email != st.session_state.last_login_email:
    st.session_state.usage_count = 0
    st.session_state.df = None
    st.session_state.messages = []
    st.session_state.last_login_email = user_email

# 判斷是否為付費會員
is_paid = False
if is_logged_in and user_email in PAID_USERS:
    expiry = datetime.strptime(PAID_USERS[user_email], "%Y-%m-%d").date()
    if datetime.now().date() <= expiry:
        is_paid = True

has_free_quota = (not is_paid) and (st.session_state.usage_count < FREE_LIMIT)

# ================= 側邊欄 =================
with st.sidebar:
    st.header("👤 Account | 帳號")
    
    # 登入狀態
    if not is_logged_in:
        st.warning("Please login to use the service.\n請先登入以使用服務。")
        if st.button("Login with Google | Google 登入"):
            st.login("google") # 強制指定 provider 為 google
    else:
        st.success(f"Logged in as:\n**{user_email}**")
        if st.button("Logout | 登出"):
            st.logout()
            st.rerun()

    st.divider()
    
    # 訂閱狀態
    if is_paid:
        st.success("👑 **Pro Member | 專業版會員**\nUnlimited usage | 無限次數使用")
    elif is_logged_in:
        st.info(f"🎁 **Free Trial | 免費試用**\nRemaining: {max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} times\n剩餘次數：{max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} 次")
    
    st.header("📂 Upload Data | 上傳數據")
    
    # 【修復】未登入不能上傳
    if not is_logged_in:
        st.info("Please login first.\n請先登入才能上傳數據。")
        uploaded_file = None
    else:
        uploaded_file = st.file_uploader("Upload Excel or CSV", type=["xlsx", "csv"])
    
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
            st.success(f"✅ Loaded: {uploaded_file.name} ({len(df)} rows)")
        except Exception as e:
            st.error(f"Error: {e}")
            
    if st.session_state.df is not None:
        if st.button("🗑️ Clear Data | 清除數據"):
            st.session_state.df = None
            st.session_state.messages = []
            st.rerun()

    # 付費解鎖區塊
    if is_logged_in and not is_paid:
        st.divider()
        st.markdown("### 🔓 Upgrade to Pro | 升級專業版")
        st.markdown("Unlock unlimited analyses.\n解鎖無限次數分析。")
        st.link_button("💳 Pay Now | 立即付款", PAYMENT_LINK)
        st.caption("Account will be upgraded manually within 24 hrs.\n付款後 24 小時內將為您開通。")


# ================= 核心計算函數 =================
def execute_local(df, plan):
    d = df.copy()
    op = plan.get("operator")
    gb = plan.get("group_by")
    target = plan.get("target_col")
    
    if isinstance(gb, list): gb = gb[0] if len(gb) > 0 else None
    if isinstance(gb, str) and gb.strip() in ["null", "None", "無", ""]: gb = None
        
    if isinstance(target, list): target = target[0] if len(target) > 0 else None
    if isinstance(target, str) and target.strip() in ["null", "None", "無", ""]: target = None

    if not target:
        num_cols = d.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols: target = num_cols[0]
        else: return pd.DataFrame([{"提示": "找不到可計算的數值欄位"}]), None

    if target not in d.columns: raise ValueError(f"找不到欄位：{target}")

    if not gb or gb not in d.columns:
        if op in ["groupby_mean", "rank"]: return pd.DataFrame([{f"{target} 平均值": d[target].mean()}]), None
        elif op == "groupby_sum": return pd.DataFrame([{f"{target} 總和": d[target].sum()}]), None
        else: return pd.DataFrame([{f"{target} 總數": d[target].count()}]), None

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

# ================= 主畫面 =================
if not is_logged_in:
    st.info("👈 Please login using the sidebar to start.\n請先由左側選單登入以開始使用。")
else:
    if st.session_state.df is not None:
        # 顯示歷史對話
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "chart_data" in message:
                    chart_data = pd.DataFrame(message["chart_data"])
                    if message.get("x_col") and message.get("target_col"):
                        st.bar_chart(data=chart_data, x=message["x_col"], y=message["target_col"], color="#2FA572")
                if "whitebox_plan" in message:
                    with st.expander("🔍 White Box | 白箱計算依據"):
                        st.json(message["whitebox_plan"])
                        st.dataframe(pd.DataFrame(message["whitebox_df"]), use_container_width=True)

        # 阻擋邏輯
        if not is_paid and not has_free_quota:
            st.warning("⚠️ **Free trial limit reached. | 免費試用次數已達上限。**\n\nPlease upgrade to Pro to continue analyzing. | 請升級至 Pro 版本以繼續分析。")
            st.markdown(f"👈 **請在左側選單點擊付款。**\n\n[👉 Click here to Pay | 點此前往付款]({PAYMENT_LINK})")
        else:
            # 輸入框
            if question := st.chat_input("Ask a question... | 輸入您的問題"):
                if not is_paid:
                    st.session_state.usage_count += 1 
                    
                with st.chat_message("user"):
                    st.markdown(question)
                st.session_state.messages.append({"role": "user", "content": question})
                
                with st.chat_message("assistant"):
                    with st.spinner("Analyzing | 正在理解問題並計算..."):
                        try:
                            columns = list(st.session_state.df.columns)
                            prompt = f"表列名：{columns}\n用戶的問題：{question}\n請判斷要用哪種分析（groupby_mean, groupby_sum, groupby_count, trend, rank）。只返回嚴格 JSON，包含：operator, group_by, target_col, assumptions, plain_explanation。請使用繁體中文。"
                            
                            resp = client.chat.completions.create(
                                model=MODEL_NAME,
                                messages=[{"role": "user", "content": prompt}],
                                response_format={"type": "json_object"}
                            )
                            plan = json.loads(resp.choices[0].message.content)
                            result_df, x_col = execute_local(st.session_state.df, plan)
                            
                            if result_df is not None and not result_df.empty:
                                target_col = plan.get("target_col")
                                if not target_col or target_col not in result_df.columns:
                                    if len(result_df.columns) > 1: target_col = result_df.columns[-1] 
                                
                                conc_prompt = f"用戶問：{question}\n計算邏輯：{plan.get('plain_explanation', '')}\n結果數據：\n{result_df.head(10).to_string()}\n請寫出老闆能看懂的三段話，總字數不超過 150 字：發現(帶數字)、依據、建議。請使用繁體中文回答。"
                                resp2 = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "user", "content": conc_prompt}])
                                conclusion = resp2.choices[0].message.content.strip()
                                
                                st.markdown(conclusion)
                                
                                chart_data = result_df.to_dict(orient="records")
                                st.session_state.messages.append({
                                    "role": "assistant", "content": conclusion,
                                    "chart_data": chart_data, "x_col": x_col, "target_col": target_col,
                                    "whitebox_plan": plan, "whitebox_df": chart_data
                                })
                                
                                if x_col and target_col and target_col in result_df.columns:
                                    st.bar_chart(data=result_df, x=x_col, y=target_col, color="#2FA572")
                                
                                with st.expander("🔍 White Box | 白箱計算依據"):
                                    st.json(plan)
                                    st.dataframe(result_df, use_container_width=True)
                            else:
                                st.error("無法生成結果")
                        except Exception as e:
                            st.error(f"Error: {e}")
    else:
        st.info("👈 Please upload a file to start | 請先在左側上傳檔案開始分析。")
##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
