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
    RAW_API_KEY = "gsk_你的Groq密钥" 

client = OpenAI(api_key=RAW_API_KEY.strip(), base_url="https://api.groq.com/openai/v1")
MODEL_NAME = "openai/gpt-oss-120b"

PAYMENT_LINK = "https://your-payment-link.com" 
PAID_USERS = {"boss@example.com": "2026-12-31"}
FREE_LIMIT = 3
# ==========================================

st.set_page_config(page_title="Data Analyzer | 智能數據分析", page_icon="📊", layout="wide")
st.title("📊 Data Analyzer | 智能數據分析工具")
st.markdown("🔒 **Local Computing · Data Privacy Guaranteed** | **本地端計算 · 數據絕對安全**")
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
if tracker_key not in tracker: tracker[tracker_key] = 0
usage_count = tracker[tracker_key]

is_paid = False
if is_logged_in and user_email in PAID_USERS:
    expiry = datetime.strptime(PAID_USERS[user_email], "%Y-%m-%d").date()
    if datetime.now().date() <= expiry: is_paid = True

has_free_quota = is_paid or (usage_count < FREE_LIMIT)

if "df" not in st.session_state: st.session_state.df = None
if "messages" not in st.session_state: st.session_state.messages = []

# ================= 側邊欄 =================
with st.sidebar:
    st.header("👤 Account | 帳號")
    if not is_logged_in:
        st.info(f"🎁 **Free Trial**\nRemaining: {max(0, FREE_LIMIT - usage_count)} / {FREE_LIMIT}")
        if st.button("Login with Google | Google 登入"): st.login("google")
    else:
        st.success(f"Logged in: **{user_email}**")
        if st.button("Logout | 登出"):
            st.logout()
            st.session_state.browser_id = str(uuid.uuid4())
            st.rerun()
        if is_paid: st.success("👑 **Pro Member**")
        else: st.warning("⚠️ **Account not activated.**")

    st.divider()
    st.header("📂 Upload Data | 上傳數據")
    uploaded_file = st.file_uploader("Upload Excel or CSV", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'): df = pd.read_excel(uploaded_file)
            else:
                try: df = pd.read_csv(uploaded_file, encoding='utf-8')
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='big5')
            df.columns = df.columns.str.strip()
            st.session_state.df = df
            st.success(f"✅ Loaded: {uploaded_file.name}")
            with st.expander("🔍 Preview Data (前 5 行)"): st.dataframe(df.head(), use_container_width=True)
        except Exception as e: st.error(f"Error: {e}")
            
    if st.session_state.df is not None:
        if st.button("🗑️ Clear Data | 清除數據"):
            st.session_state.df = None
            st.session_state.messages = []
            st.rerun()

    if is_logged_in and not is_paid:
        st.divider()
        st.link_button("💳 Upgrade to Pro | 立即升級", PAYMENT_LINK)

# ================= 核心計算引擎 =================
def execute_local(df, plan):
    d = df.copy()
    op, gb, target = plan.get("operator"), plan.get("group_by"), plan.get("target_col")
    
    if isinstance(gb, list) and len(gb) > 0: gb = str(gb[0])
    if isinstance(target, list) and len(target) > 0: target = str(target[0])
    if gb in ["null", "None", "無", ""]: gb = None
    if target in ["null", "None", "無", ""]: target = None

    if not target:
        num_cols = d.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols: target = num_cols[0]
        else: return pd.DataFrame([{"提示": "找不到數值欄位"}]), None

    if target not in d.columns: raise ValueError(f"找不到欄位：{target}")
    d[target] = pd.to_numeric(d[target], errors='coerce').fillna(0)

    if op == "trend":
        time_col = next((c for c in d.columns if 'date' in str(c).lower() or '日期' in str(c) or '時間' in str(c)), None)
        if time_col:
            d[time_col] = pd.to_datetime(d[time_col], errors='coerce')
            d['_month'] = d[time_col].dt.to_period('M').astype(str)
            agg = d.groupby('_month')[target].agg(['sum', 'mean', 'count']).reset_index()
            agg.columns = ['_month', f'{target}_sum', f'{target}_mean', f'{target}_count']
            return agg, "_month"
        else: return pd.DataFrame([{"提示": "找不到日期欄位"}]), None

    elif op == "groupby_ratio" and gb and gb in d.columns:
        agg = d.groupby(gb)[target].sum().reset_index()
        total = agg[target].sum() if agg[target].sum() != 0 else 1
        agg[f'{target}_ratio'] = (agg[target] / total * 100).round(2).astype(str) + '%'
        return agg.sort_values(by=target, ascending=False).head(10), gb

    elif op == "anomaly" and gb and gb in d.columns:
        agg = d.groupby(gb)[target].sum().reset_index()
        threshold = agg[target].mean() + (2 * agg[target].std())
        anomalies = agg[agg[target] > threshold].sort_values(by=target, ascending=False).head(10)
        if anomalies.empty: return pd.DataFrame([{"提示": "未檢測到明顯異常值"}]), gb
        return anomalies, gb

    elif op in ["groupby_mean", "groupby_sum", "groupby_count", "rank"] and gb and gb in d.columns:
        if op in ["groupby_mean", "rank"]: agg = d.groupby(gb)[target].mean().reset_index()
        elif op == "groupby_sum": agg = d.groupby(gb)[target].sum().reset_index()
        else: agg = d.groupby(gb)[target].count().reset_index()
        return agg.sort_values(by=target, ascending=False).head(10), gb
    else:
        if op == "groupby_sum": return pd.DataFrame([{f"{target} 總和": d[target].sum()}]), None
        else: return pd.DataFrame([{f"{target} 平均值": d[target].mean()}]), None

# ================= 主畫面 =================
if st.session_state.df is not None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_data" in message:
                chart_data = pd.DataFrame(message["chart_data"])
                x_c, y_c = message.get("x_col"), message.get("target_col")
                if isinstance(x_c, list) and len(x_c) > 0: x_c = str(x_c[0])
                if isinstance(y_c, list) and len(y_c) > 0: y_c = str(y_c[0])
                if x_c and y_c and x_c in chart_data.columns and y_c in chart_data.columns:
                    if message.get("op") == "trend": st.line_chart(data=chart_data, x=x_c, y=y_c, color="#FF4B4B")
                    else: st.bar_chart(data=chart_data, x=x_c, y=y_c, color="#2FA572")
            if "whitebox_plan" in message:
                with st.expander("🔍 White Box | 白箱計算依據"):
                    st.json(message["whitebox_plan"])
                    st.dataframe(pd.DataFrame(message["whitebox_df"]), use_container_width=True)

    if not has_free_quota:
        st.warning("⚠️ **Free trial limit reached. | 免費試用次數已達上限。**")
        if not is_logged_in: st.markdown("👉 **請由左側選單登入以升級。**")
        else: st.markdown(f"👉 **請升級為專業版。** [點此付款]({PAYMENT_LINK})")
    else:
        if question := st.chat_input("Ask a question... | 輸入您的問題"):
            if not is_paid: tracker[tracker_key] += 1
                
            with st.chat_message("user"):
                st.markdown(question)
            st.session_state.messages.append({"role": "user", "content": question})
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing | 正在深度分析與計算..."):
                    try:
                        sample_data = st.session_state.df.head(3).to_dict(orient="records")
                        col_info = [f"{col}({'數值' if pd.api.types.is_numeric_dtype(st.session_state.df[col]) else '文字'})" for col in st.session_state.df.columns]
                        
                        prompt = f"""你是一個數據分析專家。請根據以下資訊生成分析計畫。
【欄位】{', '.join(col_info)}
【樣本】{sample_data}
【問題】{question}
【任務】只能選這六個算子之一：groupby_mean, groupby_sum, groupby_ratio, groupby_count, trend, anomaly。
只返回嚴格 JSON 包含：operator, group_by, target_col, assumptions, plain_explanation。"""

                        plan = None
                        for _ in range(2):
                            try:
                                resp = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
                                plan = json.loads(resp.choices[0].message.content)
                                break
                            except Exception as e:
                                if _ == 1: raise e

                        result_df, x_col = execute_local(st.session_state.df, plan)
                        
                        if result_df is not None and not result_df.empty:
                            target_col = plan.get("target_col")
                            if isinstance(target_col, list) and len(target_col) > 0: target_col = str(target_col[0])
                            
                            y_col_for_chart = target_col
                            if f'{target_col}_sum' in result_df.columns: y_col_for_chart = f'{target_col}_sum'
                            elif f'{target_col}_mean' in result_df.columns: y_col_for_chart = f'{target_col}_mean'
                            elif f'{target_col}_count' in result_df.columns: y_col_for_chart = f'{target_col}_count'
                            
                            # 【終極防呆】嚴格要求 AI 不准偷懶
                            conc_prompt = f"""你是一位專業的數據分析師。
用戶問：{question}
計算邏輯：{plan.get('plain_explanation', '')}
結果數據：\n{result_df.head(10).to_string()}

【嚴格要求】
1. 絕對不准只回覆表情符號或打招呼。
2. 必須給出有價值的數據洞察。
3. 請用繁體中文，按照以下格式輸出：
發現：[寫出最重要的事實，必須包含具體數字]
依據：[說明你是怎麼算出來的]
建議：[給出一個具體可執行的商業建議]
"""
                            resp2 = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "user", "content": conc_prompt}], max_tokens=500)
                            conclusion = resp2.choices[0].message.content.strip()
                            
                            # 【終極防呆】如果 AI 回傳字數太少（例如小於 20 個字），強制重試一次
                            if len(conclusion) < 20:
                                resp2 = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "user", "content": conc_prompt + "\n請注意：你剛剛的回覆太短了，請嚴格按照格式產出有數字的洞察！"}], max_tokens=500)
                                conclusion = resp2.choices[0].message.content.strip()
                            
                            st.markdown(conclusion)
                            
                            chart_data = result_df.to_dict(orient="records")
                            st.session_state.messages.append({
                                "role": "assistant", "content": conclusion,
                                "chart_data": chart_data, "x_col": x_col, "target_col": y_col_for_chart,
                                "whitebox_plan": plan, "whitebox_df": chart_data, "op": plan.get("operator")
                            })
                            
                            if isinstance(x_col, list) and len(x_col) > 0: x_col = str(x_col[0])
                            if x_col and y_col_for_chart and x_col in result_df.columns and y_col_for_chart in result_df.columns:
                                if plan.get("operator") == "trend": st.line_chart(data=result_df, x=x_col, y=y_col_for_chart, color="#FF4B4B")
                                else: st.bar_chart(data=result_df, x=x_col, y=y_col_for_chart, color="#2FA572")
                            
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
