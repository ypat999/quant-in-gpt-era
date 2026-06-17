# -*- coding: utf-8 -*-
"""
实时盯盘预警系统（多数据源 + 高频 + 综合评分版）
-------------------------------------------------
监控指定个股的实时走势，包含日K级别与分钟级别双层预警，
并集成多因子综合买卖点评分系统。

【数据源】4 源冗余，自动切换
    1. akshare（东财）
    2. 新浪财经 hq.sinajs.cn（国内免费，免注册）
    3. 腾讯财经 qt.gtimg.cn（国内免费，免注册）
    4. yfinance（墙外，全球市场，需 pip install yfinance）

【日K级别】18 项基础因子
【分钟级别】28 项高频 alpha 因子
    微观结构：VWAP偏离 / TWAP偏离 / OFI订单流不平衡 / Kyle Lambda价格冲击 /
              Amihud非流动性 / 买卖力道 / VPIN简化版
    动量反转：短期动量 / 动量加速 / Z-score价格跳跃 / 短期反转
    波动率：  已实现波动率RV / 波动率比 / 分钟ATR / 分钟布林带
    量能：    分钟量比突变 / 成交量脉冲 / 成交集中度Herfindahl /
              量价相关 / 大单占比
    形态：    Donchian通道突破 / 分钟均线突破 / 分钟MACD /
              分钟RSI / 分钟KDJ / 双顶双底
    统计：    Hurst指数 / 偏度峰度 / 收益自相关

【综合买卖点评分】8 维度加权打分（-100 ~ +100）
    趋势(20%) + 动量(15%) + 反转(10%) + 量能(15%) +
    微观结构(10%) + 波动率(10%) + 统计(10%) + 结构(10%)
    输出：强烈买入/买入/观望/卖出/强烈卖出
    附加：ATR止损止盈 + 风险收益比 + 凯利公式仓位建议

使用方法：
    1. 修改 WATCH_LIST 为你要盯的股票代码（纯数字）
    2. 运行：python realtime_monitor.py
"""

import time
import threading
import winsound
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
from queue import Queue, Empty
import re
import json
import urllib.request
import urllib.error

import numpy as np
import pandas as pd
import akshare as ak

try:
    import yfinance as yf  # 墙外数据源
    _HAS_YFINANCE = True
except Exception:
    _HAS_YFINANCE = False


# =====================================================================
# 配置区
# =====================================================================
WATCH_LIST = [
    "600519",   # 贵州茅台
    "000001",   # 平安银行
    "300750",   # 宁德时代
    "002594",   # 比亚迪
    "000858",   # 五粮液
]

SCAN_INTERVAL = 10          # 主扫描间隔（秒）
MINUTE_PERIOD = "1"         # 分钟周期: 1/5/15/30/60
MINUTE_BARS = 240           # 拉取分钟K线根数
HISTORY_DAYS = 120          # 日K历史天数

THRESHOLDS = {
    # 日K
    "pct_change":      0.03,
    "amplitude":       0.05,
    "volume_ratio":    2.0,
    "volume_surge":    2.5,
    "rsi_overbought":  80,
    "rsi_oversold":    20,
    "atr_ratio":       2.0,
    "consecutive_days": 5,
    "new_high_low_days": 20,
    "limit_pct":       0.095,
    "big_amount_ratio": 3.0,
    # 高频
    "vwap_dev":        0.015,   # VWAP偏离 1.5%
    "twap_dev":        0.015,
    "ofi_ratio":       0.3,     # OFI净额/总成交 30%
    "kyle_lambda":     0.0,     # 价格冲击系数（自动）
    "amihud_high":     1e-9,    # 非流动性高
    "buy_sell_force":  0.3,     # 买卖力道 30%
    "vpin_high":       0.5,
    "mom_short":       0.01,    # 1分钟动量 1%
    "mom_accel":       0.005,
    "zscore_jump":     2.5,     # 价格跳跃Z-score
    "rv_ratio":        2.0,     # 短期/长期波动率比
    "min_vol_ratio":   3.0,     # 分钟量比
    "vol_pulse":       4.0,     # 单分钟放量倍数
    "herfindahl":      0.15,    # 成交集中度
    "big_order_pct":   0.3,     # 大单占比
    "hurst_trend":     0.65,    # Hurst>0.65 趋势
    "hurst_mean_rev":  0.35,    # Hurst<0.35 反转
    "autocorr":        0.3,
    "donchian_n":      60,
}


# =====================================================================
# 通用指标函数
# =====================================================================
def calc_ma(s, n): return s.rolling(n, min_periods=1).mean()

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    dif = ema_f - ema_s
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea, (dif - dea) * 2

def calc_rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(n, min_periods=1).mean()
    avg_loss = loss.rolling(n, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)

def calc_kdj(high, low, close, n=9):
    low_n = low.rolling(n, min_periods=1).min()
    high_n = high.rolling(n, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return k, d, 3 * k - 2 * d

def calc_boll(close, n=20, k=2):
    mid = close.rolling(n, min_periods=1).mean()
    std = close.rolling(n, min_periods=1).std()
    return mid + k * std, mid, mid - k * std

def calc_atr(high, low, close, n=14):
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(),
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=1).mean()


# =====================================================================
# 高频专用函数
# =====================================================================
def vwap(high, low, close, volume):
    tp = (high + low + close) / 3.0
    return (tp * volume).cumsum() / volume.cumsum().replace(0, np.nan)

def twap(close):
    """时间加权均价（等权累积均值）"""
    return close.expanding().mean()

def realized_volatility(returns, n=20):
    """已实现波动率（年化按 240 分钟/日 × 250 日）"""
    return returns.rolling(n).std() * np.sqrt(240 * 250)

def kyle_lambda(returns, volume_signed):
    """价格冲击系数：收益率对成交量的回归斜率"""
    try:
        if len(returns) < 30:
            return np.nan
        x = volume_signed.values[-30:]
        y = returns.values[-30:]
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() < 10:
            return np.nan
        slope = np.polyfit(x[mask], y[mask], 1)[0]
        return slope
    except Exception:
        return np.nan

def amihud_illiquidity(returns, amount, n=20):
    """Amihud 非流动性 = |r| / 成交额"""
    ill = returns.abs() / amount.replace(0, np.nan)
    return ill.rolling(n, min_periods=1).mean()

def ofi(close, volume):
    """订单流不平衡（OFI）简化版：以分钟涨跌方向给成交量带符号"""
    direction = np.sign(close.diff().fillna(0))
    signed_vol = direction * volume
    return signed_vol

def vpin(close, volume, n=10):
    """VPIN 简化版：基于方向成交量的差异比例"""
    direction = np.sign(close.diff().fillna(0))
    buy = (direction > 0) * volume
    sell = (direction < 0) * volume
    buy_sum = buy.rolling(n, min_periods=1).sum()
    sell_sum = sell.rolling(n, min_periods=1).sum()
    total = (buy_sum + sell_sum).replace(0, np.nan)
    return (buy_sum - sell_sum).abs() / total

def hurst_rs(series, n=50):
    """简化 R/S Hurst 指数"""
    def _rs(x):
        if len(x) < 10:
            return np.nan
        mean = np.mean(x)
        dev = np.cumsum(x - mean)
        R = np.max(dev) - np.min(dev)
        S = np.std(x)
        if S == 0 or R == 0:
            return np.nan
        return np.log(R / S) / np.log(len(x))
    return series.rolling(n).apply(_rs, raw=True)

def herfindahl(volume, n=30):
    """成交集中度 Herfindahl 指数（0~1，越大越集中）"""
    def _h(x):
        s = np.sum(x)
        if s == 0:
            return np.nan
        return np.sum((x / s) ** 2)
    return volume.rolling(n).apply(_h, raw=True)

def donchian_channel(high, low, n):
    """唐奇安通道"""
    return high.rolling(n).max(), low.rolling(n).min()


# =====================================================================
# 多数据源管理器（akshare / 新浪 / 腾讯 / yfinance）
# =====================================================================
def _to_sina_symbol(code: str) -> str:
    """600519 -> sh600519, 000001 -> sz000001, 300750 -> sz300750"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90", "11")):
        return f"sh{code}"
    return f"sz{code}"


def _to_tencent_symbol(code: str) -> str:
    """600519 -> sh600519（与新浪相同）"""
    return _to_sina_symbol(code)


def _to_yf_symbol(code: str) -> str:
    """600519 -> 600519.SS, 000001 -> 000001.SZ"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90")):
        return f"{code}.SS"
    return f"{code}.SZ"


class MultiSourceQuote:
    """多源实时行情聚合器：依次尝试 akshare → 新浪 → 腾讯 → yfinance"""

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def __init__(self):
        self.source_order = ["akshare", "sina", "tencent", "yfinance"]
        self.last_ok_source = "akshare"

    # ---- 各源实现 ----
    def _akshare(self, code):
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "source": "akshare",
            "name": str(r.get("名称", code)),
            "price": float(r["最新价"]),
            "pct": float(r["涨跌幅"]),
            "change": float(r["涨跌额"]),
            "volume": float(r["成交量"]),
            "amount": float(r["成交额"]),
            "high": float(r["最高"]),
            "low": float(r["最低"]),
            "open": float(r["今开"]),
            "prev_close": float(r["昨收"]),
            "amplitude": float(r["振幅"]),
            "turnover": float(r.get("换手率", 0)),
            "volume_ratio": float(r.get("量比", 0)),
        }

    def _sina(self, code):
        sym = _to_sina_symbol(code)
        url = f"http://hq.sinajs.cn/list={sym}"
        req = urllib.request.Request(url, headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": self.UA,
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("gbk", errors="ignore")
        m = re.search(r'"([^"]*)"', text)
        if not m or not m.group(1):
            return {}
        f = m.group(1).split(",")
        if len(f) < 10:
            return {}
        open_p = float(f[1]); prev_close = float(f[2])
        price = float(f[3]); high = float(f[4]); low = float(f[5])
        volume = float(f[8]); amount = float(f[9])
        pct = (price / prev_close - 1) * 100 if prev_close else 0
        return {
            "source": "sina", "name": f[0],
            "price": price, "pct": pct,
            "change": price - prev_close,
            "volume": volume, "amount": amount,
            "high": high, "low": low, "open": open_p,
            "prev_close": prev_close,
            "amplitude": (high - low) / prev_close * 100 if prev_close else 0,
            "turnover": 0, "volume_ratio": 0,
        }

    def _tencent(self, code):
        sym = _to_tencent_symbol(code)
        url = f"http://qt.gtimg.cn/q={sym}"
        req = urllib.request.Request(url, headers={"User-Agent": self.UA})
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("gbk", errors="ignore")
        m = re.search(r'"([^"]*)"', text)
        if not m or not m.group(1):
            return {}
        f = m.group(1).split("~")
        if len(f) < 35:
            return {}
        # 腾讯字段：1名称 4现价 5涨跌 6涨跌幅 9开盘 10昨收
        # 33最高 34最低 36成交额 37成交量(手) 38换手 49量比
        name = f[1]; price = float(f[4]); prev_close = float(f[10])
        open_p = float(f[9]); high = float(f[33]); low = float(f[34])
        amount = float(f[36]); volume = float(f[37]) * 100
        pct = float(f[6]) if f[6] else (price / prev_close - 1) * 100
        return {
            "source": "tencent", "name": name,
            "price": price, "pct": pct,
            "change": float(f[5]) if f[5] else price - prev_close,
            "volume": volume, "amount": amount,
            "high": high, "low": low, "open": open_p,
            "prev_close": prev_close,
            "amplitude": (high - low) / prev_close * 100 if prev_close else 0,
            "turnover": float(f[38]) if f[38] else 0,
            "volume_ratio": float(f[49]) if len(f) > 49 and f[49] else 0,
        }

    def _yfinance(self, code):
        if not _HAS_YFINANCE:
            return {}
        sym = _to_yf_symbol(code)
        t = yf.Ticker(sym)
        info = t.fast_info
        price = info.get("last_price")
        if price is None:
            return {}
        prev = info.get("previous_close", price)
        return {
            "source": "yfinance", "name": code,
            "price": float(price), "pct": (price / prev - 1) * 100 if prev else 0,
            "change": price - prev,
            "volume": float(info.get("last_volume", 0)),
            "amount": 0,
            "high": float(info.get("day_high", price)),
            "low": float(info.get("day_low", price)),
            "open": float(info.get("open", price)),
            "prev_close": float(prev),
            "amplitude": 0, "turnover": 0, "volume_ratio": 0,
        }

    # ---- 主入口：优先用上次成功的源，失败则切换 ----
    def get(self, code):
        # 优先尝试上次成功的源
        order = [self.last_ok_source] + [s for s in self.source_order
                                          if s != self.last_ok_source]
        for src in order:
            try:
                fn = getattr(self, f"_{src}")
                data = fn(code)
                if data and data.get("price", 0) > 0:
                    self.last_ok_source = src
                    return data
            except Exception as e:
                print(f"[{code}] {src} 数据源失败: {e}")
                continue
        return {}


# 全局单例
QUOTE = MultiSourceQuote()


# =====================================================================
# 综合买卖点评分系统（长短期结合）
# =====================================================================
class CompositeScorer:
    """
    多因子综合打分，输出 -100(强烈卖出) ~ +100(强烈买入)
    结合长短期、动量/反转、量价、形态、统计 多维度
    """

    # 因子权重（合计 100）
    WEIGHTS = {
        "trend":      20,   # 趋势（MA排列+MACD+Hurst）
        "momentum":   15,   # 动量（短中期动量+加速度）
        "reversal":   10,   # 反转（超买超卖+短期反转）
        "volume":     15,   # 量能（OFI+量比+大单+脉冲）
        "micro":      10,   # 微观结构（VWAP+VPIN+Kyle）
        "volatility": 10,   # 波动率（RV比+ATR+Boll位置）
        "stat":       10,   # 统计（自相关+偏度峰度）
        "structure":  10,   # 结构（Donchian+新高新低+双顶底）
    }

    def __init__(self, name: str):
        self.name = name
        self.last_score = 0
        self.last_detail = {}

    def score(self, daily_hist: pd.DataFrame, minute_df: pd.DataFrame) -> dict:
        """
        返回 {score, level, detail, suggestion}
        score: -100 ~ +100
        level: 强买/买入/观望/卖出/强卖
        suggestion: 操作建议
        """
        detail = {}
        s_trend = self._trend_score(daily_hist, minute_df, detail)
        s_mom = self._momentum_score(daily_hist, minute_df, detail)
        s_rev = self._reversal_score(daily_hist, minute_df, detail)
        s_vol = self._volume_score(daily_hist, minute_df, detail)
        s_micro = self._micro_score(minute_df, detail)
        s_vola = self._volatility_score(daily_hist, minute_df, detail)
        s_stat = self._stat_score(minute_df, detail)
        s_struct = self._structure_score(daily_hist, minute_df, detail)

        total = (s_trend * self.WEIGHTS["trend"]
                 + s_mom * self.WEIGHTS["momentum"]
                 + s_rev * self.WEIGHTS["reversal"]
                 + s_vol * self.WEIGHTS["volume"]
                 + s_micro * self.WEIGHTS["micro"]
                 + s_vola * self.WEIGHTS["volatility"]
                 + s_stat * self.WEIGHTS["stat"]
                 + s_struct * self.WEIGHTS["structure"]) / 100.0

        total = max(-100, min(100, total))
        self.last_score = total
        self.last_detail = detail

        if total >= 60:
            level, sug = "强烈买入", "多因子共振看多，建议建仓/加仓"
        elif total >= 25:
            level, sug = "买入", "偏多，可轻仓试多"
        elif total >= -25:
            level, sug = "观望", "信号中性，建议等待"
        elif total >= -60:
            level, sug = "卖出", "偏空，可减仓"
        else:
            level, sug = "强烈卖出", "多因子共振看空，建议清仓"

        # 风险收益比与建议止损止盈
        rr = self._risk_reward(daily_hist, minute_df, total)

        return {
            "score": total, "level": level, "suggestion": sug,
            "detail": detail, "risk_reward": rr,
        }

    # ---- 各维度评分（-100 ~ +100）----
    def _trend_score(self, hist, m, d):
        s = 0
        # 日K MA排列
        if len(hist) >= 60:
            c = hist["close"]
            ma5, ma10, ma20, ma60 = (calc_ma(c, n).iloc[-1] for n in (5, 10, 20, 60))
            p = c.iloc[-1]
            if ma5 > ma10 > ma20 > ma60:
                s += 50
                if p > ma5: s += 20
            elif ma5 < ma10 < ma20 < ma60:
                s -= 50
                if p < ma5: s -= 20
            else:
                s += (ma5 - ma20) / ma20 * 1000 if ma20 else 0
        # MACD方向
        if len(hist) >= 35:
            dif, dea, _ = calc_macd(hist["close"])
            if dif.iloc[-1] > dea.iloc[-1]: s += 15
            else: s -= 15
        # Hurst 趋势持续性
        if len(m) >= 60:
            h = hurst_rs(m["close"].pct_change().fillna(0), 50).iloc[-1]
            if not np.isnan(h):
                if h > 0.6: s += 15
                elif h < 0.4: s -= 15
        s = max(-100, min(100, s))
        d["trend"] = s
        return s

    def _momentum_score(self, hist, m, d):
        s = 0
        # 日K动量（20日）
        if len(hist) >= 21:
            r20 = hist["close"].iloc[-1] / hist["close"].iloc[-21] - 1
            s += np.clip(r20 * 800, -40, 40)
        # 分钟动量（5/10/20）
        for n in (5, 10, 20):
            if len(m) >= n + 1:
                r = m["close"].iloc[-1] / m["close"].iloc[-n-1] - 1
                s += np.clip(r * 500, -15, 15)
        # 动量加速
        if len(m) >= 20:
            r5 = m["close"].pct_change(5)
            accel = r5.diff().iloc[-1]
            if not np.isnan(accel):
                s += np.clip(accel * 1000, -10, 10)
        s = max(-100, min(100, s))
        d["momentum"] = s
        return s

    def _reversal_score(self, hist, m, d):
        s = 0
        # 日K RSI
        if len(hist) >= 15:
            r = calc_rsi(hist["close"]).iloc[-1]
            if r >= 80: s -= 30
            elif r >= 70: s -= 15
            elif r <= 20: s += 30
            elif r <= 30: s += 15
        # 分钟 RSI
        if len(m) >= 15:
            r = calc_rsi(m["close"], 14).iloc[-1]
            if r >= 85: s -= 25
            elif r <= 15: s += 25
        # 短期反转（5/10分钟超涨超跌）
        if len(m) >= 10:
            r5 = m["close"].pct_change(5).iloc[-1]
            r10 = m["close"].pct_change(10).iloc[-1]
            if r5 > 0.025 and r10 > 0.04: s -= 20
            elif r5 < -0.025 and r10 < -0.04: s += 20
        s = max(-100, min(100, s))
        d["reversal"] = s
        return s

    def _volume_score(self, hist, m, d):
        s = 0
        # 日K放量
        if len(hist) >= 6:
            avg5 = hist["volume"].iloc[-6:-1].mean()
            if avg5 > 0:
                ratio = hist["volume"].iloc[-1] / avg5
                # 价涨量增为正，价跌量增为负
                price_chg = hist["close"].iloc[-1] - hist["close"].iloc[-2]
                s += np.clip(ratio * (20 if price_chg > 0 else -20), -30, 30)
        # OFI
        if len(m) >= 20:
            sv = ofi(m["close"], m["volume"])
            net = sv.iloc[-20:].sum()
            total = m["volume"].iloc[-20:].sum()
            if total > 0:
                ratio = net / total
                s += np.clip(ratio * 100, -30, 30)
        # 量价相关
        if len(m) >= 30:
            r = m["close"].pct_change().fillna(0)
            corr = r.iloc[-30:].corr(m["volume"].iloc[-30:])
            if not np.isnan(corr):
                s += np.clip(corr * 30, -20, 20)
        s = max(-100, min(100, s))
        d["volume"] = s
        return s

    def _micro_score(self, m, d):
        s = 0
        if len(m) < 20: 
            d["micro"] = 0
            return 0
        # VWAP 偏离
        v = vwap(m["high"], m["low"], m["close"], m["volume"]).iloc[-1]
        p = m["close"].iloc[-1]
        if not np.isnan(v) and v > 0:
            dev = (p - v) / v
            s += np.clip(dev * 1000, -30, 30)
        # VPIN
        vp = vpin(m["close"], m["volume"], 10).iloc[-1]
        if not np.isnan(vp) and vp > 0.5:
            # 高 VPIN 配合方向
            recent_ret = m["close"].pct_change(5).iloc[-1]
            if not np.isnan(recent_ret):
                s += np.clip(recent_ret * 500, -20, 20)
        # Kyle Lambda 方向
        r = m["close"].pct_change().fillna(0)
        sv = ofi(m["close"], m["volume"])
        lam = kyle_lambda(r, sv, 30)
        if not np.isnan(lam):
            # lambda 负=买盘推动价格上涨（成交量正则价格涨）
            s += np.clip(-lam * 1e6, -20, 20)
        s = max(-100, min(100, s))
        d["micro"] = s
        return s

    def _volatility_score(self, hist, m, d):
        s = 0
        # 波动率放大 + 方向
        if len(m) >= 60:
            r = m["close"].pct_change().fillna(0)
            rv_s = r.iloc[-20:].std(); rv_l = r.iloc[-60:-20].std()
            if rv_l > 0:
                ratio = rv_s / rv_l
                # 波动放大时配合趋势方向
                mom = m["close"].iloc[-1] / m["close"].iloc[-20] - 1
                s += np.clip(mom * 500 * (1 if ratio > 1 else 0.5), -30, 30)
        # 布林带位置（日K）
        if len(hist) >= 20:
            up, mid, lo = calc_boll(hist["close"])
            p = hist["close"].iloc[-1]
            if up.iloc[-1] > lo.iloc[-1]:
                pos = (p - mid.iloc[-1]) / (up.iloc[-1] - mid.iloc[-1]) if up.iloc[-1] != mid.iloc[-1] else 0
                # 在上轨附近偏空，下轨附近偏多
                s += np.clip((0.5 - pos) * 40, -30, 30)
        s = max(-100, min(100, s))
        d["volatility"] = s
        return s

    def _stat_score(self, m, d):
        s = 0
        if len(m) < 30:
            d["stat"] = 0
            return 0
        r = m["close"].pct_change().iloc[-30:].dropna()
        if len(r) < 20:
            d["stat"] = 0
            return 0
        # 自相关：正=动量延续，负=反转
        ac = r.autocorr(lag=1)
        if not np.isnan(ac):
            # 配合当前方向
            cur = r.iloc[-1]
            if ac > 0.3:
                s += np.clip(cur * 1000, -40, 40)
            elif ac < -0.3:
                s += np.clip(-cur * 1000, -40, 40)
        # 偏度：右偏偏多，左偏偏空
        skew = r.skew()
        if not np.isnan(skew):
            s += np.clip(skew * 15, -20, 20)
        s = max(-100, min(100, s))
        d["stat"] = s
        return s

    def _structure_score(self, hist, m, d):
        s = 0
        # 日K新高新低
        n = 20
        if len(hist) >= n + 1:
            wh = hist["high"].iloc[-n-1:-1].max()
            wl = hist["low"].iloc[-n-1:-1].min()
            p = hist["close"].iloc[-1]
            if p >= wh: s += 30
            elif p <= wl: s -= 30
        # Donchian 突破（分钟）
        dn = 60
        if len(m) >= dn:
            up, lo = donchian_channel(m["high"], m["low"], dn)
            p = m["close"].iloc[-1]
            if p >= up.iloc[-2]: s += 25
            elif p <= lo.iloc[-2]: s -= 25
        # 双顶双底
        if len(m) >= 30:
            window = m.iloc[-30:]
            highs = window["high"].values; lows = window["low"].values
            idx = np.argmax(highs)
            if 5 <= idx <= 25:
                left = highs[:idx].max()
                right = highs[idx+1:].max() if len(highs) > idx+1 else 0
                if right > 0 and abs(left - right) / left < 0.003 and highs[-1] < min(left, right) * 0.998:
                    s -= 25
            idx = np.argmin(lows)
            if 5 <= idx <= 25:
                left = lows[:idx].min()
                right = lows[idx+1:].min() if len(lows) > idx+1 else 0
                if right > 0 and abs(left - right) / left < 0.003 and lows[-1] > max(left, right) * 1.002:
                    s += 25
        s = max(-100, min(100, s))
        d["structure"] = s
        return s

    # ---- 风险收益比与止损止盈 ----
    def _risk_reward(self, hist, m, score):
        """基于 ATR 计算止损止盈建议"""
        try:
            if len(hist) < 15:
                return {}
            atr_d = calc_atr(hist["high"], hist["low"], hist["close"]).iloc[-1]
            price = hist["close"].iloc[-1]
            # 方向：score>0 多头，<0 空头
            if score >= 0:
                stop = price - 1.5 * atr_d
                target1 = price + 2.0 * atr_d
                target2 = price + 3.5 * atr_d
                direction = "多头"
            else:
                stop = price + 1.5 * atr_d
                target1 = price - 2.0 * atr_d
                target2 = price - 3.5 * atr_d
                direction = "空头"
            rr = abs(target1 - price) / abs(price - stop) if price != stop else 0
            # 凯利公式简化仓位（假设胜率与score挂钩）
            win_rate = 0.5 + score / 200  # score=100 -> 1.0, score=0 -> 0.5
            win_rate = max(0.1, min(0.9, win_rate))
            kelly = win_rate - (1 - win_rate) / rr if rr > 0 else 0
            kelly = max(0, min(0.5, kelly))  # 最多半仓
            return {
                "direction": direction,
                "entry": round(price, 2),
                "stop_loss": round(stop, 2),
                "target1": round(target1, 2),
                "target2": round(target2, 2),
                "risk_reward": round(rr, 2),
                "kelly_position": f"{kelly*100:.0f}%",
                "atr": round(atr_d, 3),
            }
        except Exception:
            return {}


# =====================================================================
# 日K检测器（保留原版）
# =====================================================================
class DailyDetector:
    def __init__(self, code, name):
        self.code = code
        self.name = name
        self.history = pd.DataFrame()
        self.last_alert_time = {}

    def load_history(self):
        try:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=HISTORY_DAYS * 2)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(symbol=self.code, period="daily",
                                    start_date=start, end_date=end, adjust="qfq")
            if df is None or df.empty:
                return False
            df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                               "最高": "high", "最低": "low",
                               "成交量": "volume", "成交额": "amount"}, inplace=True)
            for c in ["open", "close", "high", "low", "volume", "amount"]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["date"] = pd.to_datetime(df["date"])
            df.sort_values("date", inplace=True)
            df.reset_index(drop=True, inplace=True)
            self.history = df
            return True
        except Exception as e:
            print(f"[{self.code}] 日K加载失败: {e}")
            return False

    def get_realtime(self):
        """通过多数据源聚合器获取实时行情"""
        data = QUOTE.get(self.code)
        if data:
            if data.get("name"):
                self.name = data["name"]
            return data
        return {}

    def detect(self):
        out = []
        if self.history.empty and not self.load_history():
            return out
        rt = self.get_realtime()
        if not rt:
            return out
        hist = self.history.copy()
        today = {"date": pd.Timestamp.now(), "open": rt["open"], "high": rt["high"],
                 "low": rt["low"], "close": rt["price"],
                 "volume": rt["volume"], "amount": rt["amount"]}
        if not hist.empty and hist.iloc[-1]["date"].date() == datetime.now().date():
            i = hist.index[-1]
            hist.loc[i, "close"] = rt["price"]
            hist.loc[i, "high"] = rt["high"]
            hist.loc[i, "low"] = rt["low"]
            hist.loc[i, "volume"] = rt["volume"]
            hist.loc[i, "amount"] = rt["amount"]
        else:
            hist = pd.concat([hist, pd.DataFrame([today])], ignore_index=True)

        out += self._price(rt)
        out += self._volume(rt, hist)
        out += self._ma(hist)
        out += self._macd(hist)
        out += self._rsi(hist)
        out += self._kdj(hist)
        out += self._boll(hist, rt)
        out += self._atr(hist)
        out += self._new_hl(hist)
        out += self._consec(hist)
        out += self._gap(hist)
        out += self._diverge(hist)
        out += self._limit(rt)
        out += self._big_amt(hist, rt)
        out += self._vwap(rt)
        return self._dedup(out)

    def _dedup(self, signals):
        now = time.time()
        out = []
        for s in signals:
            last = self.last_alert_time.get(s["key"], 0)
            if now - last > 300:
                out.append(s)
                self.last_alert_time[s["key"]] = now
        return out

    def _price(self, rt):
        out = []
        if abs(rt["pct"]) >= THRESHOLDS["pct_change"] * 100:
            d = "大涨" if rt["pct"] > 0 else "大跌"
            out.append({"key": f"pct_{d}", "level": "高",
                        "title": f"[{self.name} 日K] {d}",
                        "msg": f"涨跌幅 {rt['pct']:.2f}%，现价 {rt['price']}"})
        if rt["amplitude"] >= THRESHOLDS["amplitude"] * 100:
            out.append({"key": "amp", "level": "中",
                        "title": f"[{self.name} 日K] 振幅放大",
                        "msg": f"振幅 {rt['amplitude']:.2f}%"})
        return out

    def _volume(self, rt, hist):
        out = []
        if rt["volume_ratio"] >= THRESHOLDS["volume_ratio"]:
            out.append({"key": "vr", "level": "中",
                        "title": f"[{self.name} 日K] 量比突变",
                        "msg": f"量比 {rt['volume_ratio']:.2f}"})
        if len(hist) >= 6:
            avg5 = hist["volume"].iloc[-6:-1].mean()
            if avg5 > 0 and rt["volume"] / avg5 >= THRESHOLDS["volume_surge"]:
                out.append({"key": "vs", "level": "高",
                            "title": f"[{self.name} 日K] 放量",
                            "msg": f"放量 {rt['volume']/avg5:.2f} 倍"})
        return out

    def _ma(self, hist):
        out = []
        if len(hist) < 60: return out
        c = hist["close"]; p = c.iloc[-1]
        for n in (5, 10, 20, 60):
            ma = calc_ma(c, n).iloc[-1]; pm = calc_ma(c, n).iloc[-2]; pp = c.iloc[-2]
            if pp <= pm and p > ma:
                out.append({"key": f"ma{n}u", "level": "中",
                            "title": f"[{self.name} 日K] 突破MA{n}",
                            "msg": f"{p:.2f} 上穿 MA{n}({ma:.2f})"})
            elif pp >= pm and p < ma:
                out.append({"key": f"ma{n}d", "level": "中",
                            "title": f"[{self.name} 日K] 跌破MA{n}",
                            "msg": f"{p:.2f} 下穿 MA{n}({ma:.2f})"})
        m5, m10, m20, m60 = (calc_ma(c, n).iloc[-1] for n in (5, 10, 20, 60))
        if m5 > m10 > m20 > m60 and p > m5:
            out.append({"key": "mabull", "level": "中",
                        "title": f"[{self.name} 日K] 多头排列", "msg": "强势多头"})
        if m5 < m10 < m20 < m60 and p < m5:
            out.append({"key": "mabear", "level": "中",
                        "title": f"[{self.name} 日K] 空头排列", "msg": "弱势空头"})
        return out

    def _macd(self, hist):
        out = []
        if len(hist) < 35: return out
        dif, dea, _ = calc_macd(hist["close"])
        if dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
            out.append({"key": "macdg", "level": "高",
                        "title": f"[{self.name} 日K] MACD金叉",
                        "msg": f"DIF {dif.iloc[-1]:.3f} 上穿 DEA {dea.iloc[-1]:.3f}"})
        elif dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
            out.append({"key": "macdd", "level": "高",
                        "title": f"[{self.name} 日K] MACD死叉",
                        "msg": f"DIF {dif.iloc[-1]:.3f} 下穿 DEA {dea.iloc[-1]:.3f}"})
        return out

    def _rsi(self, hist):
        out = []
        if len(hist) < 15: return out
        r = calc_rsi(hist["close"]).iloc[-1]
        if r >= THRESHOLDS["rsi_overbought"]:
            out.append({"key": "rsio", "level": "中",
                        "title": f"[{self.name} 日K] RSI超买", "msg": f"RSI={r:.1f}"})
        elif r <= THRESHOLDS["rsi_oversold"]:
            out.append({"key": "rsiu", "level": "中",
                        "title": f"[{self.name} 日K] RSI超卖", "msg": f"RSI={r:.1f}"})
        return out

    def _kdj(self, hist):
        out = []
        if len(hist) < 10: return out
        k, d, j = calc_kdj(hist["high"], hist["low"], hist["close"])
        if k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
            out.append({"key": "kdjg", "level": "中",
                        "title": f"[{self.name} 日K] KDJ金叉",
                        "msg": f"K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f} J={j.iloc[-1]:.1f}"})
        elif k.iloc[-2] >= d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
            out.append({"key": "kdjd", "level": "中",
                        "title": f"[{self.name} 日K] KDJ死叉",
                        "msg": f"K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f} J={j.iloc[-1]:.1f}"})
        return out

    def _boll(self, hist, rt):
        out = []
        if len(hist) < 20: return out
        up, _, lo = calc_boll(hist["close"])
        if rt["price"] > up.iloc[-1]:
            out.append({"key": "bollu", "level": "中",
                        "title": f"[{self.name} 日K] 突破布林上轨",
                        "msg": f"{rt['price']:.2f} > {up.iloc[-1]:.2f}"})
        elif rt["price"] < lo.iloc[-1]:
            out.append({"key": "bolld", "level": "中",
                        "title": f"[{self.name} 日K] 跌破布林下轨",
                        "msg": f"{rt['price']:.2f} < {lo.iloc[-1]:.2f}"})
        return out

    def _atr(self, hist):
        out = []
        if len(hist) < 15: return out
        a = calc_atr(hist["high"], hist["low"], hist["close"])
        if a.iloc[-1] / a.iloc[-15:-1].mean() >= THRESHOLDS["atr_ratio"]:
            out.append({"key": "atr", "level": "中",
                        "title": f"[{self.name} 日K] 波动率放大",
                        "msg": f"ATR {a.iloc[-1]:.3f}"})
        return out

    def _new_hl(self, hist):
        out = []
        n = THRESHOLDS["new_high_low_days"]
        if len(hist) < n + 1: return out
        wh = hist["high"].iloc[-n-1:-1].max()
        wl = hist["low"].iloc[-n-1:-1].min()
        p = hist["close"].iloc[-1]
        if p >= wh:
            out.append({"key": "nh", "level": "高",
                        "title": f"[{self.name} 日K] 创{n}日新高", "msg": f"{p:.2f}"})
        if p <= wl:
            out.append({"key": "nl", "level": "高",
                        "title": f"[{self.name} 日K] 创{n}日新低", "msg": f"{p:.2f}"})
        return out

    def _consec(self, hist):
        out = []
        n = THRESHOLDS["consecutive_days"]
        if len(hist) < n + 1: return out
        r = hist["close"].iloc[-n-1:]
        d = r.diff().dropna()
        if (d > 0).all():
            out.append({"key": "cu", "level": "中",
                        "title": f"[{self.name} 日K] 连{n}阳",
                        "msg": f"涨 {(r.iloc[-1]/r.iloc[0]-1)*100:.2f}%"})
        elif (d < 0).all():
            out.append({"key": "cd", "level": "中",
                        "title": f"[{self.name} 日K] 连{n}阴",
                        "msg": f"跌 {(r.iloc[-1]/r.iloc[0]-1)*100:.2f}%"})
        return out

    def _gap(self, hist):
        out = []
        if len(hist) < 2: return out
        pc = hist["close"].iloc[-2]; to = hist["open"].iloc[-1]
        if to > pc * 1.02:
            out.append({"key": "gu", "level": "中",
                        "title": f"[{self.name} 日K] 向上跳空",
                        "msg": f"缺口 {(to/pc-1)*100:.2f}%"})
        elif to < pc * 0.98:
            out.append({"key": "gd", "level": "中",
                        "title": f"[{self.name} 日K] 向下跳空",
                        "msg": f"缺口 {(to/pc-1)*100:.2f}%"})
        return out

    def _diverge(self, hist):
        out = []
        if len(hist) < 5: return out
        pc = hist["close"].iloc[-1] / hist["close"].iloc[-5] - 1
        vc = hist["volume"].iloc[-1] / (hist["volume"].iloc[-5:-1].mean() + 1) - 1
        if pc > 0.03 and vc < -0.2:
            out.append({"key": "divt", "level": "中",
                        "title": f"[{self.name} 日K] 量价背离(顶)", "msg": "价涨量缩"})
        elif pc < -0.03 and vc > 0.2:
            out.append({"key": "divb", "level": "中",
                        "title": f"[{self.name} 日K] 量价背离(底)", "msg": "价跌量增"})
        return out

    def _limit(self, rt):
        out = []
        if rt["prev_close"] <= 0: return out
        lp = THRESHOLDS["limit_pct"]
        if self.code[0] in ("3", "6") or self.code.startswith("68"):
            lp = 0.195
        up = rt["prev_close"] * (1 + lp); dn = rt["prev_close"] * (1 - lp)
        if rt["price"] >= up * 0.995:
            out.append({"key": "lu", "level": "高",
                        "title": f"[{self.name} 日K] 接近涨停", "msg": f"≈{up:.2f}"})
        elif rt["price"] <= dn * 1.005:
            out.append({"key": "ld", "level": "高",
                        "title": f"[{self.name} 日K] 接近跌停", "msg": f"≈{dn:.2f}"})
        return out

    def _big_amt(self, hist, rt):
        out = []
        if len(hist) < 6: return out
        avg = hist["amount"].iloc[-6:-1].mean()
        if avg > 0 and rt["amount"] / avg >= THRESHOLDS["big_amount_ratio"]:
            out.append({"key": "ba", "level": "中",
                        "title": f"[{self.name} 日K] 成交额异动",
                        "msg": f"{rt['amount']/avg:.2f} 倍"})
        return out

    def _vwap(self, rt):
        out = []
        if rt["volume"] <= 0: return out
        v = (rt["high"] + rt["low"] + rt["price"]) / 3.0
        d = (rt["price"] - v) / v
        if d > THRESHOLDS["vwap_dev"]:
            out.append({"key": "vwu", "level": "低",
                        "title": f"[{self.name} 日K] 突破分时均价", "msg": f"偏离 {d*100:.2f}%"})
        elif d < -THRESHOLDS["vwap_dev"]:
            out.append({"key": "vwd", "level": "低",
                        "title": f"[{self.name} 日K] 跌破分时均价", "msg": f"偏离 {d*100:.2f}%"})
        return out


# =====================================================================
# 分钟级高频检测器
# =====================================================================
class MinuteDetector:
    """基于分钟K线的高频 alpha 因子检测器"""

    def __init__(self, code, name):
        self.code = code
        self.name = name
        self.minutes: pd.DataFrame = pd.DataFrame()
        self.last_alert_time = {}
        self.scorer = CompositeScorer(name)
        self.daily_hist: pd.DataFrame = pd.DataFrame()  # 由外部注入日K
        self.last_composite_alert = 0

    def load_minutes(self):
        try:
            df = ak.stock_zh_a_hist_min_em(
                symbol=self.code, period=MINUTE_PERIOD,
                start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
                end_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                adjust="qfq"
            )
            if df is None or df.empty:
                return False
            df.rename(columns={"时间": "datetime", "开盘": "open", "收盘": "close",
                               "最高": "high", "最低": "low",
                               "成交量": "volume", "成交额": "amount"}, inplace=True)
            for c in ["open", "close", "high", "low", "volume", "amount"]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.sort_values("datetime", inplace=True)
            df.reset_index(drop=True, inplace=True)
            df = df.tail(MINUTE_BARS).reset_index(drop=True)
            self.minutes = df
            return True
        except Exception as e:
            print(f"[{self.code}] 分钟K加载失败: {e}")
            return False

    def detect(self):
        out = []
        if not self.load_minutes():
            return out
        if len(self.minutes) < 30:
            return out

        m = self.minutes.copy()
        out += self._vwap_dev(m)
        out += self._twap_dev(m)
        out += self._ofi(m)
        out += self._kyle_lambda(m)
        out += self._amihud(m)
        out += self._buy_sell_force(m)
        out += self._vpin(m)
        out += self._momentum(m)
        out += self._mom_accel(m)
        out += self._zscore_jump(m)
        out += self._reversal(m)
        out += self._rv_ratio(m)
        out += self._min_atr(m)
        out += self._min_boll(m)
        out += self._min_vol_ratio(m)
        out += self._vol_pulse(m)
        out += self._herfindahl(m)
        out += self._vol_price_corr(m)
        out += self._big_order(m)
        out += self._donchian(m)
        out += self._min_ma(m)
        out += self._min_macd(m)
        out += self._min_rsi(m)
        out += self._min_kdj(m)
        out += self._double_top_bottom(m)
        out += self._hurst(m)
        out += self._skew_kurt(m)
        out += self._autocorr(m)
        # 综合买卖点评分
        out += self._composite_score(m)
        return self._dedup(out)

    def _composite_score(self, m):
        """综合买卖点评分：长短期结合，输出操作建议"""
        out = []
        if self.daily_hist.empty or len(self.daily_hist) < 30:
            return out
        try:
            result = self.scorer.score(self.daily_hist, m)
        except Exception as e:
            print(f"[{self.code}] 综合评分异常: {e}")
            return out

        score = result["score"]
        level = result["level"]
        rr = result.get("risk_reward", {})
        now = time.time()
        # 仅在评分跨阈值或方向反转时弹窗，且 5 分钟内不重复
        prev = self.scorer.last_score
        should_alert = False
        if abs(score) >= 60 and now - self.last_composite_alert > 300:
            should_alert = True
        elif abs(score - prev) >= 40 and now - self.last_composite_alert > 300:
            should_alert = True  # 评分剧变
        if not should_alert:
            return out

        self.last_composite_alert = now
        detail = result["detail"]
        detail_str = " | ".join(f"{k}:{v:.0f}" for k, v in detail.items())
        msg = (f"综合评分 {score:.0f} [{level}]\n"
               f"建议：{result['suggestion']}\n"
               f"分项：{detail_str}\n")
        if rr:
            msg += (f"\n操作建议（{rr.get('direction','')}）：\n"
                    f"  入场：{rr.get('entry')}\n"
                    f"  止损：{rr.get('stop_loss')}\n"
                    f"  目标1：{rr.get('target1')}\n"
                    f"  目标2：{rr.get('target2')}\n"
                    f"  风险收益比：{rr.get('risk_reward')}\n"
                    f"  建议仓位(凯利)：{rr.get('kelly_position')}\n"
                    f"  ATR：{rr.get('atr')}")
        out.append({
            "key": f"composite_{level}",
            "level": "高" if abs(score) >= 60 else "中",
            "title": f"[{self.name} 综合评分] {level} (score={score:.0f})",
            "msg": msg,
        })
        return out

    def _dedup(self, signals):
        now = time.time()
        out = []
        for s in signals:
            last = self.last_alert_time.get(s["key"], 0)
            # 高频信号去重时间窗缩短到 3 分钟
            if now - last > 180:
                out.append(s)
                self.last_alert_time[s["key"]] = now
        return out

    # ---------- 微观结构 ----------
    def _vwap_dev(self, m):
        out = []
        v = vwap(m["high"], m["low"], m["close"], m["volume"]).iloc[-1]
        p = m["close"].iloc[-1]
        if np.isnan(v) or v == 0: return out
        d = (p - v) / v
        if d > THRESHOLDS["vwap_dev"]:
            out.append({"key": "mvwap_u", "level": "高",
                        "title": f"[{self.name} 分钟] VWAP上方突破",
                        "msg": f"价 {p:.2f} > VWAP {v:.2f}，偏离 {d*100:.2f}%"})
        elif d < -THRESHOLDS["vwap_dev"]:
            out.append({"key": "mvwap_d", "level": "高",
                        "title": f"[{self.name} 分钟] VWAP下方跌破",
                        "msg": f"价 {p:.2f} < VWAP {v:.2f}，偏离 {d*100:.2f}%"})
        return out

    def _twap_dev(self, m):
        out = []
        t = twap(m["close"]).iloc[-1]
        p = m["close"].iloc[-1]
        if t == 0: return out
        d = (p - t) / t
        if d > THRESHOLDS["twap_dev"]:
            out.append({"key": "mtwap_u", "level": "中",
                        "title": f"[{self.name} 分钟] 突破TWAP",
                        "msg": f"价 {p:.2f} > TWAP {t:.2f}，偏离 {d*100:.2f}%"})
        elif d < -THRESHOLDS["twap_dev"]:
            out.append({"key": "mtwap_d", "level": "中",
                        "title": f"[{self.name} 分钟] 跌破TWAP",
                        "msg": f"价 {p:.2f} < TWAP {t:.2f}，偏离 {d*100:.2f}%"})
        return out

    def _ofi(self, m):
        """订单流不平衡：近期净买/总成交"""
        out = []
        sv = ofi(m["close"], m["volume"])
        n = 20
        net = sv.iloc[-n:].sum()
        total = m["volume"].iloc[-n:].sum()
        if total == 0: return out
        ratio = net / total
        if ratio > THRESHOLDS["ofi_ratio"]:
            out.append({"key": "ofi_b", "level": "高",
                        "title": f"[{self.name} 分钟] OFI主动买盘",
                        "msg": f"近{n}分钟净买占比 {ratio*100:.1f}%"})
        elif ratio < -THRESHOLDS["ofi_ratio"]:
            out.append({"key": "ofi_s", "level": "高",
                        "title": f"[{self.name} 分钟] OFI主动卖盘",
                        "msg": f"近{n}分钟净卖占比 {ratio*100:.1f}%"})
        return out

    def _kyle_lambda(self, m):
        """Kyle's Lambda：价格冲击系数突变"""
        out = []
        r = m["close"].pct_change().fillna(0)
        sv = ofi(m["close"], m["volume"])
        lam_now = kyle_lambda(r, sv, 30)
        if np.isnan(lam_now): return out
        # 用更早期 30 根做基准
        if len(r) >= 60:
            lam_base = kyle_lambda(r.iloc[-60:-30], sv.iloc[-60:-30], 30)
            if not np.isnan(lam_base) and lam_base != 0:
                ratio = abs(lam_now) / abs(lam_base)
                if ratio >= 3 and abs(lam_now) > 1e-7:
                    out.append({"key": "kyle", "level": "中",
                                "title": f"[{self.name} 分钟] 价格冲击系数放大",
                                "msg": f"Lambda {lam_now:.2e}，基准 {lam_base:.2e}，"
                                       f"放大 {ratio:.1f} 倍"})
        return out

    def _amihud(self, m):
        """Amihud 非流动性飙升"""
        out = []
        r = m["close"].pct_change().fillna(0)
        ill = amihud_illiquidity(r, m["amount"], 20)
        if len(ill) < 40: return out
        now = ill.iloc[-1]; avg = ill.iloc[-40:-20].mean()
        if np.isnan(now) or np.isnan(avg) or avg == 0: return out
        if now / avg >= 3:
            out.append({"key": "amihud", "level": "中",
                        "title": f"[{self.name} 分钟] 流动性骤降",
                        "msg": f"Amihud {now:.2e}，基准 {avg:.2e}，"
                               f"放大 {now/avg:.1f} 倍"})
        return out

    def _buy_sell_force(self, m):
        """买卖力道：(上涨分钟-下跌分钟)/总分钟"""
        out = []
        n = 30
        if len(m) < n: return out
        diff = m["close"].diff().iloc[-n:]
        up = (diff > 0).sum(); dn = (diff < 0).sum()
        force = (up - dn) / n
        if force > THRESHOLDS["buy_sell_force"]:
            out.append({"key": "bsf_u", "level": "中",
                        "title": f"[{self.name} 分钟] 买盘力道强",
                        "msg": f"近{n}分钟上涨 {up} 根，下跌 {dn} 根，力道 {force*100:.0f}%"})
        elif force < -THRESHOLDS["buy_sell_force"]:
            out.append({"key": "bsf_d", "level": "中",
                        "title": f"[{self.name} 分钟] 卖盘力道强",
                        "msg": f"近{n}分钟上涨 {up} 根，下跌 {dn} 根，力道 {force*100:.0f}%"})
        return out

    def _vpin(self, m):
        """VPIN 简化版"""
        out = []
        v = vpin(m["close"], m["volume"], 10).iloc[-1]
        if np.isnan(v): return out
        if v > THRESHOLDS["vpin_high"]:
            out.append({"key": "vpin", "level": "高",
                        "title": f"[{self.name} 分钟] VPIN知情交易预警",
                        "msg": f"VPIN={v:.2f}，知情交易概率高"})
        return out

    # ---------- 动量/反转 ----------
    def _momentum(self, m):
        out = []
        for n in (5, 10, 20):
            if len(m) < n + 1: continue
            r = m["close"].iloc[-1] / m["close"].iloc[-n-1] - 1
            if r > THRESHOLDS["mom_short"]:
                out.append({"key": f"mom_u{n}", "level": "中",
                            "title": f"[{self.name} 分钟] {n}分钟动量上攻",
                            "msg": f"{n}分钟涨幅 {r*100:.2f}%"})
            elif r < -THRESHOLDS["mom_short"]:
                out.append({"key": f"mom_d{n}", "level": "中",
                            "title": f"[{self.name} 分钟] {n}分钟动量下杀",
                            "msg": f"{n}分钟跌幅 {r*100:.2f}%"})
        return out

    def _mom_accel(self, m):
        """动量加速：动量的一阶差分"""
        out = []
        if len(m) < 20: return out
        r5 = m["close"].pct_change(5)
        accel = r5.diff()
        a = accel.iloc[-1]
        if a > THRESHOLDS["mom_accel"]:
            out.append({"key": "accel_u", "level": "中",
                        "title": f"[{self.name} 分钟] 动量加速向上",
                        "msg": f"加速度 {a*100:.2f}%"})
        elif a < -THRESHOLDS["mom_accel"]:
            out.append({"key": "accel_d", "level": "中",
                        "title": f"[{self.name} 分钟] 动量加速向下",
                        "msg": f"加速度 {a*100:.2f}%"})
        return out

    def _zscore_jump(self, m):
        """价格跳跃 Z-score"""
        out = []
        if len(m) < 30: return out
        r = m["close"].pct_change().iloc[-30:]
        mu, sigma = r.mean(), r.std()
        if sigma == 0: return out
        z = (r.iloc[-1] - mu) / sigma
        if abs(z) >= THRESHOLDS["zscore_jump"]:
            d = "向上跳跃" if z > 0 else "向下跳跃"
            out.append({"key": f"jump_{'u' if z>0 else 'd'}", "level": "高",
                        "title": f"[{self.name} 分钟] 价格{d}",
                        "msg": f"Z-score={z:.2f}，本分钟收益 {r.iloc[-1]*100:.2f}%"})
        return out

    def _reversal(self, m):
        """短期反转：5分钟累计涨幅过大"""
        out = []
        if len(m) < 10: return out
        r5 = m["close"].pct_change(5).iloc[-1]
        r10 = m["close"].pct_change(10).iloc[-1]
        if r5 > 0.025 and r10 > 0.04:
            out.append({"key": "rev_top", "level": "中",
                        "title": f"[{self.name} 分钟] 短期超涨反转预警",
                        "msg": f"5分钟 {r5*100:.2f}%，10分钟 {r10*100:.2f}%"})
        elif r5 < -0.025 and r10 < -0.04:
            out.append({"key": "rev_bot", "level": "中",
                        "title": f"[{self.name} 分钟] 短期超跌反弹预警",
                        "msg": f"5分钟 {r5*100:.2f}%，10分钟 {r10*100:.2f}%"})
        return out

    # ---------- 波动率 ----------
    def _rv_ratio(self, m):
        """短期/长期已实现波动率比"""
        out = []
        r = m["close"].pct_change().fillna(0)
        if len(r) < 60: return out
        rv_s = r.iloc[-20:].std()
        rv_l = r.iloc[-60:-20].std()
        if rv_l == 0: return out
        ratio = rv_s / rv_l
        if ratio >= THRESHOLDS["rv_ratio"]:
            out.append({"key": "rv", "level": "中",
                        "title": f"[{self.name} 分钟] 波动率放大",
                        "msg": f"短期波动率 {rv_s:.4f}，长期 {rv_l:.4f}，比 {ratio:.2f}"})
        return out

    def _min_atr(self, m):
        out = []
        if len(m) < 15: return out
        a = calc_atr(m["high"], m["low"], m["close"], 14)
        if len(a) < 30: return out
        if a.iloc[-1] / a.iloc[-30:-1].mean() >= THRESHOLDS["rv_ratio"]:
            out.append({"key": "matr", "level": "中",
                        "title": f"[{self.name} 分钟] 分钟ATR放大",
                        "msg": f"ATR {a.iloc[-1]:.3f}"})
        return out

    def _min_boll(self, m):
        out = []
        if len(m) < 20: return out
        up, _, lo = calc_boll(m["close"], 20, 2)
        p = m["close"].iloc[-1]
        if p > up.iloc[-1]:
            out.append({"key": "mboll_u", "level": "中",
                        "title": f"[{self.name} 分钟] 突破分钟布林上轨",
                        "msg": f"{p:.2f} > {up.iloc[-1]:.2f}"})
        elif p < lo.iloc[-1]:
            out.append({"key": "mboll_d", "level": "中",
                        "title": f"[{self.name} 分钟] 跌破分钟布林下轨",
                        "msg": f"{p:.2f} < {lo.iloc[-1]:.2f}"})
        return out

    # ---------- 量能 ----------
    def _min_vol_ratio(self, m):
        """分钟级量比：当前分钟量 / 近20分钟均量"""
        out = []
        if len(m) < 21: return out
        v = m["volume"].iloc[-1]
        avg = m["volume"].iloc[-21:-1].mean()
        if avg == 0: return out
        ratio = v / avg
        if ratio >= THRESHOLDS["min_vol_ratio"]:
            out.append({"key": "mvr", "level": "中",
                        "title": f"[{self.name} 分钟] 分钟量比放大",
                        "msg": f"量比 {ratio:.2f}，本分钟 {v:.0f}，均量 {avg:.0f}"})
        return out

    def _vol_pulse(self, m):
        """单分钟成交量脉冲"""
        out = []
        if len(m) < 20: return out
        v = m["volume"].iloc[-1]
        avg = m["volume"].iloc[-20:-1].mean()
        std = m["volume"].iloc[-20:-1].std()
        if avg == 0 or std == 0: return out
        z = (v - avg) / std
        if z >= THRESHOLDS["vol_pulse"]:
            out.append({"key": "pulse", "level": "高",
                        "title": f"[{self.name} 分钟] 成交量脉冲",
                        "msg": f"本分钟量 {v:.0f}，Z-score={z:.1f}，"
                               f"是均量 {v/avg:.1f} 倍"})
        return out

    def _herfindahl(self, m):
        """成交集中度"""
        out = []
        if len(m) < 30: return out
        h = herfindahl(m["volume"], 30).iloc[-1]
        if np.isnan(h): return out
        if h > THRESHOLDS["herfindahl"]:
            out.append({"key": "herf", "level": "中",
                        "title": f"[{self.name} 分钟] 成交高度集中",
                        "msg": f"Herfindahl={h:.3f}，资金集中入场"})
        return out

    def _vol_price_corr(self, m):
        """量价相关系数突变"""
        out = []
        if len(m) < 30: return out
        r = m["close"].pct_change().fillna(0)
        corr = r.iloc[-30:].corr(m["volume"].iloc[-30:])
        if np.isnan(corr): return out
        if corr > 0.6:
            out.append({"key": "vpc_p", "level": "中",
                        "title": f"[{self.name} 分钟] 量价同步上涨",
                        "msg": f"近30分钟量价相关 {corr:.2f}"})
        elif corr < -0.6:
            out.append({"key": "vpc_n", "level": "中",
                        "title": f"[{self.name} 分钟] 量价背离",
                        "msg": f"近30分钟量价相关 {corr:.2f}"})
        return out

    def _big_order(self, m):
        """大单占比：成交额分位检测"""
        out = []
        if len(m) < 30: return out
        amt = m["amount"].iloc[-30:]
        q90 = amt.quantile(0.9)
        big = (amt >= q90).sum()
        ratio = big / 30
        if ratio >= THRESHOLDS["big_order_pct"]:
            out.append({"key": "big", "level": "中",
                        "title": f"[{self.name} 分钟] 大单密集出现",
                        "msg": f"近30分钟大单占比 {ratio*100:.0f}%"})
        return out

    # ---------- 形态 ----------
    def _donchian(self, m):
        out = []
        n = THRESHOLDS["donchian_n"]
        if len(m) < n: return out
        up, lo = donchian_channel(m["high"], m["low"], n)
        p = m["close"].iloc[-1]
        # 排除当前根
        if p >= up.iloc[-2]:
            out.append({"key": "don_u", "level": "高",
                        "title": f"[{self.name} 分钟] 突破{n}分钟高点",
                        "msg": f"{p:.2f} > {up.iloc[-2]:.2f}"})
        elif p <= lo.iloc[-2]:
            out.append({"key": "don_d", "level": "高",
                        "title": f"[{self.name} 分钟] 跌破{n}分钟低点",
                        "msg": f"{p:.2f} < {lo.iloc[-2]:.2f}"})
        return out

    def _min_ma(self, m):
        out = []
        if len(m) < 30: return out
        c = m["close"]; p = c.iloc[-1]
        for n in (5, 10, 20):
            if len(c) < n + 1: continue
            ma = calc_ma(c, n).iloc[-1]; pm = calc_ma(c, n).iloc[-2]; pp = c.iloc[-2]
            if pp <= pm and p > ma:
                out.append({"key": f"mma{n}u", "level": "中",
                            "title": f"[{self.name} 分钟] 突破MA{n}",
                            "msg": f"{p:.2f} 上穿 MA{n}({ma:.2f})"})
            elif pp >= pm and p < ma:
                out.append({"key": f"mma{n}d", "level": "中",
                            "title": f"[{self.name} 分钟] 跌破MA{n}",
                            "msg": f"{p:.2f} 下穿 MA{n}({ma:.2f})"})
        return out

    def _min_macd(self, m):
        out = []
        if len(m) < 35: return out
        dif, dea, _ = calc_macd(m["close"])
        if dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
            out.append({"key": "mmacdg", "level": "高",
                        "title": f"[{self.name} 分钟] MACD金叉",
                        "msg": f"DIF {dif.iloc[-1]:.3f} 上穿 DEA {dea.iloc[-1]:.3f}"})
        elif dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
            out.append({"key": "mmacdd", "level": "高",
                        "title": f"[{self.name} 分钟] MACD死叉",
                        "msg": f"DIF {dif.iloc[-1]:.3f} 下穿 DEA {dea.iloc[-1]:.3f}"})
        return out

    def _min_rsi(self, m):
        out = []
        if len(m) < 15: return out
        r = calc_rsi(m["close"], 14).iloc[-1]
        if r >= 85:
            out.append({"key": "mrsi_o", "level": "中",
                        "title": f"[{self.name} 分钟] RSI极度超买",
                        "msg": f"RSI={r:.1f}"})
        elif r <= 15:
            out.append({"key": "mrsi_u", "level": "中",
                        "title": f"[{self.name} 分钟] RSI极度超卖",
                        "msg": f"RSI={r:.1f}"})
        return out

    def _min_kdj(self, m):
        out = []
        if len(m) < 10: return out
        k, d, j = calc_kdj(m["high"], m["low"], m["close"])
        if k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
            out.append({"key": "mkdjg", "level": "中",
                        "title": f"[{self.name} 分钟] KDJ金叉",
                        "msg": f"K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f} J={j.iloc[-1]:.1f}"})
        elif k.iloc[-2] >= d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
            out.append({"key": "mkdjd", "level": "中",
                        "title": f"[{self.name} 分钟] KDJ死叉",
                        "msg": f"K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f} J={j.iloc[-1]:.1f}"})
        return out

    def _double_top_bottom(self, m):
        """分钟级双顶/双底"""
        out = []
        if len(m) < 30: return out
        window = m.iloc[-30:]
        highs = window["high"].values
        lows = window["low"].values
        # 简化：找两个相近的高点
        idx_max = np.argmax(highs)
        if 5 <= idx_max <= 25:
            left = highs[:idx_max].max()
            right = highs[idx_max+1:].max() if len(highs) > idx_max+1 else 0
            if right > 0 and abs(left - right) / left < 0.003 and highs[-1] < min(left, right) * 0.998:
                out.append({"key": "mdt", "level": "中",
                            "title": f"[{self.name} 分钟] 双顶形态",
                            "msg": f"双顶高点 ≈{left:.2f}"})
        idx_min = np.argmin(lows)
        if 5 <= idx_min <= 25:
            left = lows[:idx_min].min()
            right = lows[idx_min+1:].min() if len(lows) > idx_min+1 else 0
            if right > 0 and abs(left - right) / left < 0.003 and lows[-1] > max(left, right) * 1.002:
                out.append({"key": "mdb", "level": "中",
                            "title": f"[{self.name} 分钟] 双底形态",
                            "msg": f"双底低点 ≈{left:.2f}"})
        return out

    # ---------- 统计 ----------
    def _hurst(self, m):
        """Hurst 指数：>0.5 趋势，<0.5 反转"""
        out = []
        if len(m) < 60: return out
        h = hurst_rs(m["close"].pct_change().fillna(0), 50).iloc[-1]
        if np.isnan(h): return out
        if h > THRESHOLDS["hurst_trend"]:
            out.append({"key": "hurst_t", "level": "中",
                        "title": f"[{self.name} 分钟] 趋势持续性强",
                        "msg": f"Hurst={h:.2f}，趋势性强"})
        elif h < THRESHOLDS["hurst_mean_rev"]:
            out.append({"key": "hurst_r", "level": "中",
                        "title": f"[{self.name} 分钟] 均值回归性强",
                        "msg": f"Hurst={h:.2f}，反转概率高"})
        return out

    def _skew_kurt(self, m):
        """偏度峰度：尖峰厚尾预警"""
        out = []
        if len(m) < 30: return out
        r = m["close"].pct_change().iloc[-30:].dropna()
        if len(r) < 20: return out
        skew = r.skew(); kurt = r.kurt()
        if kurt > 5:
            out.append({"key": "kurt", "level": "中",
                        "title": f"[{self.name} 分钟] 尖峰厚尾",
                        "msg": f"峰度 {kurt:.2f}，偏度 {skew:.2f}，"
                               f"极端走势概率高"})
        return out

    def _autocorr(self, m):
        """收益率自相关：动量/反转特征"""
        out = []
        if len(m) < 30: return out
        r = m["close"].pct_change().iloc[-30:].dropna()
        if len(r) < 20: return out
        ac = r.autocorr(lag=1)
        if np.isnan(ac): return out
        if ac > THRESHOLDS["autocorr"]:
            out.append({"key": "ac_p", "level": "中",
                        "title": f"[{self.name} 分钟] 动量效应显著",
                        "msg": f"一阶自相关 {ac:.2f}，趋势延续"})
        elif ac < -THRESHOLDS["autocorr"]:
            out.append({"key": "ac_n", "level": "中",
                        "title": f"[{self.name} 分钟] 反转效应显著",
                        "msg": f"一阶自相关 {ac:.2f}，反转概率高"})
        return out


# =====================================================================
# 弹窗
# =====================================================================
class AlertWindow:
    def __init__(self):
        self.queue: Queue = Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.after(200, self._poll)

    def push(self, level, title, msg):
        self.queue.put((level, title, msg))

    def _poll(self):
        try:
            while True:
                lvl, t, m = self.queue.get_nowait()
                self._show(lvl, t, m)
        except Empty:
            pass
        self.root.after(200, self._poll)

    def _show(self, level, title, msg):
        try:
            if level == "高":
                winsound.Beep(2000, 600)
            elif level == "中":
                winsound.Beep(1500, 400)
            else:
                winsound.Beep(1000, 200)
        except Exception:
            pass
        icon = {"高": "warning", "中": "info", "低": "info"}.get(level, "info")
        self.root.after(0, lambda: messagebox.showinfo(
            title, msg, icon=icon, parent=self.root))

    def run(self):
        self.root.mainloop()


# =====================================================================
# 主循环
# =====================================================================
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (datetime.strptime("09:15", "%H:%M").time() <= t <= datetime.strptime("11:35", "%H:%M").time()
            or datetime.strptime("12:55", "%H:%M").time() <= t <= datetime.strptime("15:05", "%H:%M").time())


def monitor_loop(daily_list, minute_list, alert):
    print(f"[{datetime.now():%H:%M:%S}] 盯盘启动 "
          f"日K检测器 {len(daily_list)} 只，分钟检测器 {len(minute_list)} 只 "
          f"间隔 {SCAN_INTERVAL}s")
    toggle = 0
    while True:
        if not is_trading_time():
            time.sleep(60); continue
        # 交替执行：避免单轮太慢，分钟级每轮都跑，日K级每 3 轮跑一次
        toggle += 1
        detectors = minute_list + (daily_list if toggle % 3 == 0 else [])
        for det in detectors:
            try:
                for s in det.detect():
                    print(f"[{datetime.now():%H:%M:%S}] [{s['level']}] {s['title']} - {s['msg']}")
                    alert.push(s["level"], s["title"], s["msg"])
            except Exception as e:
                print(f"[{getattr(det, 'code', '?')}] 检测异常: {e}")
            time.sleep(0.3)
        time.sleep(SCAN_INTERVAL)


def main():
    try:
        spot = ak.stock_zh_a_spot_em()
        name_map = dict(zip(spot["代码"], spot["名称"]))
    except Exception:
        name_map = {}

    daily_list, minute_list = [], []
    for code in WATCH_LIST:
        name = name_map.get(code, code)
        d = DailyDetector(code, name); d.load_history()
        m = MinuteDetector(code, name)
        # 注入日K历史给综合评分使用
        m.daily_hist = d.history
        daily_list.append(d); minute_list.append(m)
        print(f"已加载 {code} {name}，日K {len(d.history)} 根")

    print(f"数据源顺序：{QUOTE.source_order}")
    if _HAS_YFINANCE:
        print("yfinance 可用（墙外源）")
    else:
        print("yfinance 未安装，墙外源不可用（pip install yfinance 启用）")

    alert = AlertWindow()
    t = threading.Thread(target=monitor_loop,
                         args=(daily_list, minute_list, alert), daemon=True)
    t.start()
    alert.run()


if __name__ == "__main__":
    main()
