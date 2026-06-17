import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData

class FOFStrategy(bt.Strategy):
    """FOF基金组合策略
    
    基于信息比率(IR)选择基金，动态调整组合权重
    """
    
    params = (
        ('rebalance_days', 60),     # 调仓周期
        ('check_returns', 10),      # 收益检查周期
        ('top_funds', 10),          # 持有基金数量
        ('lookback_periods', 6),    # IR计算回看期数
        ('period_days', 60),        # 单个IR计算周期
        ('profit_take', 0.20),      # 止盈比例
        ('stop_loss', 0.10),        # 止损比例
    )
    
    def __init__(self):
        # 记录调仓日期
        self.last_rebalance_day = 0
        self.last_check_day = 0
        
        # 存储基金池
        self.fund_pool = {}
        
        # 目标权重
        self.target_weights = {
            1: 0.14, 2: 0.13, 3: 0.12, 4: 0.11, 5: 0.10,
            6: 0.10, 7: 0.09, 8: 0.08, 9: 0.07, 10: 0.06
        }
        
        # 加载基准数据
        self.benchmark = self.get_benchmark_data()
        
    def get_benchmark_data(self):
        """获取沪深300基准数据"""
        stock_data = StockData()
        return stock_data.get_history_data('000300.SH')
        
    def next(self):
        """每个交易日调用一次"""
        # 检查止盈止损
        if len(self) - self.last_check_day >= self.p.check_returns:
            self.check_positions()
            self.last_check_day = len(self)
            
        # 调仓
        if len(self) - self.last_rebalance_day >= self.p.rebalance_days:
            self.rebalance_portfolio()
            self.last_rebalance_day = len(self)
            
    def check_positions(self):
        """检查持仓收益"""
        for data in self.datas:
            if self.getposition(data).size:
                # 计算持仓收益
                pos = self.getposition(data)
                profit_ratio = (data.close[0] - pos.price) / pos.price
                
                # 止盈止损
                if profit_ratio >= self.p.profit_take or profit_ratio <= -self.p.stop_loss:
                    self.close(data=data)
                    if data._name in self.fund_pool:
                        del self.fund_pool[data._name]
                        
    def rebalance_portfolio(self):
        """调仓"""
        # 1. 选择基金
        self.select_funds()
        
        # 2. 获取调仓清单
        to_sell, to_buy = self.get_rebalance_orders()
        
        # 3. 执行卖出
        for data in to_sell:
            self.close(data=data)
            
        # 4. 执行买入
        if to_buy:
            portfolio_value = self.broker.get_value()
            for i, data in enumerate(to_buy, 1):
                if i in self.target_weights:
                    target_value = portfolio_value * self.target_weights[i]
                    self.order_target_value(data=data, target=target_value)
                    
    def select_funds(self):
        """基金选择"""
        self.fund_pool.clear()
        
        # 计算所有基金的IR
        ir_data = []
        for data in self.datas:
            ir = self.calculate_ir(data)
            if ir is not None:
                ir_data.append((data._name, ir))
                
        # 按IR排序
        ir_data.sort(key=lambda x: x[1], reverse=True)
        
        # 选择前N只基金
        for i, (fund_code, ir) in enumerate(ir_data[:self.p.top_funds], 1):
            if i in self.target_weights:
                self.fund_pool[fund_code] = self.target_weights[i]
                
    def calculate_ir(self, data):
        """计算信息比率"""
        try:
            # 计算基金收益率
            fund_returns = pd.Series([data.close[i] for i in range(self.p.period_days)])
            fund_returns = fund_returns.pct_change().dropna()
            
            # 计算基准收益率
            bench_returns = pd.Series([self.benchmark.close[i] for i in range(self.p.period_days)])
            bench_returns = bench_returns.pct_change().dropna()
            
            # 计算超额收益
            excess_returns = fund_returns - bench_returns
            
            # 计算IR
            ir = excess_returns.mean() / excess_returns.std()
            
            return ir
            
        except Exception as e:
            print(f"计算IR出错 - {data._name}: {str(e)}")
            return None
            
    def get_rebalance_orders(self):
        """获取调仓订单"""
        # 当前持仓
        current_funds = set([d._name for d, pos in self.positions.items() if pos.size > 0])
        
        # 目标持仓
        target_funds = set(self.fund_pool.keys())
        
        # 生成买卖清单
        to_sell = [d for d in self.datas if d._name in (current_funds - target_funds)]
        to_buy = [d for d in self.datas if d._name in (target_funds - current_funds)]
        
        return to_sell, to_buy
        
    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            print(f'基金 {trade.data._name} 交易利润: {trade.pnl:.2f}')

def run_strategy():
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    stock_data = StockData()
    fund_list = get_fund_list()  # 获取基金列表的函数需要实现
    
    for fund in fund_list:
        data = stock_data.get_history_data(fund['code'])
        if data is not None:
            cerebro.adddata(bt.feeds.PandasData(dataname=data, name=fund['code']))
    
    # 设置初始资金
    cerebro.broker.setcash(10000000.0)
    
    # 设置手续费
    cerebro.broker.setcommission(commission=0.0001)  # 万分之一
    
    # 添加策略
    cerebro.addstrategy(FOFStrategy)
    
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

def get_fund_list():
    """获取基金列表
    
    需要实现从数据源获取基金列表的逻辑
    """
    # TODO: 实现基金列表获取逻辑
    return []

if __name__ == '__main__':
    run_strategy() 