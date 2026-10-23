# web_app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import uuid
from datetime import datetime
from openai import OpenAI

# ================= 配置區 =================
try:
    RAW_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    RAW_API_KEY = "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" # 本地測試用

client = OpenAI(api_key=RAW_API_KEY.strip(), base_url="https://api.groq.com/openai/v1")
MODEL_NAME = "openai/gpt-oss-120b"

PAYMENT_LINK = "https://your-payment-link.com" 

# 付費會員名單
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
st.markdown("🚀 **New: Predictive Trend & Anomaly Detection** | **全新：趨勢預測與異常檢測**")
st.divider()

# ================= 核心狀態管理 =================
@st.cache_resource
def get_global_tracker():
    return {}

tracker = get_global_tracker()

is_logged_in = st.user.is_logged_in if hasattr(st.user, "is_logged_in") else False
user_email = st.user.email if is_logged_in else None

if "browser_id" not in st.session_state:
    st.session_state.browser_id = str(uuid.uuid4())

tracker_key = user_email if is_logged_in else st.session_state.browser_id

if tracker_key not in tracker:
    tracker[tracker_key] = 0

usage_count = tracker[tracker_key]

is_paid = False
if is_logged_in and user_email in PAID_USERS:
    expiry = datetime.strptime(PAID_USERS[user_email], "%Y-%m-%d").date()
    if datetime.now().date() <= expiry:
        is_paid = True

has_free_quota = is_paid or (usage_count < FREE_LIMIT)

if "df" not in st.session_state:
    st.session_state.df = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# ================= 側邊欄 =================
with st.sidebar:
    st.header("👤 Account | 帳號")
    
    if not is_logged_in:
        st.info(f"🎁 **Free Trial | 免費試用**\nRemaining: {max(0, FREE_LIMIT - usage_count)} / {FREE_LIMIT} times\n剩餘次數：{max(0, FREE_LIMIT - usage_count)} / {FREE_LIMIT} 次")
        if st.button("Login with Google | Google 登入"):
            st.login("google")
    else:
        st.success(f"Logged in as:\n**{user_email}**")
        if st.button("Logout | 登出"):
            st.logout()
            st.session_state.browser_id = str(uuid.uuid4()) # 登出後換新 ID
            st.rerun()
            
        if is_paid:
            st.success("👑 **Pro Member | 專業版會員**\nUnlimited usage | 無限次數使用")
        else:
            st.warning("⚠️ **Account not activated. | 帳號尚未開通。**\nPlease upgrade. | 請升級以繼續使用。")

    st.divider()
    
    # 上傳數據區
    st.header("📂 Upload Data | 上傳數據")
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
            st.success(f"✅ Loaded: {uploaded_file.name}")
            
            # 【恢復預覽功能】
            st.markdown(f"**Data Dimensions | 數據維度：** `{len(df)} rows` × `{len(df.columns)} columns`")
            with st.expander("🔍 Preview Data | 預覽數據 (前 5 行)"):
                st.dataframe(df.head(), use_container_width=True)
                
        except Exception as e:
            st.error(f"Error: {e}")
            
    if st.session_state.df is not None:
        if st.button("🗑️ Clear Data | 清除數據"):
            st.session_state.df = None
            st.session_state.messages = []
            st.rerun()

    if is_logged_in and not is_paid:
        st.divider()
        st.markdown("### 🔓 Upgrade to Pro | 升級專業版")
        st.link_button("💳 Pay Now | 立即付款", PAYMENT_LINK)


# ================= 升級版核心計算引擎 =================
def execute_local(df, plan):
    d = df.copy()
    op = plan.get("operator")
    gb = plan.get("group_by")
    target = plan.get("target_col")
    
    # 處理 AI 回傳格式
    if isinstance(gb, list): gb = gb[0] if len(gb) > 0 else None
    if isinstance(gb, str) and gb.strip() in ["null", "None", "無", ""]: gb = None
    if isinstance(target, list): target = target[0] if len(target) > 0 else None
    if isinstance(target, str) and target.strip() in ["null", "None", "無", ""]: target = None

    if not target:
        num_cols = d.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols: target = num_cols[0]
        else: return pd.DataFrame([{"提示": "找不到可計算的數值欄位 (No numerical column found)"}]), None

    if target not in d.columns: raise ValueError(f"找不到欄位：{target}")
    
    # 確保目標欄位是數字
    d[target] = pd.to_numeric(d[target], errors='coerce').fillna(0)

    # 1. 趨勢分析 (Trend)
    if op == "trend":
        time_col = next((c for c in d.columns if 'date' in str(c).lower() or '日期' in str(c) or '時間' in str(c)), None)
        if time_col:
            d[time_col] = pd.to_datetime(d[time_col], errors='coerce')
            d['_month'] = d[time_col].dt.to_period('M').astype(str)
            agg = d.groupby('_month')[target].agg(['sum', 'mean', 'count']).reset_index()
            agg.columns = ['_month', f'{target}_sum', f'{target}_mean', f'{target}_count']
            return agg, "_month"
        else:
            return pd.DataFrame([{"提示": "找不到時間/日期欄位，無法進行趨勢分析"}]), None

    # 2. 佔比拆解 (Ratio)
    elif op == "groupby_ratio" and gb and gb in d.columns:
        agg = d.groupby(gb)[target].sum().reset_index()
        total = agg[target].sum()
        agg[f'{target}_ratio'] = (agg[target] / total * 100).round(2).astype(str) + '%'
        return agg.sort_values(by=target, ascending=False).head(10), gb

    # 3. 異常檢測 (Anomaly)
    elif op == "anomaly" and gb and gb in d.columns:
        # 計算該組的總和，並找出大於「平均值 + 2個標準差」的極端值
        agg = d.groupby(gb)[target].sum().reset_index()
        mean_val = agg[target].mean()
        std_val = agg[target].std()
        threshold = mean_val + (2 * std_val)
        
        anomalies = agg[agg[target] > threshold].sort_values(by=target, ascending=False).head(10)
        if anomalies.empty:
            return pd.DataFrame([{"提示": "未檢測到明顯異常值"}]), gb
        return anomalies, gb

    # 4. 一般分組 (Mean / Sum / Count / Rank)
    elif op in ["groupby_mean", "groupby_sum", "groupby_count", "rank"] and gb and gb in d.columns:
        if op == "groupby_mean" or op == "rank":
            agg = d.groupby(gb)[target].mean().reset_index()
        elif op == "groupby_sum":
            agg = d.groupby(gb)[target].sum().reset_index()
        else:
            agg = d.groupby(gb)[target].count().reset_index()
        return agg.sort_values(by=target, ascending=False).head(10), gb
        
    else:
        # 如果沒分組，回傳整體總計
        if op == "groupby_sum": return pd.DataFrame([{f"{target} 總和": d[target].sum()}]), None
        else: return pd.DataFrame([{f"{target} 平均值": d[target].mean()}]), None

# ================= 主畫面 =================
if st.session_state.df is not None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_data" in message:
                chart_data = pd.DataFrame(message["chart_data"])
                if message.get("x_col") and message.get("target_col"):
                    # 趨勢圖用折線圖，一般分組用柱狀圖
                    if message.get("op") == "trend":
                        st.line_chart(data=chart_data, x=message["x_col"], y=message["target_col"], color="#FF4B4B")
                    else:
                        st.bar_chart(data=chart_data, x=message["x_col"], y=message["target_col"], color="#2FA572")
            if "whitebox_plan" in message:
                with st.expander("🔍 White Box | 白箱計算依據"):
                    st.json(message["whitebox_plan"])
                    st.dataframe(pd.DataFrame(message["whitebox_df"]), use_container_width=True)

    if not has_free_quota:
        st.warning("⚠️ **Free trial limit reached. | 免費試用次數已達上限。**")
        if not is_logged_in:
            st.markdown("👉 **Please login using the sidebar to upgrade. | 請由左側選單登入以升級為專業版。**")
        else:
            st.markdown(f"👉 **Please upgrade to Pro to continue analyzing. | 請升級為專業版以繼續分析。**\n\n[👉 Click here to Pay | 點此前往付款]({PAYMENT_LINK})")
            
    else:
        if question := st.chat_input("Ask a question... | 輸入您的問題（例如：預測下個月的趨勢）"):
            if not is_paid:
                tracker[tracker_key] += 1
                
            with st.chat_message("user"):
                st.markdown(question)
            st.session_state.messages.append({"role": "user", "content": question})
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing | 正在深度分析與計算..."):
                    try:
                        columns = list(st.session_state.df.columns)
                        # 升級版 Prompt：加入新的算子
                        prompt = f"""表列名：{columns}
用戶的問題：{question}
請判斷要用哪種分析。只能選這六個英文單字之一：
- groupby_mean (分組算平均)
- groupby_sum (分組加總)
- groupby_ratio (分組算佔比)
- groupby_count (分組算數量)
- trend (時間趨勢分析)
- anomaly (異常值檢測)
只返回嚴格 JSON，包含：operator, group_by, target_col, assumptions, plain_explanation。請使用繁體中文。"""

                        # 加入自動重試機制
                        for _ in range(2):
                            try:
                                resp = client.chat.completions.create(
                                    model=MODEL_NAME,
                                    messages=[{"role": "user", "content": prompt}],
                                    response_format={"type": "json_object"}
                                )
                                plan = json.loads(resp.choices[0].message.content)
                                break
                            except Exception as e:
                                if _ == 1: raise e

                        result_df, x_col = execute_local(st.session_state.df, plan)
                        
                        if result_df is not None and not result_df.empty:
                            target_col = plan.get("target_col")
                            # 處理圖表 Y 軸對應的欄位名稱
                            y_col_for_chart = target_col
                            if f'{target_col}_sum' in result_df.columns: y_col_for_chart = f'{target_col}_sum'
                            elif f'{target_col}_mean' in result_df.columns: y_col_for_chart = f'{target_col}_mean'
                            elif f'{target_col}_count' in result_df.columns: y_col_for_chart = f'{target_col}_count'
                            
                            # 生成結論
                            conc_prompt = f"""用戶問：{question}
計算邏輯：{plan.get('plain_explanation', '')}
結果數據：\n{result_df.head(10).to_string()}
請寫出老闆能看懂的三段話，總字數不超過 150 字：發現(帶數字)、依據、建議。請使用繁體中文回答。"""
                            
                            resp2 = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "user", "content": conc_prompt}])
                            conclusion = resp2.choices[0].message.content.strip()
                            
                            st.markdown(conclusion)
                            
                            chart_data = result_df.to_dict(orient="records")
                            st.session_state.messages.append({
                                "role": "assistant", "content": conclusion,
                                "chart_data": chart_data, "x_col": x_col, "target_col": y_col_for_chart,
                                "whitebox_plan": plan, "whitebox_df": chart_data, "op": plan.get("operator")
                            })
                            
                            # 根據算子畫不同的圖表
                            if x_col and y_col_for_chart and y_col_for_chart in result_df.columns:
                                if plan.get("operator") == "trend":
                                    st.line_chart(data=result_df, x=x_col, y=y_col_for_chart, color="#FF4B4B")
                                else:
                                    st.bar_chart(data=result_df, x=x_col, y=y_col_for_chart, color="#2FA572")
                            
                            with st.expander("🔍 White Box | 白箱計算依據"):
                                st.json(plan)
                                st.dataframe(result_df, use_container_width=True)
                        else:
                            st.error("無法生成結果，請嘗試換個問法。")
                    except Exception as e:
                        st.error(f"分析發生錯誤：{e}")
                        
        if not is_paid and tracker[tracker_key] >= FREE_LIMIT:
            st.info("You have used all your free quotas. Please login to upgrade. | 您的免費額度已用完，請登入升級。")
else:
    st.info("👈 Please upload a file to start | 請先在左側上傳檔案開始分析。")
##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
