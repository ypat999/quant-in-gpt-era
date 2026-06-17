import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData
import concurrent.futures

class PeterLynchStrategy(bt.Strategy):
    """彼得林奇选股策略"""
    
    # params = (
    #     ('profit_threshold', 10000000),  # 利润阈值(1000万)
    #     ('pcf_threshold', 10),           # 股价/现金流阈值
    #     ('debt_threshold', 0.25),        # 资产负债率阈值
    #     ('pe_threshold', 1.0),           # PE/利润增长率阈值
    #     ('position_size', 0.03),         # 单个股票持仓比例
    #     ('max_positions', 30),           # 最大持仓数量
    #     ('rebalance_days', 5)           # 调仓周期(天数)
    # )

    params = (
        ('profit_threshold', 5000000),  # 利润阈值(500万)
        ('pcf_threshold', 150),          # 股价/现金流阈值
        ('debt_threshold', 1),        # 资产负债率阈值
        ('pe_threshold', 20.0),          # PE/利润增长率阈值
        ('position_size', 0.3),        # 单个股票持仓比例
        ('max_positions', 30),          # 最大持仓数量
        ('rebalance_days', 1)           # 调仓周期(天数)
    )
    def __init__(self):
        # 记录调仓日期
        self.last_rebalance_day = 0
        
        # 存储选股结果
        self.candidates = {}
        self.holdings = {}
        
        # 技术指标
        self.pe = {}
        self.profit_growth = {}
        self.inventory_turnover = {}
        self.revenue_growth = {}
        
        # 复用单个StockData实例
        self.stock_data = StockData()
        
        # 加载财务数据
        self.load_fundamental_data()
        
    def load_fundamental_data(self):
        """加载财务数据"""
        for data in self.datas:
            symbol = data._name
            finance_data = self.stock_data.get_stock_finance(symbol)
            
            if finance_data:
                self.process_fundamental_data(symbol, finance_data)
    
    def process_fundamental_data(self, symbol, finance_data):
        """处理财务数据"""
        try:
            latest_report = finance_data[0]
            
            # 提取关键指标
            self.pe[symbol] = float(latest_report.get('市盈率', 0))
            self.profit_growth[symbol] = float(latest_report.get('净利润同比增长率', 0))
            self.inventory_turnover[symbol] = float(latest_report.get('存货周转率', 0))
            self.revenue_growth[symbol] = float(latest_report.get('营业收入同比增长率', 0))
            
        except (KeyError, ValueError, IndexError) as e:
            print(f"处理财务数据出错 - {symbol}: {str(e)}")
    
    def next(self):
        """每个交易日调用一次"""
        # 每 rebalance_days 天调仓一次
        if len(self) - self.last_rebalance_day >= self.params.rebalance_days:
            self.rebalance_portfolio()
            self.last_rebalance_day = len(self)
    
    def rebalance_portfolio(self):
        self.log('调仓')
        """调仓"""
        # 1. 选股
        self.select_stocks()
        
        # 2. 获取调仓清单
        to_sell, to_buy = self.get_rebalance_orders()
        
        # 3. 执行卖出
        for data in to_sell:
            self.close(data=data)
            self.log(f'卖出 {data._name}')
        
        # 4. 执行买入
        if to_buy:
            target_value = self.broker.get_value() * self.params.position_size * 0.95
            for data in to_buy:
                self.buy(data=data, size=self.position_size(data, target_value))
                self.log(f'买入 {data._name}')
    
    def select_stocks(self):
        """选股"""
        self.candidates.clear()
        
        for data in self.datas:
            symbol = data._name
            
            # 1. 利润总额筛选
            if not self.filter_by_profit(symbol):
                continue
                
            # 2. 股价/现金流筛选
            if not self.filter_by_pcf(symbol):
                continue
                
            # 3. 资产负债率筛选
            if not self.filter_by_debt(symbol):
                continue
                
            # 4. PE/利润增长率筛选
            if not self.filter_by_pe_growth(symbol):
                continue
                
            # 通过所有筛选的股票加入候选列表
            self.candidates[symbol] = {
                'inventory_turnover': self.inventory_turnover.get(symbol, 0),
                'revenue_growth': self.revenue_growth.get(symbol, 0)
            }
    
    def filter_by_profit(self, symbol):
        """利润筛选"""
        profit = self.get_fundamental_value(symbol, 'total_profit')
        return profit and profit > self.params.profit_threshold
    
    def filter_by_pcf(self, symbol):
        """现金流筛选"""
        pcf = self.get_fundamental_value(symbol, 'pcf_ratio')
        return pcf and pcf < self.params.pcf_threshold
    
    def filter_by_debt(self, symbol):
        """负债率筛选"""
        debt_ratio = self.get_fundamental_value(symbol, 'debt_ratio')
        return debt_ratio and debt_ratio < self.params.debt_threshold
    
    def filter_by_pe_growth(self, symbol):
        """PE/增长率筛选"""
        pe = self.pe.get(symbol, 0)
        growth = self.profit_growth.get(symbol, 0)
        
        if not pe or not growth:
            return False
            
        return (pe / growth) < self.params.pe_threshold
    
    def get_rebalance_orders(self):
        """获取调仓订单"""
        # 排序候选股票
        sorted_candidates = sorted(
            self.candidates.items(),
            key=lambda x: (x[1]['inventory_turnover'], -x[1]['revenue_growth'])
        )
        
        # 获取前 max_positions 只股票
        target_stocks = set([x[0] for x in sorted_candidates[:self.params.max_positions]])
        
        # 当前持仓
        current_stocks = set([d._name for d, pos in self.positions.items() if pos.size > 0])
        
        # 生成买卖清单
        to_sell = [d for d in self.datas if d._name in (current_stocks - target_stocks)]
        to_buy = [d for d in self.datas if d._name in (target_stocks - current_stocks)]
        
        return to_sell, to_buy
    
    def position_size(self, data, target_value):
        """计算目标持仓数量"""
        price = data.close[0]
        if price > 0:
            size = target_value / price
            return int(size / 100) * 100  # 向下取整到100股
        return 0
    
    def get_fundamental_value(self, symbol, field):
        """获取基本面数据"""
        try:
            # 这里需要根据实际数据源进行修改
            return self.fundamental_data[symbol][field]
        except:
            return None
        
    def log(self, txt, dt=None):
        """输出日志"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}') 

def load_stock_data(stock, start_date, end_date):
    stock_data = StockData()
    return stock['code'], stock_data.get_history_data(stock['code'], start_date, end_date)

def run_strategy():
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    stock_data = StockData()
    stock_list = stock_data.get_stock_list()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*2)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
        future_to_stock = {executor.submit(load_stock_data, stock, start_date, end_date): stock for stock in stock_list[4000:4020]}
        for future in concurrent.futures.as_completed(future_to_stock):
            stock_code, data = future.result()
            if data is not None:
                cerebro.adddata(bt.feeds.PandasData(dataname=data, name=stock_code))
    
    # 设置初始资金
    cerebro.broker.setcash(10000000.0)
    
    # 设置手续费
    cerebro.broker.setcommission(commission=0.0001)
    
    # 添加策略
    cerebro.addstrategy(PeterLynchStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    cerebro.addanalyzer(bt.analyzers.Returns)
    
    # 运行回测
    results = cerebro.run()
    
    # 打印结果
    strategy = results[0]
    print(f'最终资金: {cerebro.broker.getvalue():,.2f}')
    print(f'总收益率: {strategy.analyzers.returns.get_analysis()["rtot"]:,.2%}')
    print(f'夏普比率: {strategy.analyzers.sharperatio.get_analysis()["sharperatio"]:,.2f}')
    print(f'最大回撤: {strategy.analyzers.drawdown.get_analysis()["max"]["drawdown"]:,.2%}')
    
    # 绘制图表
    cerebro.plot()

if __name__ == '__main__':
    run_strategy()