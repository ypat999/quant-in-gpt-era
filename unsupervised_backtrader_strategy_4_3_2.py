import backtrader as bt
import concurrent
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_feed import StockData
from sklearn.cluster import KMeans
from sklearn import metrics


def load_stock_data(code):
    """加载股票数据"""
    stock_data = StockData()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365+10)
    
    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)

    if df is None:
        print(f"获取数据失败: {code}")
        return code, None
    
    if len(df) < 100:
        print(f"数据长度不足: {code}")
        return code, None
    
    return code, df


def apply_cluster(df, feature_li, clusters=2):
    """
    应用聚类
    :param df: 处理好的输入数据
    :param feature_li: 特征列
    :param clusters: 设置的聚类数量
    :return: 最终的聚类结果
    """
    if df is None or df.empty or len(feature_li) == 0:
        print("输入数据为空或特征列为空，跳过聚类操作。")
        return df
    X = df[feature_li]
    kmeans = KMeans(n_clusters=clusters, random_state=10, n_init=10)
    kmeans.fit(X)
    score = metrics.silhouette_score(X, kmeans.labels_, random_state=10)
    df['cluster'] = kmeans.labels_
    sse_within_cluster = kmeans.inertia_
    
    print("clustering performance")
    print("--------------------")
    print(f"silhouette score: {score:.2f}")
    print(f"sse within cluster: {sse_within_cluster:.2f}")
    
    return df


class UnsupervisedStrategy(bt.Strategy):
    params = (
        ('feature_li', []),
        ('clusters', 2),
    )

    def __init__(self):
        self.order = None
        self.dataclose = self.datas[0].close

    def next(self):
        if self.order:
            return

        # 假设这里有一个方法可以获取当前所有股票的数据
        all_stock_data = self.get_all_stock_data()
        clustered_data = apply_cluster(all_stock_data, self.p.feature_li, self.p.clusters)
        if 'cluster' not in clustered_data.columns:
            print('聚类结果未包含cluster列，跳过交易决策。')
            return
        # 这里可以根据聚类结果进行交易决策
        # 示例：简单地根据聚类结果买入或卖出
        for i, data in enumerate(self.datas):
            if clustered_data.iloc[i]['cluster'] == 0:
                self.buy(data=data)
            else:
                self.sell(data=data)

    def get_all_stock_data(self):
        # 实现获取所有股票数据的逻辑
        data_list = []
        for data in self.datas:
            df = pd.DataFrame({
                'close': data.close.get(size=len(data)),
                'volume': data.volume.get(size=len(data)),
                'high': data.high.get(size=len(data)),
                'low': data.low.get(size=len(data))
            })
            data_list.append(df)
        all_data = pd.concat(data_list, ignore_index=True)
        return all_data


def run_strategy(strategy: bt.Strategy):
    """运行策略"""
    cerebro = bt.Cerebro()
    
    # 加载数据
    stock_data = StockData()
    stocks = stock_data.get_stock_list(update=False)
    if not stocks:
        print("获取股票列表失败")
        return
    if 1:
        num_random_stocks = 10
        # 随机选取10支不重复股票
        selected_indices = np.random.choice(len(stocks), size=num_random_stocks, replace=False)
        
        for idx in selected_indices:
            stock = stocks[idx]
            code = stock['code']
            code, data = load_stock_data(code)
            if data is not None:
                cerebro.adddata(bt.feeds.PandasData(dataname=data, name=code))
                print(f'成功加载股票: {code}')
            else:
                print(f'股票加载失败: {code}')
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
            future_to_stock = {executor.submit(load_stock_data, stock['code']): stock   for stock in stocks}
            for future in concurrent.futures.as_completed(future_to_stock):
                stock_code, data = future.result()
                if data is not None:
                    cerebro.adddata(bt.feeds.PandasData(dataname=data, name=stock_code))
    
    print(f"成功加载 {len(cerebro.datas)} 支股票数据")
    # 设置初始资金
    cerebro.broker.setcash(1000000.0)
    
    # 添加策略
    cerebro.addstrategy(strategy)
    
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
    for data in cerebro.datas:
        data.plotinfo.plot = False
    # 绘制图表
    cerebro.plot(style='candlestick', volume=False, barup='red', bardown='green')


if __name__ == '__main__':
    run_strategy(UnsupervisedStrategy)