import backtrader as bt
from datetime import datetime, timedelta
import pandas as pd
from rsrs_strategy_2_3_1 import RSRSStrategy
from data_feed import StockData

def run_backtest(data_df, cash=1000000.0):
    """
    运行回测
    
    参数:
        data_df: DataFrame，包含OHLCV数据
        cash: 初始资金
    """
    # 创建cerebro引擎
    cerebro = bt.Cerebro()
    
    # 加载数据
    data = bt.feeds.PandasData(
        dataname=data_df,
        datetime=None,    # 使用索引作为日期列
        open='open',
        high='high',
        low='low',
        close='close',
        volume='volume',
        openinterest=-1
    )
    cerebro.adddata(data)
    
    # 设置初始资金
    cerebro.broker.setcash(cash)
    
    # 设置手续费
    cerebro.broker.setcommission(
        commission=0.0001,  # 0.03%
        mult=1.0,
        margin=False
    )
    
    # 添加策略
    cerebro.addstrategy(RSRSStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # 运行回测
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    results = cerebro.run()
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    
    # 输出分析结果
    strat = results[0]
    
    # 获取分析结果
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', 0)
    drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    returns = strat.analyzers.returns.get_analysis().get('rnorm100', 0)
    
    # 打印结果
    print(f'夏普比率: {sharpe_ratio:.2f}' if sharpe_ratio is not None else '夏普比率: N/A')
    print(f'最大回撤: {drawdown:.2f}%' if drawdown is not None else '最大回撤: N/A')
    print(f'年化收益: {returns:.2f}%' if returns is not None else '年化收益: N/A')
    
    # 绘制结果
    figsize = (16, 9)
    cerebro.plot(style='candlestick',figsize=figsize, dpi=100)

if __name__ == '__main__':
    # 获取数据
    stock_data = StockData()
    # 获取更长时间的历史数据
    end_date = datetime.now() - timedelta(days=5)
    start_date = end_date - timedelta(days=365*10)  # 获取五年的数据
    data_df = stock_data.get_history_data('600745.SH', start_date=start_date, end_date=end_date)
    run_backtest(data_df) 