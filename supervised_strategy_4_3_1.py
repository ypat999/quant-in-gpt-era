import backtrader as bt
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import MinMaxScaler

import backtrader as bt
import concurrent
from datetime import datetime, timedelta
from data_feed import StockData

class SupervisedStrategy(bt.Strategy):
    """基于监督学习的交易策略"""
    params = (
        ('lookback', 10),  # 用于特征的历史数据长度
        ('prediction_horizon', 1),  # 预测未来的天数
        ('top_n', 3),  # 选择排名靠前的股票数量
    )

    def __init__(self):
        # 加载预训练模型
        self.model = joblib.load('D:\\work\\quant\\stock_data\\lgbm_model.pkl')
        self.scaler = joblib.load('D:\\work\\quant\\stock_data\\lgbm_scaler.pkl')
        self.order = None
        self.dataclose = self.datas[0].close
        
    def prepare_features(self):
        """准备模型输入特征"""
        features = []
        indices = []
        max_size = self.p.lookback + 20  # 使用合理的数据长度

        for data in self.datas:
            index = self.datas.index(data)
            # 获取最近的数据
            if len(data) < max_size:
                continue
            
            recent_data = pd.DataFrame({
                'close': data.close.get(size=max_size),
                'volume': data.volume.get(size=max_size),
                'high': data.high.get(size=max_size),
                'low': data.low.get(size=max_size)
            })
            
            # 检查数据是否为空
            if recent_data.empty:
                continue
            
            # 计算特征
            recent_data['return'] = recent_data['close'].pct_change()
            recent_data['ma_10'] = recent_data['close'].rolling(window=10, min_periods=1).mean()
            recent_data['ma_20'] = recent_data['close'].rolling(window=20, min_periods=1).mean()
            recent_data['volatility'] = recent_data['close'].rolling(window=10, min_periods=1).std()
            recent_data['amount'] = recent_data['volume'] * recent_data['close']
            recent_data.dropna(inplace=True)
            
            # 检查处理后的数据是否为空
            if recent_data.empty:
                continue
            
            num_rows = 1
            stock_feature = np.empty((num_rows, 50))
            i = len(recent_data) - 1
            # 正确reshape为(1,50)维特征
            raw_features = recent_data.iloc[i-10:i][['close', 'volume', 'ma_10', 'ma_20', 'volatility']].values.reshape(1, -1)[:,:50]
            stock_feature[0] = self.scaler.transform(raw_features)
            features.extend(stock_feature)
            indices.append(index)
        
        if features == []:
            return None, None
        return np.array(features), np.array(indices)
        
    def next(self):
        if self.model is None:
            print("模型未加载")
            return
            
        if self.order:
            print("order")
            return
            
        features, indices = self.prepare_features()
        if features is None:
            print("特征为空")
            return
        #print(features)
        predictions = self.model.predict_proba(features)[:, 1]
        
        # 将predictions和indices组合起来排序
        combined = list(zip(predictions, indices))
        #print(combined)
        combined.sort(key=lambda x: x[0], reverse=True)
        #去除概率小于0.5的股票
        combined = [x for x in combined if x[0] > 0.5]
        # 选择排名靠前的股票
        choose_len = self.p.top_n
        if len(combined) < self.p.top_n:
            choose_len = len(combined)
        combined = [x for x in combined[:choose_len]]
        top_indices = [x[1] for x in combined]
        
        # 打印预测结果
        for i, d in enumerate(self.datas):
            if i in top_indices:
                print(f"{d._name}: 预测买入")
            elif self.getposition(d).size > 0:
                print(f"{d._name}: 预测卖出")
                self.close(d)

        if len(top_indices) == 0:
            return

        # 对top_n股票等权重分配
        target_value = self.broker.get_value() / len(top_indices)
        for i in top_indices:
            data = self.datas[i]
            pos = self.getposition(data).size
            if pos == 0:
                size = int(target_value / data.close[0])
                self.buy(data=data, size=size)


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
    run_strategy(SupervisedStrategy)