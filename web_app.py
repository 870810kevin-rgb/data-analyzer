# web_app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from openai import OpenAI

# ================= 配置區 =================
# 判斷是否在 Streamlit Cloud 上運行，優先讀取 Secrets
try:
    RAW_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    # 本地測試用：請在這裡填入你的 gsk_ 開頭 Key
    RAW_API_KEY = "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" 

GROQ_API_KEY = RAW_API_KEY.encode("ascii", errors="ignore").decode("ascii").strip()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)
MODEL_NAME = "openai/gpt-oss-120b"
# ==========================================

st.set_page_config(page_title="Data Analyzer | 智能數據分析", page_icon="📊", layout="wide")

# 自訂 CSS 讓介面更現代
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

FREE_LIMIT = 3

# 側邊欄
with st.sidebar:
    st.header("1. Upload Data | 上傳數據")
    
    st.info(f"🎁 **Free Trial | 免費試用**\nRemaining: {max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} times\n剩餘次數：{max(0, FREE_LIMIT - st.session_state.usage_count)} / {FREE_LIMIT} 次")
    
    uploaded_file = st.file_uploader("Upload Excel or CSV | 選擇 Excel 或 CSV", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                # 修復：自動處理 CSV 的編碼問題 (UTF-8 或 台灣常用的 Big5)
                try:
                    df = pd.read_csv(uploaded_file, encoding='utf-8')
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='big5')
            
            # 清理欄位名稱的隱藏空白
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

# 核心計算函數 (泛用防呆版)
def execute_local(df, plan):
    d = df.copy()
    op = plan.get("operator")
    gb = plan.get("group_by")
    target = plan.get("target_col")
    
    # 處理 AI 可能回傳 List 的防呆
    if isinstance(gb, list): gb = gb[0] if len(gb) > 0 else None
    if isinstance(gb, str):
        gb = gb.strip()
        if gb in ["null", "None", "無", ""]: gb = None
        
    if isinstance(target, list): target = target[0] if len(target) > 0 else None
    if isinstance(target, str):
        target = target.strip()
        if target in ["null", "None", "無", ""]: target = None

    # 如果 AI 沒給目標欄位，嘗試找一個數值欄位
    if not target:
        num_cols = d.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols:
            target = num_cols[0]
        else:
            return pd.DataFrame([{"提示": "找不到可計算的數值欄位 (No numerical column found)"}]), None

    # 確保目標欄位存在
    if target not in d.columns:
        raise ValueError(f"找不到欄位：{target} (Column not found)")

    # 如果沒有有效的分組欄位，直接回傳整體統計
    if not gb or gb not in d.columns:
        if op in ["groupby_mean", "rank"]:
            return pd.DataFrame([{f"{target} 平均值": d[target].mean()}]), None
        elif op == "groupby_sum":
            return pd.DataFrame([{f"{target} 總和": d[target].sum()}]), None
        else:
            return pd.DataFrame([{f"{target} 總數": d[target].count()}]), None

    # 執行分組分析
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
    # 顯示歷史對話 (包含圖表與白箱)
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # 顯示圖表
            if "chart_data" in message:
                chart_data = pd.DataFrame(message["chart_data"])
                if message.get("x_col") and message.get("target_col"):
                    st.bar_chart(data=chart_data, x=message["x_col"], y=message["target_col"], color="#2FA572")
            
            # 顯示白箱
            if "whitebox_plan" in message and "whitebox_df" in message:
                with st.expander("🔍 White Box | 白箱計算依據"):
                    st.markdown("**第一步：AI 分析計畫**")
                    st.json(message["whitebox_plan"])
                    st.markdown("**第二步：本地端執行計算**")
                    st.dataframe(pd.DataFrame(message["whitebox_df"]), use_container_width=True)

    # 檢查額度
    if st.session_state.usage_count >= FREE_LIMIT:
        st.warning("⚠️ **Free trial limit reached. | 免費試用次數已達上限。**\n\nPlease upgrade to Pro to continue analyzing. | 請升級至 Pro 版本以繼續分析。")
        st.markdown("[👉 Upgrade Now | 立即升級](https://your-payment-link.com)") 
    else:
        # 輸入框
        if question := st.chat_input("Ask a question... | 輸入您的問題（例如：哪條路線預估時間最長？）"):
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
                            # 存入歷史紀錄，包含白箱
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": conclusion,
                                "chart_data": chart_data,
                                "x_col": x_col,
                                "target_col": target_col,
                                "whitebox_plan": plan,
                                "whitebox_df": chart_data
                            })
                            
                            # 畫圖表
                            if x_col and target_col and target_col in result_df.columns:
                                st.bar_chart(data=result_df, x=x_col, y=target_col, color="#2FA572")
                            
                            # 立即顯示白箱
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
