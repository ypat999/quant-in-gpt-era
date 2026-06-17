import backtrader as bt
import concurrent
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData

class DaBanStrategy(bt.Strategy):
    """打板交易策略"""
    
    params = (
        ('trailing_stop_atr', 2.0),  # 跟踪止损的ATR倍数
        ('atr_period', 14),          # ATR周期
        ('position_size', 0.8),      # 单次仓位比例
        ('max_positions', 1000000),        # 最大持仓数量
        ('lookback_period', 60),     # 新高的回溯周期（一个月大约20个交易日）
        ('deviation', 0.02),  # 双顶形态的高点差异
        ('window', 10),  # 颈线窗口
        ('stop_loss', 0.8),  # 止损比例
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
        # self.log(" ")
        self.buy_stocks()
        self.manage_positions()
            
    def buy_stocks(self):
        """选股买入"""
        # 使用 getpositions() 获取当前持仓
        if len(self.getpositions()) >= self.p.max_positions:
            self.log("持仓数量已达到最大值")
            return
            
        if self.is_new_high():
            size = self.position_size()
            order = self.buy(size=size)
            self.orders[self.datas[0]._name] = order
            self.highest_prices[self.datas[0]._name] = self.datas[0].close[0]
            self.log(f"新高，买入股票 {self.datas[0]._name}，数量: {size}")
            
    def manage_positions(self):
        """持仓管理"""
        for data in self.datas:
            position = self.getposition(data)
            if position.size > 0:
                if self.is_double_top(data, 1) or self.is_double_top(data, 2) or self.is_double_top(data, 4):
                    self.log(f"跌破颈线，卖出股票 {data._name}, 数量: {position.size}")
                    order = self.close(data=data)
                    self.orders[data._name] = order
                elif self.is_stop_loss(data):
                    self.log(f"止损，卖出股票 {data._name}, 数量: {position.size}")
                    order = self.close(data=data)
                    self.orders[data._name] = order
        
        return None

    def is_new_high(self):
        """判断是否创出一个月新高"""
        high_data = self.datas[0].high.get(size=self.p.lookback_period)
        if high_data is None or len(high_data) == 0:
            return False
        high = max(high_data)
        return self.datas[0].high[0] >= high
        
    def is_double_top(self, data, windowsize):
        """判断是否走出双顶形态"""
        # high_data = data.high.get(size=self.p.lookback_period * 3)
        # if high_data is None or len(high_data) == 0:
        #     return False
        # high = max(high_data)
        # current_price = data.close[0]
        # previous_high = data.high[-self.p.lookback_period]
        # 判断双顶形态
        # return current_price < previous_high and current_price < high

        # 找到最近的两个高点
        window = self.p.window * windowsize
        if len(data) < window:
            return False
        
        recent_highs = data.high.get(size=window)
        first_high = max(recent_highs[:window // 2])
        second_high = max(recent_highs[window // 2:])

        # 判断两个高点是否相近
        if first_high > 0 and abs(first_high - second_high) / first_high <= self.p.deviation:
            # 判断是否跌破颈线
            neckline = min((self.data.low.get(size=window))[window// 4:window*3//4])
            if self.data.close[0] < neckline:
                return True  # 双顶形态确认
            else:
                return False
        else:
            return False
        
        

    def is_head_and_shoulders(self, data):
        """判断是否走出头肩顶形态"""
        high_data = data.high.get(size=self.p.lookback_period)
        if high_data is None or len(high_data) == 0:
            return False
        high = max(high_data)
        current_price = data.close[0]
        previous_high = data.high[-self.p.lookback_period]
        
        # 判断头肩顶形态
        left_shoulder = data.high[-self.p.lookback_period * 2]
        right_shoulder = data.high[-self.p.lookback_period // 2]
        
        return (left_shoulder < high and right_shoulder < high and current_price < right_shoulder)
        
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
    
    def is_stop_loss(self, data):
        """判断是否达到止损条件"""
        high_data = data.high.get(size=self.p.lookback_period)
        if high_data is None or len(high_data) == 0:
            return False
        high = max(high_data)
        return data.close[0] < high * self.p.stop_loss

    def log(self, txt, dt=None):
        """输出日志"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}',flush=True) 


def load_stock_data(code):
    """加载股票数据"""
    stock_data = StockData()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*20)
    
    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date)

    if df is None:
        print(f"获取数据失败: {code}")
        return code, None
    
    if len(df) < 100:
        print(f"数据长度不足: {code}")
        return code, None
    
    
    
    # required_columns = ['open', 'high', 'low', 'close', 'volume']
    # if not all(col in df.columns for col in required_columns):
    #     print(f"数据缺少必要的列: {required_columns}")
    #     return None
        
    # #print(f"成功加载数据 {code}，时间范围: {df.index[0]} 到 {df.index[-1]}")

    # data = bt.feeds.PandasData(
    #     dataname=df,
    #     datetime=None,
    #     open='open',
    #     high='high',
    #     low='low',
    #     close='close',
    #     volume='volume',
    #     openinterest=-1
    # )
    return code, df


def run_strategy():
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    stock_data = StockData()
    stocks = stock_data.get_stock_list(update=False)
    if not stocks:
        print("获取股票列表失败")
        return
    #随机选取一只股票
    num = np.random.randint(0,len(stocks))
    stock = stocks[num]

    code = stock['code']
    code, data = load_stock_data(code)
    if data is not None:
        cerebro.adddata(bt.feeds.PandasData(dataname=data, name=code))

    # with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
    #     future_to_stock = {executor.submit(load_stock_data, stock['code']): stock for stock in stocks}
    #     for future in concurrent.futures.as_completed(future_to_stock):
    #         stock_code, data = future.result()
    #         if data is not None:
    #             cerebro.adddata(bt.feeds.PandasData(dataname=data, name=stock_code))
    
    print(f"成功加载 {len(cerebro.datas)} 支股票数据")
    # 设置初始资金
    cerebro.broker.setcash(1000000.0)
    
    # 添加策略
    cerebro.addstrategy(DaBanStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio)
    cerebro.addanalyzer(bt.analyzers.DrawDown)

    # 启用现金和市值观察器
    # cerebro.addobserver(bt.observers.Cash)
    # cerebro.addobserver(bt.observers.Value)
    
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

    # 禁用默认的股票绘图
    # for data in cerebro.datas:
        # data.plotinfo.plot = False
        # 绘制图表
    cerebro.plot(style='candlestick')


if __name__ == '__main__':
    run_strategy()