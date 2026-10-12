"""
多因子选股系统
================
基于技术面+基本面多因子分析，通过XGBoost训练因子权重，实现股票预测与回测。

因子分类：
  - 技术因子（30个）：动量、反转、波动率、量价、均线、RSRS等
  - 基本面因子（10个）：ROE、PE、PB、毛利率、净利率等
  - 衍生因子（10个）：因子排名、行业中性化等

训练方式：
  1. XGBoost 回归：以未来N日收益率为标签，学习非线性因子组合
  2. IC加权：以因子IC均值/ICIR为权重，线性组合

使用方式：
  python multi_factor_strategy.py --mode evaluate # 因子评估（查看哪些因子有效）
  python multi_factor_strategy.py --mode train    # 训练模型
  python multi_factor_strategy.py --mode predict   # 预测今日信号
  python multi_factor_strategy.py --mode backtest  # 回测

使用自定义股票/ETF清单：
  python multi_factor_strategy.py --mode train --stock_list my_stocks.txt
  清单文件格式：每行一个代码，如：
    600519.SH
    000858.SZ
    510300.SH
"""

import argparse
import os
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

# ============================================================
# 数据获取（复用 data_feed）
# ============================================================
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_feed'))
from data_feed_stock import StockData


def load_stock_list_from_file(filepath):
    """从文件加载股票/ETF清单

    文件格式：每行一个代码，支持以下格式：
      - 纯代码：600519
      - 带后缀：600519.SH
      - 带名称（逗号分隔）：600519,贵州茅台
    """
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        return None

    codes = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 支持 "代码,名称" 或 "代码 名称" 格式
            code = line.split(',')[0].split()[0].strip()
            if code:
                codes.append(code)
    print(f"从 {filepath} 加载 {len(codes)} 只股票/ETF")
    return codes


def get_stock_pool(stock_data, min_price=3, max_price=100, min_volume=1e7):
    """获取股票池，过滤ST、停牌、低价股"""
    stock_list = stock_data._get_stock_list()
    pool = []
    for s in stock_list:
        name = s.get('name', '')
        if 'ST' in name or '退' in name:
            continue
        try:
            price = float(s.get('price', 0))
        except (ValueError, TypeError):
            continue
        if min_price <= price <= max_price:
            pool.append(s['code'])
    return pool


def batch_load_history(stock_data, code_list, start_date, end_date, max_workers=5):
    """批量加载历史数据"""
    result = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                stock_data.get_history_data, code, start_date, end_date, True  # local_only=True，只使用本地数据
            ): code for code in code_list
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                df = future.result()
                if df is not None and len(df) > 120:
                    # 应用日期过滤（local_only模式会跳过过滤，这里手动补上）
                    if start_date is not None or end_date is not None:
                        s = pd.Timestamp(start_date) if start_date else df.index.min()
                        e = pd.Timestamp(end_date) if end_date else df.index.max()
                        df = df.loc[s:e]
                    if len(df) > 0:
                        result[code] = df
            except Exception:
                pass
    print(f"成功加载 {len(result)}/{len(code_list)} 只股票的历史数据")
    return result


def batch_load_fundamental(stock_data, code_list, max_workers=3):
    """批量加载财务数据"""
    result = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(stock_data.get_stock_report, code): code
            for code in code_list
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                data = future.result()
                if data is not None and len(data) > 0:
                    # get_stock_report 返回 list[dict]，转为 DataFrame
                    df = pd.DataFrame(data)
                    result[code] = df
            except Exception:
                pass
    print(f"成功加载 {len(result)}/{len(code_list)} 只股票的财务数据")
    return result


# ============================================================
# 因子计算引擎
# ============================================================
class FactorEngine:
    """多因子计算引擎"""

    # 技术因子列表
    TECH_FACTORS = [
        'mom_5', 'mom_10', 'mom_20', 'mom_60',           # 动量因子
        'rev_5', 'rev_10',                                 # 反转因子
        'vol_10', 'vol_20', 'vol_60',                      # 波动率因子
        'turnover_5', 'turnover_20',                       # 换手率因子
        'volume_ratio_5', 'volume_ratio_20',               # 量比因子
        'amount_ma_ratio',                                  # 成交额均线比
        'price_volume_corr_10', 'price_volume_corr_20',    # 量价相关性
        'high_low_ratio_10', 'high_low_ratio_20',          # 振幅因子
        'rsrs', 'rsrs_norm',                               # RSRS因子
        'ma5_bias', 'ma10_bias', 'ma20_bias', 'ma60_bias', # 均线偏离度
        'macd_hist',                                        # MACD柱
        'rsi_14',                                           # RSI
        'boll_position',                                    # 布林带位置
        'vwap_bias',                                        # VWAP偏离
        'obv_ma_ratio',                                     # OBV/MA比
        'ad_line_ma',                                       # AD线均线
    ]

    # 基本面因子列表
    FUND_FACTORS = [
        'roe', 'roe_stability',       # ROE及稳定性
        'pe', 'pb',                   # 估值因子
        'gross_margin', 'net_margin', # 利润率因子
        'revenue_growth',             # 营收增长
        'profit_growth',              # 利润增长
        'current_ratio',              # 流动比率
    ]

    ALL_FACTORS = TECH_FACTORS + FUND_FACTORS

    @staticmethod
    def compute_technical_factors(df):
        """计算全部技术因子

        Args:
            df: DataFrame，需包含 open/high/low/close/volume/amount/turnover 列
        Returns:
            DataFrame，与 df 等长，列为各因子名
        """
        o = df['open'].astype(float)
        h = df['high'].astype(float)
        l = df['low'].astype(float)
        c = df['close'].astype(float)
        # 清除价格为0的异常数据（会导致pct_change除零产生inf）
        for col in [o, h, l, c]:
            col.replace(0, np.nan, inplace=True)
        v = df['volume'].astype(float)
        amt = df['amount'].astype(float) if 'amount' in df.columns else v * c
        turnover = df['turnover'].astype(float) if 'turnover' in df.columns else pd.Series(0, index=df.index)

        factors = pd.DataFrame(index=df.index)

        # ---- 动量因子 ----
        for n in [5, 10, 20, 60]:
            factors[f'mom_{n}'] = c.pct_change(n)

        # ---- 反转因子（短期负收益=反转信号）----
        factors['rev_5'] = -c.pct_change(5)
        factors['rev_10'] = -c.pct_change(10)

        # ---- 波动率因子 ----
        ret = c.pct_change()
        for n in [10, 20, 60]:
            factors[f'vol_{n}'] = ret.rolling(n).std()

        # ---- 换手率因子 ----
        factors['turnover_5'] = turnover.rolling(5).mean()
        factors['turnover_20'] = turnover.rolling(20).mean()

        # ---- 量比因子 ----
        factors['volume_ratio_5'] = v / v.rolling(5).mean()
        factors['volume_ratio_20'] = v / v.rolling(20).mean()

        # ---- 成交额均线比 ----
        factors['amount_ma_ratio'] = amt / amt.rolling(20).mean()

        # ---- 量价相关性 ----
        for n in [10, 20]:
            factors[f'price_volume_corr_{n}'] = c.rolling(n).corr(v)

        # ---- 振幅因子 ----
        for n in [10, 20]:
            factors[f'high_low_ratio_{n}'] = (h.rolling(n).max() - l.rolling(n).min()) / c.rolling(n).mean()

        # ---- RSRS因子 ----
        factors['rsrs'], factors['rsrs_norm'] = FactorEngine._compute_rsrs(h, l, N=18, M=300)

        # ---- 均线偏离度 ----
        for n in [5, 10, 20, 60]:
            ma = c.rolling(n).mean()
            factors[f'ma{n}_bias'] = (c - ma) / ma

        # ---- MACD ----
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        factors['macd_hist'] = dif - dea

        # ---- RSI ----
        delta = c.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        factors['rsi_14'] = 100 - 100 / (1 + rs)

        # ---- 布林带位置 ----
        ma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        factors['boll_position'] = (c - ma20) / (2 * std20 + 1e-10)

        # ---- VWAP偏离 ----
        vwap = amt / (v + 1e-10)
        factors['vwap_bias'] = (c - vwap) / (vwap + 1e-10)

        # ---- OBV/MA比 ----
        obv = (np.sign(c.diff()) * v).cumsum()
        obv_ma = obv.rolling(20).mean()
        factors['obv_ma_ratio'] = obv / (obv_ma + 1e-10)

        # ---- AD线均线 ----
        clv = ((c - l) - (h - c)) / (h - l + 1e-10)
        ad = (clv * v).cumsum()
        factors['ad_line_ma'] = ad / (ad.rolling(20).mean() + 1e-10)

        return factors

    @staticmethod
    def _compute_rsrs(high, low, N=18, M=300):
        """计算RSRS指标"""
        rsrs_raw = pd.Series(np.nan, index=high.index)
        for i in range(N - 1, len(high)):
            y = low.iloc[i - N + 1:i + 1].values
            x = high.iloc[i - N + 1:i + 1].values
            if np.std(x) < 1e-10:
                continue
            slope = np.cov(x, y)[0, 1] / (np.var(x) + 1e-10)
            rsrs_raw.iloc[i] = slope

        # 标准化
        rsrs_norm = pd.Series(np.nan, index=high.index)
        for i in range(M - 1, len(rsrs_raw)):
            window = rsrs_raw.iloc[i - M + 1:i + 1].dropna()
            if len(window) < M * 0.5:
                continue
            mu = window.mean()
            sigma = window.std()
            if sigma < 1e-10:
                continue
            rsrs_norm.iloc[i] = (rsrs_raw.iloc[i] - mu) / sigma

        return rsrs_raw, rsrs_norm

    @staticmethod
    def compute_fundamental_factors(finance_data):
        """计算基本面因子

        Args:
            finance_data: DataFrame，来自 get_stock_report 转换后的数据
        Returns:
            dict，各因子值
        """
        if finance_data is None or len(finance_data) == 0:
            return {f: np.nan for f in FactorEngine.FUND_FACTORS}

        try:
            # 取最近5期数据
            sorted_data = finance_data.sort_values('日期', ascending=False)
            recent = sorted_data.head(5)

            def safe_float(val):
                if val is None or val == '' or val == '-' or pd.isna(val):
                    return np.nan
                try:
                    s = str(val).replace(',', '').replace('%', '').replace('元', '')
                    return float(s)
                except (ValueError, TypeError):
                    return np.nan

            # 字段名映射：新版新浪接口字段名 -> 旧版东财字段名
            field_map = {
                '净资产收益率(%)': ['净资产收益率(%)', '净资产收益率(ROE)', '摊薄净资产收益率', '净资产收益率_平均'],
                '市盈率': ['市盈率'],
                '市净率': ['市净率'],
                '销售毛利率(%)': ['销售毛利率(%)', '毛利率'],
                '销售净利率(%)': ['销售净利率(%)', '销售净利率'],
                '营业收入同比增长率(%)': ['营业收入同比增长率(%)', '营业总收入增长率'],
                '净利润同比增长率(%)': ['净利润同比增长率(%)', '归属母公司净利润增长率'],
                '流动比率': ['流动比率'],
            }

            def get_val(row, field_name):
                """从行中获取值，支持多种字段名"""
                candidates = field_map.get(field_name, [field_name])
                for c in candidates:
                    if c in row and row[c] is not None:
                        v = safe_float(row[c])
                        if not np.isnan(v):
                            return v
                return np.nan

            # ROE
            roe_vals = [get_val(r, '净资产收益率(%)') for _, r in recent.iterrows()]
            roe_vals = [x for x in roe_vals if not np.isnan(x)]

            # 估值
            pe_vals = [get_val(r, '市盈率') for _, r in recent.iterrows()]
            pb_vals = [get_val(r, '市净率') for _, r in recent.iterrows()]

            # 利润率
            gm_vals = [get_val(r, '销售毛利率(%)') for _, r in recent.iterrows()]
            nm_vals = [get_val(r, '销售净利率(%)') for _, r in recent.iterrows()]

            # 增长率
            rg_vals = [get_val(r, '营业收入同比增长率(%)') for _, r in recent.iterrows()]
            pg_vals = [get_val(r, '净利润同比增长率(%)') for _, r in recent.iterrows()]

            # 流动比率
            cr_vals = [get_val(r, '流动比率') for _, r in recent.iterrows()]

            def first_valid(vals):
                for v in vals:
                    if not np.isnan(v):
                        return v
                return np.nan

            roe = first_valid(roe_vals)
            roe_stability = np.std(roe_vals) if len(roe_vals) >= 3 else np.nan

            return {
                'roe': roe,
                'roe_stability': -roe_stability if not np.isnan(roe_stability) else np.nan,  # 稳定性越高越好
                'pe': first_valid(pe_vals),
                'pb': first_valid(pb_vals),
                'gross_margin': first_valid(gm_vals),
                'net_margin': first_valid(nm_vals),
                'revenue_growth': first_valid(rg_vals),
                'profit_growth': first_valid(pg_vals),
                'current_ratio': first_valid(cr_vals),
            }
        except Exception as e:
            return {f: np.nan for f in FactorEngine.FUND_FACTORS}


# ============================================================
# 因子预处理
# ============================================================
class FactorPreprocessor:
    """因子预处理：去极值、标准化、缺失值填充"""

    @staticmethod
    def winsorize(series, n_sigma=3):
        """MAD法去极值"""
        median = series.median()
        mad = (series - median).abs().median()
        upper = median + n_sigma * 1.4826 * mad
        lower = median - n_sigma * 1.4826 * mad
        return series.clip(lower, upper)

    @staticmethod
    def zscore(series):
        """Z-Score标准化"""
        mu = series.mean()
        sigma = series.std()
        if sigma < 1e-10:
            return series * 0
        return (series - mu) / sigma

    @staticmethod
    def preprocess_factor_df(factor_df, factor_names=None):
        """对因子截面做预处理

        Args:
            factor_df: DataFrame，index为股票代码，列为因子名
            factor_names: 要处理的列名列表，None则处理全部
        """
        if factor_names is None:
            factor_names = factor_df.columns.tolist()
        result = factor_df.copy()
        for col in factor_names:
            if col not in result.columns:
                continue
            series = result[col].dropna()
            if len(series) < 10:
                continue
            series = FactorPreprocessor.winsorize(series)
            series = FactorPreprocessor.zscore(series)
            result.loc[series.index, col] = series
        # 缺失值填充为0（中性含义）
        result = result.fillna(0)
        return result


# ============================================================
# 因子评估
# ============================================================
class FactorEvaluator:
    """因子IC/IR评估"""

    @staticmethod
    def compute_ic(factor_values, forward_returns):
        """计算单因子IC序列

        Args:
            factor_values: DataFrame (dates x stocks)，因子值
            forward_returns: DataFrame (dates x stocks)，未来收益率
        Returns:
            Series，每期的IC值
        """
        ic_series = {}
        common_idx = factor_values.index.intersection(forward_returns.index)
        for date in common_idx:
            fv = factor_values.loc[date].dropna()
            fr = forward_returns.loc[date].dropna()
            common = fv.index.intersection(fr.index)
            if len(common) < 10:
                continue
            ic = fv[common].corr(fr[common], method='spearman')
            ic_series[date] = ic
        return pd.Series(ic_series)

    @staticmethod
    def evaluate_factors(factor_panel, forward_returns, factor_names=None):
        """评估所有因子

        Args:
            factor_panel: dict，{因子名: DataFrame(dates x stocks)}
            forward_returns: DataFrame (dates x stocks)
            factor_names: 要评估的因子列表
        Returns:
            DataFrame，包含IC均值、IC标准差、ICIR、IC>0占比
        """
        if factor_names is None:
            factor_names = list(factor_panel.keys())

        results = []
        for name in factor_names:
            if name not in factor_panel:
                continue
            ic = FactorEvaluator.compute_ic(factor_panel[name], forward_returns)
            if len(ic) == 0:
                continue
            ic_mean = ic.mean()
            ic_std = ic.std()
            icir = ic_mean / ic_std if ic_std > 1e-10 else 0
            ic_pos_ratio = (ic > 0).mean()
            results.append({
                'factor': name,
                'ic_mean': ic_mean,
                'ic_std': ic_std,
                'icir': icir,
                'ic_pos_ratio': ic_pos_ratio,
                'ic_count': len(ic),
            })
        if not results:
            return pd.DataFrame(columns=['factor', 'ic_mean', 'ic_std', 'icir', 'ic_pos_ratio', 'ic_count'])
        return pd.DataFrame(results).sort_values('icir', ascending=False)


# ============================================================
# 因子权重训练
# ============================================================
class FactorTrainer:
    """因子权重训练：XGBoost + IC加权"""

    def __init__(self, forward_period=5):
        self.forward_period = forward_period
        self.model = None
        self.ic_weights = None
        self.factor_importance = None

    def prepare_training_data(self, factor_panel, forward_returns):
        """向量化构造训练数据

        Args:
            factor_panel: dict，{因子名: DataFrame(dates x stocks)}
            forward_returns: DataFrame (dates x stocks)
        Returns:
            X, y, groups, feature_cols
        """
        if not factor_panel:
            return None, None, None, []

        # 向量化：stack所有因子为 (date, stock) MultiIndex
        stacked_list = []
        for name, fdf in factor_panel.items():
            s = fdf.stack()
            s.name = name
            stacked_list.append(s)
        X_df = pd.concat(stacked_list, axis=1)  # index=(date, stock), cols=因子名

        # 标签
        y_s = forward_returns.stack()
        y_s.name = 'forward_return'

        # 内连接对齐
        df = X_df.join(y_s, how='inner')
        if len(df) == 0:
            return None, None, None, []

        feature_cols = list(factor_panel.keys())
        X = df[feature_cols].values
        y = df['forward_return'].values
        groups = df.index.get_level_values(0).values

        # 过滤label为NaN的行
        valid_mask = ~np.isnan(y)
        X, y, groups = X[valid_mask], y[valid_mask], groups[valid_mask]

        # NaN填充为0
        X = np.nan_to_num(X, nan=0.0)

        return X, y, groups, feature_cols

    def train_xgboost(self, factor_panel, forward_returns):
        """训练XGBoost模型"""
        try:
            import xgboost as xgb
        except ImportError:
            print("请安装xgboost: pip install xgboost")
            return None

        result = self.prepare_training_data(factor_panel, forward_returns)
        if result[0] is None:
            print("训练数据为空，无法训练")
            return None

        X, y, groups, feature_cols = result
        print(f"训练数据: {X.shape[0]} 条样本, {X.shape[1]} 个因子")

        # 时间序列分割：前80%训练，后20%验证
        unique_dates = np.sort(np.unique(groups))
        split_idx = int(len(unique_dates) * 0.8)
        train_dates = set(unique_dates[:split_idx])
        train_mask = np.isin(groups, list(train_dates))

        X_train, X_val = X[train_mask], X[~train_mask]
        y_train, y_val = y[train_mask], y[~train_mask]

        # 清洗NaN和无穷值（XGBoost不支持）
        X_train = np.nan_to_num(X_train, nan=np.nan, posinf=np.nan, neginf=np.nan)
        X_val = np.nan_to_num(X_val, nan=np.nan, posinf=np.nan, neginf=np.nan)
        y_train = np.nan_to_num(y_train, nan=np.nan, posinf=np.nan, neginf=np.nan)
        y_val = np.nan_to_num(y_val, nan=np.nan, posinf=np.nan, neginf=np.nan)
        # 裁剪极端值到float32安全范围
        clip_val = np.finfo(np.float32).max / 10
        X_train = np.clip(X_train, -clip_val, clip_val)
        X_val = np.clip(X_val, -clip_val, clip_val)
        # 过滤仍含NaN的行
        valid_mask = np.isfinite(y_train) & np.isfinite(X_train).all(axis=1)
        X_train, y_train = X_train[valid_mask], y_train[valid_mask]
        valid_mask_val = np.isfinite(y_val) & np.isfinite(X_val).all(axis=1)
        X_val, y_val = X_val[valid_mask_val], y_val[valid_mask_val]
        print(f"清洗后训练集: {X_train.shape[0]}, 验证集: {X_val.shape[0]}")

        # 训练XGBoost（优先GPU）
        xgb_params = dict(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
            missing=np.nan,
        )
        # 尝试启用GPU加速
        try:
            self.model = xgb.XGBRegressor(**xgb_params, tree_method='hist', device='cuda')
            self.model.fit(X_train[:min(100, len(X_train))], y_train[:min(100, len(y_train))], verbose=False)
            print("XGBoost GPU加速已启用 (CUDA)")
        except Exception as e:
            print(f"GPU不可用 ({e})，回退到CPU训练")
            self.model = xgb.XGBRegressor(**xgb_params)
        
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        # 特征重要性
        self.factor_importance = pd.Series(
            self.model.feature_importances_, index=feature_cols
        ).sort_values(ascending=False)

        print("\n===== XGBoost 因子重要性 Top 15 =====")
        print(self.factor_importance.head(15).to_string())

        # 验证集IC
        y_pred = self.model.predict(X_val)
        val_ic = np.corrcoef(y_pred, y_val)[0, 1]
        print(f"\n验证集 IC: {val_ic:.4f}")

        self._feature_cols = feature_cols
        return self.model

    def compute_ic_weights(self, factor_panel, forward_returns):
        """基于IC/ICIR计算因子权重"""
        eval_result = FactorEvaluator.evaluate_factors(factor_panel, forward_returns)
        if len(eval_result) == 0:
            return {}

        # ICIR加权
        eval_result = eval_result.set_index('factor')
        icir = eval_result['icir']
        # 只保留ICIR为正的因子
        icir_pos = icir[icir > 0]
        if len(icir_pos) == 0:
            print("没有ICIR为正的因子")
            return {}

        weights = icir_pos / icir_pos.sum()
        self.ic_weights = weights

        print("\n===== IC加权因子权重 =====")
        print(weights.to_string())

        return weights

    def predict(self, factor_df, method='xgboost'):
        """预测股票收益

        Args:
            factor_df: DataFrame，index为股票代码，列为因子名
            method: 'xgboost' 或 'ic_weighted'
        Returns:
            Series，index为股票代码，值为预测收益
        """
        if method == 'xgboost' and self.model is not None:
            feature_cols = self._feature_cols
            X = factor_df[feature_cols].values
            X = np.nan_to_num(X, nan=0.0)
            pred = self.model.predict(X)
            return pd.Series(pred, index=factor_df.index)

        elif method == 'ic_weighted' and self.ic_weights is not None:
            score = pd.Series(0.0, index=factor_df.index)
            for factor_name, weight in self.ic_weights.items():
                if factor_name in factor_df.columns:
                    score += factor_df[factor_name] * weight
            return score

        else:
            raise ValueError(f"无法使用 {method} 方法预测，模型未训练")


# ============================================================
# 回测引擎
# ============================================================
class BacktestEngine:
    """简单回测引擎：基于因子预测的多头组合"""

    def __init__(self, n_stocks=30, rebalance_period=20, commission=0.001):
        self.n_stocks = n_stocks
        self.rebalance_period = rebalance_period
        self.commission = commission

    def run(self, predictions_panel, returns_panel):
        """运行回测

        Args:
            predictions_panel: dict，{date: Series(stock_code -> predicted_return)}
            returns_panel: dict，{date: Series(stock_code -> actual_return)}
        Returns:
            DataFrame，回测净值曲线
        """
        dates = sorted(predictions_panel.keys())
        portfolio_returns = []
        nav = [1.0]

        for i, date in enumerate(dates):
            pred = predictions_panel[date]
            if len(pred) < self.n_stocks:
                continue

            # 选取预测收益最高的N只股票
            top_stocks = pred.nlargest(self.n_stocks).index

            # 计算组合收益（等权）
            if date in returns_panel:
                actual = returns_panel[date]
                held_returns = actual.reindex(top_stocks).dropna()
                if len(held_returns) > 0:
                    port_ret_raw = held_returns.mean() - self.commission  # 扣手续费
                else:
                    port_ret_raw = 0
            else:
                port_ret_raw = 0

            # 限制单期亏损/收益，防止NAV归零或溢出
            port_ret = np.clip(port_ret_raw, -0.99, 9.99)
            if i < 3 or port_ret != port_ret_raw:
                print(f"  [回测] {date.date()} 组合收益: {port_ret:.2%} (原始: {port_ret_raw:.2%})")

            portfolio_returns.append({'date': date, 'return': port_ret})
            nav.append(nav[-1] * (1 + port_ret))

        result = pd.DataFrame(portfolio_returns)
        if len(result) == 0:
            return pd.DataFrame()
        result['nav'] = nav[1:]
        result.set_index('date', inplace=True)
        return result

    @staticmethod
    def compute_metrics(nav_series):
        """计算回测指标"""
        if len(nav_series) < 2:
            return {}
        rets = nav_series.pct_change().dropna()
        # 过滤inf值（NAV归零会产生inf）
        rets = rets.replace([np.inf, -np.inf], np.nan).dropna()
        if len(rets) == 0:
            return {}
        total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
        annual_return = (1 + total_return) ** (252 / len(rets)) - 1
        annual_vol = rets.std() * np.sqrt(252)
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0
        max_drawdown = ((nav_series.cummax() - nav_series) / nav_series.cummax()).max()
        win_rate = (rets > 0).mean()

        return {
            '总收益': f'{total_return:.2%}',
            '年化收益': f'{annual_return:.2%}',
            '年化波动': f'{annual_vol:.2%}',
            '夏普比率': f'{sharpe:.3f}',
            '最大回撤': f'{max_drawdown:.2%}',
            '胜率': f'{win_rate:.2%}',
            '交易天数': len(rets),
        }


# ============================================================
# 主流程
# ============================================================
class MultiFactorSystem:
    """多因子选股系统主流程"""

    def __init__(self, forward_period=5, n_stocks=30):
        self.stock_data = StockData()
        self.factor_engine = FactorEngine()
        self.preprocessor = FactorPreprocessor()
        self.trainer = FactorTrainer(forward_period=forward_period)
        self.backtester = BacktestEngine(n_stocks=n_stocks)
        self.forward_period = forward_period

        # 数据缓存
        self.history_data = {}
        self.fundamental_data = {}
        self.factor_panel = {}      # {因子名: DataFrame(dates x stocks)}
        self.forward_returns = None  # DataFrame(dates x stocks)

    def load_data(self, start_date=None, end_date=None, max_stocks=200, stock_list=None):
        """加载股票数据

        Args:
            start_date: 开始日期
            end_date: 结束日期
            max_stocks: 股票池最大数量（仅在自动获取时生效）
            stock_list: 自定义股票/ETF列表，优先于自动获取
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=365 * 2)

        # 获取股票池：优先使用自定义列表
        if stock_list:
            pool = stock_list
            print(f"使用自定义股票/ETF列表: {len(pool)} 只")
        else:
            pool = get_stock_pool(self.stock_data)
            if max_stocks and len(pool) > max_stocks:
                pool = pool[:max_stocks]
            print(f"自动获取股票池: {len(pool)} 只")

        # 加载历史数据
        self.history_data = batch_load_history(
            self.stock_data, pool, start_date, end_date, max_workers=5
        )

        # 加载财务数据（仅对股票有效，ETF无财务数据）
        self.fundamental_data = batch_load_fundamental(
            self.stock_data, list(self.history_data.keys()), max_workers=3
        )

    def compute_all_factors(self):
        """计算所有因子"""
        print("\n===== 计算技术因子 =====")
        tech_factors = {f: {} for f in FactorEngine.TECH_FACTORS}
        fund_factors = {f: {} for f in FactorEngine.FUND_FACTORS}

        for code, df in self.history_data.items():
            try:
                # 技术因子
                tf = FactorEngine.compute_technical_factors(df)
                for col in tf.columns:
                    if col in tech_factors:
                        tech_factors[col][code] = tf[col]

                # 基本面因子
                finance = self.fundamental_data.get(code)
                ff = FactorEngine.compute_fundamental_factors(finance)
                for k, v in ff.items():
                    if k in fund_factors:
                        fund_factors[k][code] = v
            except Exception as e:
                if self.stock_data.verbose_output:
                    print(f"因子计算出错 - {code}: {e}")

        # 组装面板数据：{因子名: DataFrame(dates x stocks)}
        all_factor_dict = {**tech_factors, **fund_factors}

        for factor_name, stock_series in all_factor_dict.items():
            if not stock_series:
                continue
            # 技术因子：每个股票是一个时间序列
            if factor_name in FactorEngine.TECH_FACTORS:
                df = pd.DataFrame(stock_series)
                self.factor_panel[factor_name] = df
            else:
                # 基本面因子：标量值，扩展为与最新日期对齐
                if factor_name not in self.factor_panel and len(tech_factors.get('mom_5', {})) > 0:
                    ref_df = pd.DataFrame(tech_factors['mom_5'])
                    scalar_df = pd.DataFrame(
                        {code: pd.Series(val, index=ref_df.index) for code, val in stock_series.items()}
                    )
                    self.factor_panel[factor_name] = scalar_df

        # 统一清理inf值（防止除零传播）
        for name in list(self.factor_panel.keys()):
            self.factor_panel[name] = self.factor_panel[name].replace([np.inf, -np.inf], np.nan)

        print(f"共计算 {len(self.factor_panel)} 个因子")

    def compute_forward_returns(self):
        """计算未来收益率标签"""
        ret_dict = {}
        for code, df in self.history_data.items():
            if 'close' not in df.columns:
                continue
            close = df['close'].astype(float)
            # 将0替换为NaN，防止pct_change除零产生inf
            close = close.replace(0, np.nan)
            fwd = close.pct_change(self.forward_period).shift(-self.forward_period)
            # 过滤inf值
            fwd = fwd.replace([np.inf, -np.inf], np.nan)
            ret_dict[code] = fwd

        if ret_dict:
            self.forward_returns = pd.DataFrame(ret_dict)

    def train(self, method='both'):
        """训练模型

        Args:
            method: 'xgboost', 'ic_weighted', 'both'
        """
        if not self.factor_panel or self.forward_returns is None:
            print("请先运行 load_data() 和 compute_all_factors()")
            return

        if method in ('ic_weighted', 'both'):
            print("\n===== IC加权训练 =====")
            self.trainer.compute_ic_weights(self.factor_panel, self.forward_returns)

        if method in ('xgboost', 'both'):
            print("\n===== XGBoost训练 =====")
            self.trainer.train_xgboost(self.factor_panel, self.forward_returns)

    def evaluate_factors(self):
        """评估因子有效性"""
        if not self.factor_panel or self.forward_returns is None:
            print("请先运行 load_data() 和 compute_all_factors()")
            return None

        result = FactorEvaluator.evaluate_factors(self.factor_panel, self.forward_returns)
        print("\n===== 因子IC评估 =====")
        print(result.head(20).to_string(index=False))
        return result

    def backtest(self, method='xgboost'):
        """回测"""
        if self.forward_returns is None:
            print("请先计算因子和收益率")
            return None

        # 逐日预测
        predictions_panel = {}
        returns_panel = {}

        common_dates = self.forward_returns.index
        # 每self.rebalance_period调仓一次
        rebalance_dates = common_dates[::self.backtester.rebalance_period]

        for date in rebalance_dates:
            # 构建当日截面因子数据
            factor_df = pd.DataFrame(index=self.forward_returns.columns)
            for factor_name, factor_df_full in self.factor_panel.items():
                if date in factor_df_full.index:
                    factor_df[factor_name] = factor_df_full.loc[date].reindex(factor_df.index)

            # 预处理
            factor_df = FactorPreprocessor.preprocess_factor_df(factor_df)

            # 预测
            try:
                pred = self.trainer.predict(factor_df, method=method)
                predictions_panel[date] = pred
            except (ValueError, AttributeError):
                continue

            # 实际收益
            if date in self.forward_returns.index:
                returns_panel[date] = self.forward_returns.loc[date]

        # 回测
        result = self.backtester.run(predictions_panel, returns_panel)
        if len(result) == 0:
            print("回测结果为空")
            return None

        # 计算指标
        metrics = BacktestEngine.compute_metrics(result['nav'])
        print(f"\n===== 回测结果 ({method}) =====")
        for k, v in metrics.items():
            print(f"  {k}: {v}")

        return result

    def predict_today(self, method='xgboost', top_n=20):
        """预测今日信号"""
        # 构建截面因子数据
        factor_df = pd.DataFrame(index=list(self.history_data.keys()))
        for factor_name, factor_df_full in self.factor_panel.items():
            # 取最新一期的因子值
            latest = factor_df_full.iloc[-1] if len(factor_df_full) > 0 else pd.Series()
            factor_df[factor_name] = latest.reindex(factor_df.index)

        # 预处理
        factor_df = FactorPreprocessor.preprocess_factor_df(factor_df)

        # 预测
        pred = self.trainer.predict(factor_df, method=method)
        top = pred.nlargest(top_n)

        print(f"\n===== 今日推荐 Top {top_n} ({method}) =====")
        stock_list = self.stock_data._get_stock_list()
        name_map = {s['code']: s.get('name', '') for s in stock_list}
        for i, (code, score) in enumerate(top.items(), 1):
            print(f"  {i:2d}. {code} {name_map.get(code, ''):6s}  预测得分: {score:.4f}")

        return top


# ============================================================
# 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='多因子选股系统')
    parser.add_argument('--mode', type=str, default='train',
                        choices=['train', 'predict', 'backtest', 'evaluate'],
                        help='运行模式')
    parser.add_argument('--forward', type=int, default=5,
                        help='预测未来N日收益率')
    parser.add_argument('--n_stocks', type=int, default=30,
                        help='组合持仓股票数')
    parser.add_argument('--max_stocks', type=int, default=200,
                        help='股票池最大数量（仅在自动获取时生效）')
    parser.add_argument('--method', type=str, default='xgboost',
                        choices=['xgboost', 'ic_weighted', 'both'],
                        help='训练方法')
    parser.add_argument('--stock_list', type=str, default=None,
                        help='股票/ETF清单文件路径，每行一个代码')
    args = parser.parse_args()

    # 加载自定义股票列表（如果提供）
    stock_list = None
    if args.stock_list:
        stock_list = load_stock_list_from_file(args.stock_list)
        if not stock_list:
            print("股票清单加载失败，退出")
            return

    system = MultiFactorSystem(
        forward_period=args.forward,
        n_stocks=args.n_stocks,
    )

    # 加载数据
    print("===== 加载数据 =====")
    system.load_data(max_stocks=args.max_stocks, stock_list=stock_list)

    # 计算因子
    print("\n===== 计算因子 =====")
    system.compute_all_factors()
    system.compute_forward_returns()

    if args.mode == 'evaluate':
        system.evaluate_factors()
        return

    if args.mode == 'train':
        system.evaluate_factors()
        system.train(method=args.method)

    if args.mode == 'backtest':
        system.train(method=args.method)
        system.backtest(method='xgboost')
        system.backtest(method='ic_weighted')

    if args.mode == 'predict':
        system.train(method=args.method)
        system.predict_today(method='xgboost')
        system.predict_today(method='ic_weighted')


if __name__ == '__main__':
    main()
