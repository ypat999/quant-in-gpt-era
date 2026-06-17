import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData

class DaBanStrategy(bt.Strategy):
    """打板交易策略"""
    
    params = (
        ('trailing_stop_atr', 2.0),  # 跟踪止损的ATR倍数
        ('atr_period', 14),          # ATR周期
        ('position_size', 0.1),      # 单次仓位比例
        ('max_positions', 5),        # 最大持仓数量
    )
    
    def __init__(self):
        # 为每个数据源创建ATR指标
        self.atr = {}
        for data in self.datas:
            self.atr[data._name] = bt.indicators.ATR(
                data, 
                period=self.p.atr_period
            )
        
        self.highest_prices = {}  # 记录每个股票的最高价
        self.orders = {}  # 记录每个股票的订单

    def next(self):
        """每个交易日调用一次"""
        self.log(" ")
        self.buy_stocks()
        self.manage_positions()
            
    def buy_stocks(self):
        """选股买入"""
        # 使用 getpositions() 获取当前持仓
        if len(self.getpositions()) >= self.p.max_positions:
            return
            
        if self.is_daban_signal():
            size = self.position_size()
            order = self.buy(size=size)
            self.orders[self.datas[0]._name] = order
            self.highest_prices[self.datas[0]._name] = self.datas[0].close[0]
            
    def manage_positions(self):
        """持仓管理"""
        for data in self.datas:
            position = self.getposition(data)
            if position.size > 0 and self.should_stop_loss(data):
                order = self.close(data=data)
                self.orders[data._name] = order
                
    def is_daban_signal(self):
        """打板信号判断"""
        # 1. 涨停判断
        is_limit_up = self.datas[0].close[0] >= self.datas[0].close[-1] * 1.1
        
        # 2. 放量判断
        is_volume_up = self.datas[0].volume[0] > self.datas[0].volume[-1] * 1.5
        
        # 3. 强势股形态判断
        is_strong = self.is_strong_pattern()
        
        # 所有条件都满足才返回 True
        return is_limit_up and is_volume_up and is_strong
        
    def is_strong_pattern(self):
        """强势形态判断"""
        data = self.datas[0]
        # 数据不足时返回False
        if len(data) < 20:
            return False
        
        close = data.close
        high = data.high
        volume = data.volume
        
        # 1. 均线多头排列：MA5 > MA10 > MA20
        ma5 = sum(close[i] for i in range(-5, 0)) / 5
        ma10 = sum(close[i] for i in range(-10, 0)) / 10
        ma20 = sum(close[i] for i in range(-20, 0)) / 20
        if not (ma5 > ma10 > ma20):
            return False
        
        # 2. 突破近20日高点（排除当前根）
        recent_high = max(high[i] for i in range(-20, -1))
        if close[0] < recent_high:
            return False
        
        # 3. 量价配合：近3日成交量递增
        if not (volume[-3] < volume[-2] < volume[-1]):
            return False
        
        # 4. 避免高位放量：当前价格不应偏离MA20过远（<20%）
        if close[0] > ma20 * 1.20:
            return False
        
        return True
        
    def should_stop_loss(self, data):
        """是否触发止损"""
        current_price = data.close[0]
        highest = self.highest_prices.get(data._name, current_price)
        
        # 更新最高价
        if current_price > highest:
            self.highest_prices[data._name] = current_price
            highest = current_price
        
        # 计算止损价
        stop_price = highest - self.atr[data._name][0] * self.p.trailing_stop_atr
        
        # 判断是否触发止损
        return current_price < stop_price
        
    def position_size(self):
        """计算开仓数量"""
        risk = self.broker.get_cash() * self.p.position_size
        price = self.datas[0].close[0]
        if np.isnan(price):
            return 0
        if price == 0:
            return 0
        size = risk / price
        return int(size)
    
    def log(self, txt, dt=None):
        """输出日志"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}') 

def run_strategy(code = "300624.SZ"):
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    data = load_stock_data(code)
    if data is None:
        print("数据加载失败")
        return
    cerebro.adddata(data)
    

    # 设置初始资金
    cerebro.broker.setcash(1000000.0)
    
    # 添加策略
    cerebro.addstrategy(DaBanStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    
    # 运行回测
    results = cerebro.run()
    
    # 打印结果
    strategy = results[0]
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    sharpe_ratio = strategy.analyzers.sharperatio.get_analysis()["sharperatio"]
    if sharpe_ratio is None:
        sharpe_ratio = 0.0
    print(f'夏普比率: {sharpe_ratio:.2f}')
    print(f'最大回撤: {strategy.analyzers.drawdown.get_analysis()["max"]["drawdown"]:.2f}%')
    
    # 绘制图表
    cerebro.plot()

def load_stock_data(code = "300624.SZ"):
    """加载股票数据"""
    # 使用 data_feed.py 中的 StockData 类加载数据
    stock_data = StockData()
    
    # 使用示例股票代码 - 平安银行
    df = stock_data.get_history_data(code, start_date= datetime.now() - timedelta(days=365*20 ), end_date = datetime.now() - timedelta(days=5))  # 修改为A股股票代码
    
    if df is None:
        print("获取数据失败")
        return None
    
    # 确保数据包含必要的列
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_columns):
        print(f"数据缺少必要的列: {required_columns}")
        return None
        
    print(f"成功加载数据，时间范围: {df.index[0]} 到 {df.index[-1]}")

    # 转换为 backtrader 数据格式
    data = bt.feeds.PandasData(
        dataname=df,
        datetime=None,  # 使用索引作为日期
        open='open',
        high='high',
        low='low',
        close='close',
        volume='volume',
        openinterest=-1
    )
    return data

if __name__ == '__main__':
    run_strategy("688619.SH")