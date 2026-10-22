# web_app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
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
# ==========================================

# 設定網頁標題與圖標
st.set_page_config(page_title="Data Analyzer | 智能數據分析", page_icon="📊", layout="wide")

# 自訂 CSS
st.markdown("""
    <style>
    .stApp { max-width: 1100px; margin: 0 auto; }
    .stButton>button { width: 100%; border-radius: 8px; height: 50px; font-weight: bold; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# 中英文對照標題
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
    st.session_state.usage_count = 0 # 追蹤使用次數

FREE_LIMIT = 3

# 側邊欄
with st.sidebar:
    st.header("1. Upload Data | 上傳數據")
    
    # 顯示剩餘次數
    st.info(f"🎁 **Free Trial | 免費試用**\nRemaining: {max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} times\n剩餘次數：{max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} 次")
    
    uploaded_file = st.file_uploader("Upload Excel or CSV | 選擇 Excel 或 CSV", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)
            
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

# 核心計算函數
def execute_local(df, plan):
    d = df.copy()
    op = plan.get("operator")
    gb = plan.get("group_by")
    
    if isinstance(gb, list): gb = gb[0] if len(gb) > 0 else None
    if isinstance(gb, str):
        gb = gb.strip()
        if gb in ["null", "None", "無", ""]: gb = None

    rev_col = next((c for c in d.columns if 'revenue' in str(c).lower() or '銷售' in str(c) or '收入' in str(c)), None)
    cost_col = next((c for c in d.columns if 'cost' in str(c).lower() or '成本' in str(c)), None)
    return_col = next((c for c in d.columns if 'return' in str(c).lower() or '退貨' in str(c)), None)

    if not rev_col: raise ValueError("Missing revenue column | 找不到銷售額欄位")

    if return_col:
        is_return = d[return_col].astype(str).str.contains('是|1|True|true', case=False, na=False)
        d['_net_rev'] = np.where(is_return, 0, d[rev_col])
    else:
        d['_net_rev'] = d[rev_col]

    if cost_col:
        d['_profit'] = d['_net_rev'] - d[cost_col]
    else:
        d['_profit'] = d['_net_rev']

    if gb is None or gb not in d.columns:
        return pd.DataFrame([{"Net Revenue": d['_net_rev'].sum(), "Profit": d['_profit'].sum()}]), None

    if op == "breakdown":
        agg = d.groupby(gb).agg(Net_Revenue=('_net_rev', 'sum'), Profit=('_profit', 'sum')).reset_index()
        agg['Margin'] = (agg['Profit'] / agg['Net_Revenue'].replace(0, np.nan)).round(3)
        return agg.sort_values('Profit').head(10), gb
    elif op == "quality" and return_col:
        d['_is_return'] = is_return.astype(int)
        agg = d.groupby(gb).agg(Orders=('_net_rev', 'count'), Returns=('_is_return', 'sum')).reset_index()
        agg['Return_Rate'] = (agg['Returns'] / agg['Orders']).round(3)
        return agg.sort_values('Return_Rate', ascending=False).head(10), gb
    elif op == "trend":
        time_col = next((c for c in d.columns if 'date' in str(c).lower() or '日期' in str(c) or '時間' in str(c)), None)
        if time_col:
            d[time_col] = pd.to_datetime(d[time_col], errors='coerce')
            d['_month'] = d[time_col].dt.to_period('M').astype(str)
            agg = d.groupby('_month').agg(Net_Revenue=('_net_rev', 'sum'), Profit=('_profit', 'sum')).reset_index()
            return agg, "_month"
        else:
            agg = d.groupby(gb).agg(Profit=('_profit', 'sum')).reset_index()
            return agg.sort_values('Profit').head(10), gb
    else:
        agg = d.groupby(gb).agg(Profit=('_profit', 'sum')).reset_index()
        return agg.sort_values('Profit').head(10), gb

# 主畫面
if st.session_state.df is not None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "chart_data" in message:
                chart_data = pd.DataFrame(message["chart_data"])
                if "Profit" in chart_data.columns:
                    st.bar_chart(data=chart_data, x=message["x_col"], y="Profit", color="#2FA572")
                elif "Return_Rate" in chart_data.columns:
                    st.bar_chart(data=chart_data, x=message["x_col"], y="Return_Rate", color="#FF4B4B")

    # 檢查是否還有額度
    if st.session_state.usage_count >= FREE_LIMIT:
        st.warning("⚠️ **Free trial limit reached. | 免費試用次數已達上限。**\n\nPlease upgrade to Pro to continue analyzing. | 請升級至 Pro 版本以繼續分析。")
        st.markdown("[👉 Upgrade Now | 立即升級](https://your-payment-link.com)") # 替換成你的付款連結
    else:
        # 輸入框 (支援中英文)
        if question := st.chat_input("Ask a question... | 輸入您的問題（例如：哪個品類在虧錢？）"):
            st.session_state.usage_count += 1 # 增加使用次數
            with st.chat_message("user"):
                st.markdown(question)
            st.session_state.messages.append({"role": "user", "content": question})
            
            with st.chat_message("assistant"):
                with st.spinner("Analyzing | 正在分析中..."):
                    try:
                        columns = list(st.session_state.df.columns)
                        prompt = f"Columns: {columns}\nQuestion: {question}\nReturn strict JSON with: operator, group_by, measure_cols, assumptions, plain_explanation. Explain in Chinese and English."
                        
                        resp = client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=[{"role": "user", "content": prompt}],
                            response_format={"type": "json_object"}
                        )
                        plan = json.loads(resp.choices[0].message.content)
                        
                        result_df, x_col = execute_local(st.session_state.df, plan)
                        
                        if result_df is not None and not result_df.empty:
                            conc_prompt = f"Question: {question}\nLogic: {plan.get('plain_explanation', '')}\nData:\n{result_df.head(5).to_string()}\nWrite 3 points (Findings, Basis, Suggestion) in both Traditional Chinese and English. Max 100 words."
                            resp2 = client.chat.completions.create(
                                model=MODEL_NAME,
                                messages=[{"role": "user", "content": conc_prompt}]
                            )
                            conclusion = resp2.choices[0].message.content.strip()
                            
                            st.markdown(conclusion)
                            
                            chart_data = result_df.to_dict(orient="records")
                            st.session_state.messages.append({
                                "role": "assistant", "content": conclusion,
                                "chart_data": chart_data, "x_col": x_col
                            })
                            
                            if x_col:
                                if "Profit" in result_df.columns:
                                    st.bar_chart(data=result_df, x=x_col, y="Profit", color="#2FA572")
                                elif "Return_Rate" in result_df.columns:
                                    st.bar_chart(data=result_df, x=x_col, y="Return_Rate", color="#FF4B4B")
                            
                            with st.expander("🔍 White Box | 白箱計算依據"):
                                st.json(plan)
                                st.dataframe(result_df, use_container_width=True)
                        else:
                            st.error("No results generated | 無法生成結果")
                    except Exception as e:
                        st.error(f"Error: {e}")
else:
    st.info("👈 Please upload a file to start | 請先在左側上傳檔案開始分析。")


    ##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
