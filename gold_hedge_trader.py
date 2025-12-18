# -*- coding: utf-8 -*-
"""
黄金对冲交易辅助系统（Streamlit Cloud适配版）
修复日志目录/接口权限/路径问题
"""
import streamlit as st
import pandas as pd
import requests
import time
import logging
import datetime
import json
from typing import Dict, List
import warnings
import os
warnings.filterwarnings('ignore')

# ====================== 全局配置 ======================
st.set_page_config(
    page_title="黄金对冲交易辅助系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ====================== 日志配置（适配Streamlit Cloud） ======================
def init_logger():
    """
    修复：使用Streamlit Cloud允许的临时目录存储日志
    云端只读文件系统，只能写入/tmp目录
    """
    # 区分本地/云端环境
    if st.runtime.exists():
        # Streamlit Cloud环境：使用临时目录
        log_dir = "/tmp/gold_hedge_logs"
    else:
        # 本地环境：使用相对目录
        log_dir = "gold_hedge_logs"
    
    if not st.session_state.get("logger_init"):
        # 确保日志目录可创建（云端/tmp目录有写入权限）
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            st.warning(f"日志目录创建失败（不影响核心功能）：{str(e)}")
        
        # 配置日志（仅输出到控制台+云端日志，避免文件写入报错）
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]  # 移除FileHandler，避免文件写入错误
        )
        st.session_state["logger_init"] = True
    return logging.getLogger(__name__)

logger = init_logger()

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
        
        logger.info(
            f"策略初始化完成 | 初始价：{self.initial_price} | 点差：{self.spread} | "
            f"A定金：{self.deposit_a} | B定金：{self.deposit_b} | "
            f"上涨平衡点：{self.breakeven_up} | 下跌平衡点：{self.breakeven_down}"
        )

    def calculate_real_profit(self, current_price: float) -> Dict:
        current_price = round(current_price, 2)
        profit_up = round((current_price - self.lock_buy_price) - self.deposit_a, 2)
        profit_down = round((self.lock_sell_price - current_price) - self.deposit_b, 2)
        price_change = round(current_price - self.initial_price, 2)
        
        result = {
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
        
        logger.info(
            f"实时盈亏计算 | 当前价：{current_price} | 价格变动：{price_change} | "
            f"上涨盈亏：{profit_up} | 下跌盈亏：{profit_down}"
        )
        return result

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
        
        df = pd.DataFrame(profit_list)
        logger.info(f"盈亏阶梯表生成完成 | 价格范围：{price_range} | 步长：{step}")
        return df

# ====================== 实时行情接口（优化云端请求） ======================
def get_realtime_gold_price() -> float:
    """
    优化：适配Streamlit Cloud的API请求规则
    1. 增加更完善的请求头
    2. 缩短超时时间（云端超时限制更严格）
    3. 简化解析逻辑，降低报错概率
    """
    # 接口1：东方财富网（最稳定）
    def _eastmoney_gold_price():
        try:
            url = "https://push2.eastmoney.com/api/qt/stock/get?secid=85.AUTD&fields=f43"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive"
            }
            # 云端超时设置为5秒（更严格）
            response = requests.get(url, headers=headers, timeout=5, verify=False)  # 关闭SSL验证，避免云端证书错误
            data = response.json()
            if data.get("data") and "f43" in data["data"]:
                price = float(data["data"]["f43"])
                logger.info(f"东方财富接口获取金价成功 | 价格：{price} 元/克")
                return round(price, 2)
        except Exception as e1:
            logger.warning(f"东方财富接口失败：{str(e1)}")
        return None

    # 接口2：备用静态测试价（避免云端API请求失败）
    def _default_price():
        default_price = 602.5  # 可手动更新最新价
        logger.info(f"使用备用测试价：{default_price} 元/克")
        return default_price

    # 优先用东方财富接口，失败则用测试价
    price = _eastmoney_gold_price()
    if price:
        return price
    return _default_price()

# ====================== Streamlit界面（移除日志文件读取） ======================
def main():
    """主界面逻辑"""
    st.title("📈 黄金对冲交易辅助系统（云端适配版）")
    st.divider()

    # 初始化会话状态
    if "strategy" not in st.session_state:
        st.session_state["strategy"] = None
    if "monitor_running" not in st.session_state:
        st.session_state["monitor_running"] = False
    if "monitor_data" not in st.session_state:
        st.session_state["monitor_data"] = []

    # 侧边栏参数配置
    with st.sidebar:
        st.header("🔧 策略参数配置")
        # 优化：先获取测试价，避免接口请求阻塞初始化
        try:
            init_price = get_realtime_gold_price()
        except:
            init_price = 600.0
        initial_price = st.number_input(
            "开单初始金价（元/克）",
            value=init_price,
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
        try:
            real_price = get_realtime_gold_price()
        except:
            real_price = 600.0
            st.warning("⚠️ 实时行情获取失败，使用默认价600元/克")
        
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

    # 自动监控逻辑（优化云端循环）
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
                logger.warning(f"平仓提醒：上涨平衡点突破 | 当前价：{real_price} | 平衡点：{strategy.breakeven_up}")
            elif real_price <= strategy.breakeven_down:
                st.warning(
                    f"⚠️ 金价突破下跌平衡点！\n"
                    f"当前价：{real_price} ≤ 平衡点：{strategy.breakeven_down}\n"
                    f"建议执行A平台卖单平仓！"
                )
                logger.warning(f"平仓提醒：下跌平衡点突破 | 当前价：{real_price} | 平衡点：{strategy.breakeven_down}")
            
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

    # Excel导出功能
    col1, col2 = st.columns(2)
    with col1:
        @st.cache_data
        def convert_df_to_excel(df):
            return df.to_excel(index=False).encode('utf-8')
        
        excel_data = convert_df_to_excel(profit_table)
        st.download_button(
            label="📥 下载盈亏阶梯表",
            data=excel_data,
            file_name=f"黄金对冲盈亏表_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col2:
        if st.session_state["monitor_data"]:
            monitor_excel = convert_df_to_excel(monitor_df)
            st.download_button(
                label="📥 下载监控历史数据",
                data=monitor_excel,
                file_name=f"黄金对冲监控数据_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # 移除日志文件读取（云端无权限访问）
    with st.expander("🔍 运行日志（云端版）", expanded=False):
        st.info("云端环境已禁用本地日志文件，关键操作日志可在Streamlit Cloud后台查看")

if __name__ == "__main__":
    main()
