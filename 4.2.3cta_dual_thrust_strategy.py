import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData

class DualThrustStrategy(bt.Strategy):
    """CTA双动力策略
    
    计算方法:
    HH: N天最高价的最高价
    LC: N天收盘价的最低价
    HC: N天收盘价的最高价
    LL: N天最低价的最低价
    Range: max(HH-LC, HC-LL)
    上轨: OPEN + K1 * Range
    下轨: OPEN + K2 * Range
    """
    
    params = (
        ('k1', 0.4),          # 上轨系数
        ('k2', 0.6),          # 下轨系数
        ('period', 5),        # 计算周期
        ('size', 100),        # 每次交易数量
        ('stop_loss', 0.03),  # 止损比例
    )

    def __init__(self):
        # 保存K线数据的引用
        self.data_open = self.datas[0].open
        self.data_high = self.datas[0].high
        self.data_low = self.datas[0].low
        self.data_close = self.datas[0].close
        
        # 计算上下轨的指标
        self.upper_band = None
        self.lower_band = None
        
        # 记录当前持仓状态
        self.position_type = None  # 1: 多头, -1: 空头, None: 无持仓
        
        # 记录交易价格
        self.entry_price = None
        
    def next(self):
        """每个交易日调用一次"""
        # 确保有足够的历史数据
        if len(self) < self.p.period:
            return
            
        # 计算上下轨
        self.calculate_bands()
        
        # 获取当前价格
        current_high = self.data_high[0]
        current_low = self.data_low[0]
        
        # 交易逻辑
        self.trade_logic(current_high, current_low)
        
    def calculate_bands(self):
        """计算上下轨"""
        # 获取历史数据
        highs = self.data_high.get(size=self.p.period)
        lows = self.data_low.get(size=self.p.period)
        closes = self.data_close.get(size=self.p.period)
        
        # 计算HH, LC, HC, LL
        hh = max(highs)  # N天最高价的最高价
        lc = min(closes) # N天收盘价的最低价
        hc = max(closes) # N天收盘价的最高价
        ll = min(lows)   # N天最低价的最低价
        
        # 计算Range
        range_val = max(hh - lc, hc - ll)
        
        # 计算上下轨
        self.upper_band = self.data_open[0] + self.p.k1 * range_val
        self.lower_band = self.data_open[0] - self.p.k2 * range_val
        
    def trade_logic(self, current_high, current_low):
        """交易逻辑"""
        # 检查止损
        if self.check_stop_loss():
            return
            
        # 无持仓时的开仓逻辑
        if not self.position:
            # 突破上轨做多
            if current_high > self.upper_band:
                self.long_enter()
            # 突破下轨做空
            elif current_low < self.lower_band:
                self.short_enter()
                
        # 持仓时的平仓逻辑
        else:
            # 多头持仓
            if self.position.size > 0:
                # 跌破下轨平多
                if current_low < self.lower_band:
                    self.long_exit()
            # 空头持仓
            else:
                # 突破上轨平空
                if current_high > self.upper_band:
                    self.short_exit()
                    
    def check_stop_loss(self):
        """检查止损"""
        if not self.position or not self.entry_price:
            return False
            
        if len(self) > 0:
            current_price = self.data_close[0]
        else:
            return False
        
        loss_ratio = abs(current_price - self.entry_price) / self.entry_price
        
        if loss_ratio > self.p.stop_loss:
            if self.position.size > 0:
                self.long_exit()
            else:
                self.short_exit()
            return True
            
        return False
        
    def long_enter(self):
        """做多入场"""
        self.buy(size=self.p.size)
        self.position_type = 1
        self.entry_price = self.data_close[0]
        
    def long_exit(self):
        """多头平仓"""
        self.close()
        self.position_type = None
        self.entry_price = None
        
    def short_enter(self):
        """做空入场"""
        self.sell(size=self.p.size)
        self.position_type = -1
        self.entry_price = self.data_close[0]
        
    def short_exit(self):
        """空头平仓"""
        self.close()
        self.position_type = None
        self.entry_price = None
        
    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            print(f'交易利润: {trade.pnl:.2f}')

def run_strategy():
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    stock_data = StockData()
    code = stock_data.get_random_stock_code()
    print(f'加载数据: {code}')
    data = load_stock_data(code) 
    cerebro.adddata(data)
    
    # 设置初始资金
    cerebro.broker.setcash(1000000.0)
    
    # 设置手续费
    cerebro.broker.setcommission(commission=0.0003)
    
    # 添加策略
    cerebro.addstrategy(DualThrustStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    cerebro.addanalyzer(bt.analyzers.Returns)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
    
    # 运行回测
    results = cerebro.run()
    
    # 打印结果
    strategy = results[0]
    print(f'最终资金: {cerebro.broker.getvalue():,.2f}')
    print(f'总收益率: {strategy.analyzers.returns.get_analysis()["rtot"]:,.2%}')
    print(f'夏普比率: {strategy.analyzers.sharperatio.get_analysis()["sharperatio"]:,.2f}')
    print(f'最大回撤: {strategy.analyzers.drawdown.get_analysis()["max"]["drawdown"]:,.2%}')
    
    # 分析交易
    trade_analysis = strategy.analyzers.tradeanalyzer.get_analysis()
    print(f'总交易次数: {trade_analysis.total.total}')
    print(f'盈利交易: {trade_analysis.won.total}')
    print(f'亏损交易: {trade_analysis.lost.total}')
    
    # 绘制图表
    cerebro.plot()

def load_stock_data(code):
    """加载股票数据"""
    # 使用 data_feed.py 中的 StockData 类加载数据
    stock_data = StockData()
    df = stock_data.get_history_data(code)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*2)
    mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
    df = df[mask]
    
    if df is not None:
        return bt.feeds.PandasData(
            dataname=df,
            datetime=None,  # 使用索引作为日期
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            openinterest=-1
        )
    return None

if __name__ == '__main__':
    run_strategy() 