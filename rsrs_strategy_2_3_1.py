import backtrader as bt
import numpy as np
import statsmodels.api as sm
from datetime import datetime, timedelta

class RSRSStrategy(bt.Strategy):
    """
    RSRS择时策略
    参数：
        - N: 计算斜率的周期
        - M: 计算标准分的周期
        - buy_threshold: 买入阈值
        - sell_threshold: 卖出阈值
    """
    params = (
        ('N', 18),
        ('M', 300),
        ('buy_threshold', 0.7),
        ('sell_threshold', -0.7),
    )

    def __init__(self):
        self.slopes = []  # 存储斜率
        self.r2_list = []  # 存储R2值
        self.order = None  # 当前订单
        
        # 计算用的数据
        self.high = self.datas[0].high
        self.low = self.datas[0].low
        
    def calculate_rsrs(self):
        """计算RSRS指标"""
        # 获取历史数据
        highs = np.array([self.high[i] for i in range(-self.p.N, 0)])
        lows = np.array([self.low[i] for i in range(-self.p.N, 0)])
        # 检查数据是否包含 NaN
        if np.isnan(highs).any() or np.isnan(lows).any():
            return None
        
        # 计算斜率和R2
        X = sm.add_constant(lows)
        model = sm.OLS(highs, X)
        results = model.fit()
        
        self.slopes.append(results.params[1])  # 斜率
        self.r2_list.append(results.rsquared)  # R2值
        
        # 如果历史数据不足，返回None
        if len(self.slopes) < self.p.M:
            return None
            
        # 计算标准化RSRS指标
        recent_slopes = self.slopes[-self.p.M:]
        mu = np.mean(recent_slopes)
        sigma = np.std(recent_slopes)
        zscore = (recent_slopes[-1] - mu) / sigma
        
        # 计算右偏RSRS标准分
        return zscore * self.slopes[-1] * self.r2_list[-1]

    def next(self):
        # 如果有未完成的订单，不操作
        if self.order:
            self.log('有未完成的订单')
            return
            
        # 检查收盘价是否为 NaN
        if np.isnan(self.datas[0].close[0]):
            return

        # 计算RSRS指标
        rsrs_value = self.calculate_rsrs()
        if rsrs_value is None:
            return
            
        # 当前持仓量
        position_size = self.getposition(self.datas[0]).size
            
        # 交易逻辑
        if rsrs_value > self.p.buy_threshold and position_size == 0:
            # 买入信号
            buy_size = int(self.broker.getcash() * 0.95 / self.datas[0].close[0])
            self.order = self.buy(size=buy_size)
            self.log(f'买入信号 RSRS: {rsrs_value:.2f}，买入数量: {buy_size:.2f}')
            
        elif rsrs_value < self.p.sell_threshold and position_size > 0:
            # 卖出信号
            self.order = self.sell(size=position_size)
            self.log(f'卖出信号 RSRS: {rsrs_value:.2f}，卖出数量: {position_size:.2f}')
    
    def log(self, txt, dt=None):
        """输出日志"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}') 

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # 订单已提交或已接受，无需操作
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log('买入成交, 价格: %.2f, 成本: %.2f, 佣金 %.2f' %
                         (order.executed.price,
                          order.executed.value,
                          order.executed.comm))
            elif order.issell():
                self.log('卖出成交, 价格: %.2f, 成本: %.2f, 佣金 %.2f' %
                         (order.executed.price,
                          order.executed.value,
                          order.executed.comm))
            self.bar_executed = len(self)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/被拒绝')
        # 重置订单状态
        self.order = None