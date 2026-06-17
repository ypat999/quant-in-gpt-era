import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData

class MillenKampStrategy(bt.Strategy):
    """米伦坎普价值投资策略"""
    
    params = (
        ('roe_threshold', 0.15),        # ROE筛选阈值
        ('pe_max', 20),                 # PE最大值
        ('pb_max', 2.0),                # PB最大值
        ('pcf_min', 0),                 # PCF最小值
        ('current_ratio_min', 2.0),     # 流动比率最小值
        ('position_size', 0.1),         # 单个股票持仓比例
        ('max_positions', 10),          # 最大持仓数量
        ('lookback_years', 5),          # ROE回看年数
        ('rebalance_months', 3)         # 调仓周期(月)
    )

    def __init__(self):
        # 记录调仓日期
        self.last_rebalance_month = 0
        
        # 存储选股结果
        self.candidates = {}
        self.holdings = {}
        
        # 复用单个StockData实例
        self.stock_data = StockData()
        
        # 加载财务数据
        self.fundamental_data = {}
        self.load_fundamental_data()
        
    def load_fundamental_data(self):
        """加载财务数据"""
        for data in self.datas:
            symbol = data._name
            # 使用 data_feed.py 中的 StockData 类获取财务数据
            finance_data = self.stock_data.get_stock_finance(symbol)
            
            if finance_data:
                self.process_fundamental_data(symbol, finance_data)
    
    def process_fundamental_data(self, symbol, finance_data):
        """处理财务数据"""
        try:
            # finance_data 为记录列表，按日期倒序排序后取最近5期
            sorted_data = sorted(finance_data, key=lambda x: x.get('日期', ''), reverse=True)
            yearly_data = {}
            for report in sorted_data[:5]:
                report_date = report.get('日期', '')
                
                yearly_data[report_date] = {
                    'roe': float(report.get('净资产收益率', 0)),
                    'eps': float(report.get('每股收益', 0)),
                    'current_ratio': float(report.get('流动比率', 0)),
                    'pe': float(report.get('市盈率', 0)),
                    'pb': float(report.get('市净率', 0)),
                    'pcf': float(report.get('市现率', 0))
                }
            
            self.fundamental_data[symbol] = yearly_data
            
        except (KeyError, ValueError, IndexError, TypeError) as e:
            print(f"处理财务数据出错 - {symbol}: {str(e)}")
    
    def next(self):
        """每个交易日调用一次"""
        # 每季度调仓
        current_month = self.data0.datetime.date(0).month
        if current_month != self.last_rebalance_month and current_month % self.p.rebalance_months == 0:
            self.rebalance_portfolio()
            self.last_rebalance_month = current_month
    
    def rebalance_portfolio(self):
        """调仓"""
        # 1. 选股
        self.select_stocks()
        
        # 2. 获取调仓清单
        to_sell, to_buy = self.get_rebalance_orders()
        
        # 3. 执行卖出
        for data in to_sell:
            self.close(data=data)
        
        # 4. 执行买入
        if to_buy:
            target_value = self.broker.get_value() * self.p.position_size
            for data in to_buy:
                self.buy(data=data, size=self.position_size(data, target_value))
    
    def select_stocks(self):
        """选股"""
        self.candidates.clear()
        
        for data in self.datas:
            symbol = data._name
            
            # 1. ROE筛选
            if not self.filter_by_roe(symbol):
                continue
                
            # 2. 估值筛选
            if not self.filter_by_valuation(symbol):
                continue
                
            # 3. 流动性筛选
            if not self.filter_by_liquidity(symbol):
                continue
            
            # 通过所有筛选的股票加入候选列表
            self.candidates[symbol] = self.calculate_score(symbol)
    
    def filter_by_roe(self, symbol):
        """ROE筛选"""
        if symbol not in self.fundamental_data:
            return False
            
        # 计算5年平均ROE
        roe_values = [data['roe'] for data in self.fundamental_data[symbol].values()]
        avg_roe = np.mean(roe_values)
        
        # ROE稳定性检查
        roe_std = np.std(roe_values)
        
        return avg_roe > self.p.roe_threshold and roe_std < avg_roe * 0.3
    
    def filter_by_valuation(self, symbol):
        """估值筛选"""
        latest_data = list(self.fundamental_data[symbol].values())[0]
        
        return (latest_data['pe'] > 0 and latest_data['pe'] < self.p.pe_max and
                latest_data['pb'] < self.p.pb_max and
                latest_data['pcf'] > self.p.pcf_min)
    
    def filter_by_liquidity(self, symbol):
        """流动性筛选"""
        latest_data = list(self.fundamental_data[symbol].values())[0]
        return latest_data['current_ratio'] > self.p.current_ratio_min
    
    def calculate_score(self, symbol):
        """计算综合得分"""
        latest_data = list(self.fundamental_data[symbol].values())[0]
        
        # 计算各指标得分
        roe_score = latest_data['roe'] / self.p.roe_threshold
        pe_score = (self.p.pe_max - latest_data['pe']) / self.p.pe_max
        cr_score = latest_data['current_ratio'] / self.p.current_ratio_min
        
        # 综合得分
        return (roe_score * 0.4 + pe_score * 0.3 + cr_score * 0.3)
    
    def get_rebalance_orders(self):
        """获取调仓订单"""
        # 按得分排序候选股票
        sorted_candidates = sorted(
            self.candidates.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # 获取前 max_positions 只股票
        target_stocks = set([x[0] for x in sorted_candidates[:self.p.max_positions]])
        
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

def run_strategy():
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    stock_data = StockData()
    stock_list = stock_data.get_stock_list()
    
    for stock in stock_list[:100]:  # 测试用前100只股票
        data = stock_data.get_history_data(stock['code'])
        if data is not None:
            cerebro.adddata(bt.feeds.PandasData(dataname=data, name=stock['code']))
    
    # 设置初始资金
    cerebro.broker.setcash(10000000.0)
    
    # 设置手续费
    cerebro.broker.setcommission(commission=0.0003)  # 万分之三
    
    # 添加策略
    cerebro.addstrategy(MillenKampStrategy)
    
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