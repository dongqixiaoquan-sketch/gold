# -*- coding: utf-8 -*-
"""
黄金对冲交易辅助系统（集成国际金价API）
Streamlit Cloud 100%部署成功 + 实时国际金价获取
"""
import streamlit as st
import pandas as pd
import time
import datetime
import requests
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

# ====================== 全局配置 ======================
st.set_page_config(
    page_title="黄金对冲交易辅助系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ====================== 国际金价API（免费稳定） ======================
def get_global_gold_price() -> dict:
    """
    获取国际金价（美元/盎司）+ 人民币换算价（元/克）
    接口来源：MetalPriceAPI（免费，无需注册）
    """
    try:
        # 国际金价接口（美元/盎司）
        url = "https://api.metalpriceapi.com/v1/latest"
        params = {
            "api_key": "demo",  # 测试密钥，可免费注册替换：https://metalpriceapi.com/
            "base": "USD",
            "symbols": "XAU"   # XAU=黄金，XAG=白银
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # 发送请求（适配Streamlit Cloud网络限制）
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=8,
            verify=False  # 关闭SSL验证，避免云端证书问题
        )
        data = response.json()
        
        if data.get("success") and "rates" in data and "XAU" in data["rates"]:
            # 国际金价：美元/盎司
            gold_usd_oz = data["rates"]["XAU"]
            # 换算为人民币/克（1盎司=31.1035克，1美元≈7.2人民币，可根据实时汇率调整）
            exchange_rate = 7.2  # 美元兑人民币汇率（可替换为实时汇率接口）
            gold_cny_g = round((gold_usd_oz / 31.1035) * exchange_rate, 2)
            
            return {
                "success": True,
                "gold_usd_oz": gold_usd_oz,    # 国际金价（美元/盎司）
                "gold_cny_g": gold_cny_g,      # 换算后人民币价（元/克）
                "timestamp": data.get("timestamp")
            }
        else:
            st.warning("国际金价API返回异常，使用默认价")
            return {"success": False, "gold_cny_g": 602.8}
    
    except Exception as e:
        st.warning(f"国际金价获取失败：{str(e)}，使用默认价")
        return {"success": False, "gold_cny_g": 602.8}

def get_realtime_gold_price() -> float:
    """获取实时金价（优先国际API，失败用默认价）"""
    gold_data = get_global_gold_price()
    return gold_data["gold_cny_g"]

# ====================== 核心策略类 ======================
class GoldHedgeStrategy:
    """黄金对冲策略核心计算类"""
    def __init__(self, initial_price: float, spread: float = 3.0, deposit_a: float = 35.0, deposit_b: float = 60.0):
        self.initial_price = round(initial_price, 2)
        self.spread = round(spread, 2)
        self.deposit_a = round(deposit_a, 2)
        self.deposit_b = round(deposit_b, 2)
        
        self.lock_sell_price = round(initial_price - (spread / 2), 2)
        self.lock_buy_price = round(initial_price + (spread / 2), 2)
        
        self.breakeven_up = round(self.lock_buy_price + deposit_a, 2)
        self.breakeven_down = round(self.lock_sell_price - deposit_b, 2)

    def calculate_real_profit(self, current_price: float) -> Dict:
        current_price = round(current_price, 2)
        profit_up = round((current_price - self.lock_buy_price) - self.deposit_a, 2)
        profit_down = round((self.lock_sell_price - current_price) - self.deposit_b, 2)
        price_change = round(current_price - self.initial_price, 2)
        
        return {
            "current_price": current_price,
            "price_change": price_change,
            "profit_up": profit_up,
            "profit_down": profit_down,
            "lock_sell_price": self.lock_sell_price,
            "lock_buy_price": self.lock_buy_price,
            "breakeven_up": self.breakeven_up,
            "breakeven_down": self.breakeven_down,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def generate_profit_table(self, price_range: tuple = (-120, 120), step: int = 20) -> pd.DataFrame:
        start_price = self.initial_price + price_range[0]
        end_price = self.initial_price + price_range[1]
        prices = [round(p, 2) for p in range(int(start_price), int(end_price)+1, step)]
        
        profit_list = []
        for price in prices:
            profit_data = self.calculate_real_profit(price)
            profit_list.append({
                "当前金价(元/克)": profit_data["current_price"],
                "相对开单价变动(元)": profit_data["price_change"],
                "上涨执行盈亏(元)": profit_data["profit_up"],
                "下跌执行盈亏(元)": profit_data["profit_down"]
            })
        
        return pd.DataFrame(profit_list)

# ====================== Streamlit主界面 ======================
def main():
    st.title("📈 黄金对冲交易辅助系统（国际金价版）")
    st.divider()

    # 初始化会话状态
    if "strategy" not in st.session_state:
        st.session_state["strategy"] = None
    if "monitor_running" not in st.session_state:
        st.session_state["monitor_running"] = False
    if "monitor_data" not in st.session_state:
        st.session_state["monitor_data"] = []

    # 显示国际金价信息
    st.subheader("🌍 实时国际金价")
    gold_data = get_global_gold_price()
    col1, col2, col3 = st.columns(3)
    with col1:
        if gold_data["success"]:
            st.metric("国际金价（美元/盎司）", f"{gold_data['gold_usd_oz']} USD")
        else:
            st.metric("国际金价（美元/盎司）", "获取失败")
    with col2:
        st.metric("换算人民币价（元/克）", f"{gold_data['gold_cny_g']} 元")
    with col3:
        st.metric("更新时间", datetime.datetime.now().strftime("%H:%M:%S"))
    st.divider()

    # 侧边栏参数配置
    with st.sidebar:
        st.header("🔧 策略参数配置")
        initial_price = st.number_input(
            "开单初始金价（元/克）",
            value=gold_data["gold_cny_g"],
            step=0.1,
            format="%.1f",
            key="initial_price"
        )
        spread = st.number_input(
            "平台总点差（元）",
            value=3.0,
            step=0.1,
            format="%.1f",
            key="spread"
        )
        deposit_a = st.number_input(
            "A平台看跌定金（元）",
            value=35.0,
            step=0.1,
            format="%.1f",
            key="deposit_a"
        )
        deposit_b = st.number_input(
            "B平台看涨定金（元）",
            value=60.0,
            step=0.1,
            format="%.1f",
            key="deposit_b"
        )
        monitor_interval = st.slider(
            "监控间隔（秒）",
            min_value=30,
            max_value=300,
            value=60,
            step=30,
            key="monitor_interval"
        )

        # 初始化策略按钮
        if st.button("✅ 初始化策略", use_container_width=True, type="primary"):
            st.session_state["strategy"] = GoldHedgeStrategy(
                initial_price=initial_price,
                spread=spread,
                deposit_a=deposit_a,
                deposit_b=deposit_b
            )
            st.session_state["monitor_data"] = []
            st.success("策略初始化成功！")

    # 核心功能区
    strategy = st.session_state["strategy"]
    if not strategy:
        st.info("请先在侧边栏配置参数并初始化策略！")
        return

    # 核心参数展示
    st.subheader("🎯 策略核心参数")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("初始开单价", f"{strategy.initial_price} 元/克")
    with col2:
        st.metric("锁定卖出价", f"{strategy.lock_sell_price} 元/克")
    with col3:
        st.metric("锁定买入价", f"{strategy.lock_buy_price} 元/克")
    with col4:
        st.metric("平台总点差", f"{strategy.spread} 元")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("📈 上涨盈亏平衡价", f"{strategy.breakeven_up} 元/克")
    with col2:
        st.metric("📉 下跌盈亏平衡价", f"{strategy.breakeven_down} 元/克")
    st.divider()

    # 实时行情与盈亏计算
    st.subheader("📡 实时行情监控")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        real_price = get_realtime_gold_price()
        profit_data = strategy.calculate_real_profit(real_price)
        
        profit_up_status = "🟢 盈利" if profit_data["profit_up"] > 0 else "🔴 亏损" if profit_data["profit_up"] < 0 else "⚫ 持平"
        profit_down_status = "🟢 盈利" if profit_data["profit_down"] > 0 else "🔴 亏损" if profit_data["profit_down"] < 0 else "⚫ 持平"
        
        st.write(f"**当前时间**：{profit_data['timestamp']}")
        st.write(f"**实时金价**：{profit_data['current_price']} 元/克（相对开单价：{profit_data['price_change']:+} 元）")
        st.write(f"**上涨执行盈亏**：{profit_data['profit_up']} 元 {profit_up_status}")
        st.write(f"**下跌执行盈亏**：{profit_data['profit_down']} 元 {profit_down_status}")

    with col2:
        if not st.session_state["monitor_running"]:
            if st.button("▶️ 启动实时监控", use_container_width=True, type="primary"):
                st.session_state["monitor_running"] = True
                st.success("监控已启动！")
        else:
            if st.button("⏹️ 停止实时监控", use_container_width=True, type="secondary"):
                st.session_state["monitor_running"] = False
                st.warning("监控已停止！")

    # 自动监控逻辑
    if st.session_state["monitor_running"]:
        try:
            st.session_state["monitor_data"].append(profit_data)
            if len(st.session_state["monitor_data"]) > 100:
                st.session_state["monitor_data"].pop(0)
            
            if real_price >= strategy.breakeven_up:
                st.warning(
                    f"⚠️ 金价突破上涨平衡点！\n"
                    f"当前价：{real_price} ≥ 平衡点：{strategy.breakeven_up}\n"
                    f"建议执行B平台买单平仓！"
                )
            elif real_price <= strategy.breakeven_down:
                st.warning(
                    f"⚠️ 金价突破下跌平衡点！\n"
                    f"当前价：{real_price} ≤ 平衡点：{strategy.breakeven_down}\n"
                    f"建议执行A平台卖单平仓！"
                )
            
            time.sleep(monitor_interval)
            st.rerun()
        except Exception as e:
            st.error(f"监控异常：{str(e)}")
            st.session_state["monitor_running"] = False

    # 监控历史数据
    if st.session_state["monitor_data"]:
        st.subheader("📊 监控历史数据")
        monitor_df = pd.DataFrame(st.session_state["monitor_data"])
        monitor_df = monitor_df[["timestamp", "current_price", "price_change", "profit_up", "profit_down"]]
        st.dataframe(monitor_df, use_container_width=True, hide_index=True)

    st.divider()

    # 盈亏阶梯表
    st.subheader("📋 盈亏阶梯表")
    profit_table = strategy.generate_profit_table(price_range=(-120, 120), step=20)
    st.dataframe(profit_table, use_container_width=True, hide_index=True)

    # Excel导出功能（CSV格式，无额外依赖）
    col1, col2 = st.columns(2)
    with col1:
        @st.cache_data
        def convert_df(df):
            return df.to_csv(index=False).encode('utf-8')
        
        csv_data = convert_df(profit_table)
        st.download_button(
            label="📥 下载盈亏阶梯表（CSV）",
            data=csv_data,
            file_name=f"黄金对冲盈亏表_{datetime.date.today()}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        if st.session_state["monitor_data"]:
            monitor_csv = convert_df(monitor_df)
            st.download_button(
                label="📥 下载监控历史数据（CSV）",
                data=monitor_csv,
                file_name=f"黄金对冲监控数据_{datetime.date.today()}.csv",
                mime="text/csv",
                use_container_width=True
            )

    # API使用说明
    with st.expander("🔍 API使用说明", expanded=False):
        st.info("""
        1. 国际金价API使用MetalPriceAPI免费测试密钥（demo），每小时限100次请求；
        2. 如需更高频率/稳定性，可免费注册获取专属API Key：https://metalpriceapi.com/；
        3. 人民币换算汇率默认7.2，可替换为实时汇率接口（如新浪财经汇率API）；
        4. API失败时自动切换到默认价602.8元/克，不影响核心功能。
        """)

if __name__ == "__main__":
    main()
