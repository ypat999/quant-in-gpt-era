import backtrader as bt
import numpy as np
import pandas as pd
import joblib
import torch
from datetime import datetime, timedelta
from data_feed import StockData
from stock_cnn import CNNModel

class CustomData(bt.feeds.PandasData):
    # 增加新的数据列
    lines = ('amount', 'turnover',)
    
    # 设定数据列在 DataFrame 中的索引位置（从0开始）
    params = (
        ('amount', -1),   # 假设 amount 在第7列
        ('turnover', -1), # 假设 turnover 在第8列
    )

class CNNStrategy(bt.Strategy):
    params = (
        ('lookback', 60),
        ('prediction_horizon', 1),
    )

    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = CNNModel(input_size=7, output_size=1).to(self.device)
        
        try:
            state_dict = torch.load('D:\\work\\quant\\stock_data\\best_cnn_model_state.pth', map_location=self.device)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            print('成功加载CNN模型 best_cnn_model_state.pth')
        except Exception as e:
            print(f'加载CNN模型失败: {str(e)}')
            self.model = None

        try:
            self.scaler = joblib.load('D:\\work\\quant\\stock_data\\cnnscaler.pkl')
        except Exception as e:
            print(f'加载scaler失败: {str(e)}')
        
        self.order = None
        self.dataclose = self.datas[0].close

    def next(self):
        if self.model is None:
            return

        features, indices = self.prepare_features()
        if features is None or len(features) == 0:
            return

        with torch.no_grad():
            inputs = torch.tensor(features, dtype=torch.float32).to(self.device)
            predictions = self.model(inputs).cpu().numpy()

        prediction_copies = np.repeat(predictions, 7, axis=-1)
        pred_values = self.scaler.inverse_transform(prediction_copies.reshape(-1,7))[:,0]

        pred_gains = []
        for i, pred_value in enumerate(pred_values):
            data_idx = indices[i]
            close_price = self.datas[data_idx].close[0]
            pred_gain = (pred_value - close_price) / close_price
            pred_gains.append((data_idx, pred_gain))

        sorted_stocks = sorted(pred_gains, key=lambda x: x[1], reverse=True)
        top3 = sorted_stocks[:3]

        cash_per_stock = self.broker.getcash() / 5
        for data_idx, gain in top3:
            if gain > 0.4:
                data = self.datas[data_idx]
                size = int(cash_per_stock / data.close[0])
                self.buy(data=data, size=size)

        for data_idx, gain in sorted_stocks:
            if gain < -0.1:
                data = self.datas[data_idx]
                pos = self.getposition(data)
                if pos.size > 0:
                    self.sell(data=data, size=pos.size * 0.3)

    def prepare_features(self):
        # 修改特征处理逻辑以适应CNN输入维度
        features = []
        indices = []
        
        for data in self.datas:
            if len(data) < self.params.lookback:
                continue
            
            # 获取过去30天的5维特征数据
            stock_data = np.array([[data.open[-i], data.high[-i], data.low[-i], 
                                  data.close[-i], data.volume[-i],
                                  data.amount[-i], data.turnover_rate[-i]] 
                                 for i in range(self.params.lookback)])
            
            # 数据标准化并重塑为CNN输入形状 (batch, features, time_steps)
            scaled_data = self.scaler.transform(stock_data)
            cnn_input = scaled_data.reshape(1, self.params.lookback, 7)
            
            features.append(cnn_input)
            indices.append(self.datas.index(data))

        if not features:
            return None, None
            
        return np.vstack(features), indices

def load_stock_data(code):
    stock_data = StockData()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 + 30)
    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)
    if df is None or len(df) < 10:
        print(f"获取数据失败或数据长度不足: {code}")
        return None
    return df[['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']]


def run_strategy(strategy: bt.Strategy):
    cerebro = bt.Cerebro()

    stock_data = StockData()
    stocks = stock_data.get_stock_list(update=False)
    if not stocks:
        print("获取股票列表失败")
        return
    
    num_random_stocks = 1
    selected_indices = np.random.choice(len(stocks), size=num_random_stocks, replace=False)

    for idx in selected_indices:
        stock = stocks[idx]
        code = stock['code']
        df = load_stock_data(code)
        if df is not None:
            data = bt.feeds.PandasData(dataname=df, name=code)
            cerebro.adddata(data)
            print(f'成功加载股票: {code}')
        else:
            print(f'股票加载失败: {code}')

    print(f"成功加载 {len(cerebro.datas)} 支股票数据")
    cerebro.broker.setcash(1000000.0)
    cerebro.addstrategy(strategy)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    results = cerebro.run()
    strat = results[0]

    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    sharpe = strat.analyzers.sharpe.get_analysis()
    print(f'夏普比率: {sharpe["sharperatio"]:.2f}' if sharpe["sharperatio"] else '夏普比率: N/A')
    print(f'最大回撤: {strat.analyzers.drawdown.get_analysis()["max"]["drawdown"]:.2f}%')

    cerebro.plot(style='candlestick', volume=False, barup='red', bardown='green')

if __name__ == '__main__':
    run_strategy(CNNStrategy)