import backtrader as bt
import numpy as np
import pandas as pd
import joblib

from datetime import datetime, timedelta
from data_feed import StockData

class CustomData(bt.feeds.PandasData):
    # 增加新的数据列
    lines = ('amount', 'turnover',)
    
    # 设定数据列在 DataFrame 中的索引位置（从0开始）
    params = (
        ('amount', -1),   # 假设 amount 在第7列
        ('turnover', -1), # 假设 turnover 在第8列
    )

class LSTMStrategy(bt.Strategy):
    params = (
        ('lookback', 60),  # 用于特征的历史数据长度
        ('prediction_horizon', 1),  # 预测未来的天数
        ('use_pytorch', True),  # 使用PyTorch模型的开关
        ('data_type', 'stock'),  # 新增数据类型参数
        ('redemption_fee', 0.005),  # 基金赎回费率
        ('subscription_fee', 0.015)  # 基金申购费率
    )

    def __init__(self):
        self.first_day = True
        if self.p.use_pytorch:
            from model_training_lstm_pytorch import LSTMModel
            import torch
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            
            input_size = 7
            hidden_size1 = 128
            hidden_size2 = 64
            output_size = 1
            self.model = LSTMModel(input_size, hidden_size1, hidden_size2, output_size).to(self.device)
        

            try:
                state_dict = torch.load('models/best_lstm_model_state.pth', map_location=torch.device(self.device))
                self.model.load_state_dict(state_dict)
                self.model.eval()
                print('成功加载PyTorch模型 best_lstm_model_state.pth')
            except Exception as e:
                print(f'加载PyTorch模型失败: {str(e)}')
                self.model = None
        else:
            from keras.models import load_model
            try:
                self.model = load_model('models/best_lstm_model.h5')
                print('成功加载Keras模型 best_lstm_model.h5')
            except Exception as e:
                print(f'加载Keras模型失败: {str(e)}')
                self.model = None

        try:
            self.scaler = joblib.load('models/lstm_scaler.pkl')
            print('成功加载 scaler')
        except Exception as e:
            print(f'加载 scaler 失败: {str(e)}')
        self.order = None
        self.dataclose = self.datas[0].close

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

        if self.p.use_pytorch:
            import torch
            predictions = []
            # 逐个处理每个基金的特征
            for i in range(len(features)):
                feature = torch.tensor(features[i:i+1], dtype=torch.float32).to(self.device)
                with torch.no_grad():
                    pred = self.model(feature).to('cpu').numpy()
                    predictions.append(pred)
            predictions = np.concatenate(predictions, axis=0)
        else:
            predictions = self.model.predict(features)

        prediction_copies_array = np.repeat(predictions, 7, axis=-1)
        pred_values = self.scaler.inverse_transform(np.reshape(prediction_copies_array, (len(predictions), 7)))[:, 0]

        # 收集所有预测收益率
        pred_gains = []
        for i, pred_value in enumerate(pred_values):
            data_idx = indices[i]
            close_price = self.datas[data_idx].close[0]
            pred_gain = (pred_value - close_price) / close_price
            pred_gains.append((data_idx, pred_gain))
        
        # 按收益率降序排序
        sorted_stocks = sorted(pred_gains, key=lambda x: x[1], reverse=True)
        
        # 选择前3名
        top3 = sorted_stocks[:3]
        print(f'Top3预测收益率: {[f"{x[1]:.2%}" for x in top3]}')
        
        # 等权重买入前3名
        cash_per_stock = self.broker.getcash() / 100
        for data_idx, gain in sorted_stocks:
            data = self.datas[data_idx]
            # if gain > 0.4:
            if gain > 0.01 or self.first_day:
                size = int(cash_per_stock / data.close[0])
                self.buy(data=data, size=size)
        
        self.first_day = False


        # 等权重卖出后3名
        for data_idx, gain in sorted_stocks:
            # if gain < -0.3:
            if gain < -0.01:
                pos = self.getposition(data)
                if pos.size > 0:
                    self.sell(data=data, size=pos.size * 0.3)

    def prepare_features(self):
        features = []
        indices = []
        
        # 定义特征列名
        feature_names = ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']
        
        for data in self.datas:
            index = self.datas.index(data)
            if len(data) < self.p.lookback:
                continue
            
            stock_data = pd.DataFrame([[data.open[-self.params.lookback + i], 
                                      data.high[-self.params.lookback + i], 
                                      data.low[-self.params.lookback + i], 
                                      data.close[-self.params.lookback + i], 
                                      data.volume[-self.params.lookback + i], 
                                      data.amount[-self.params.lookback + i], 
                                      data.turnover[-self.params.lookback + i]] 
                                     for i in range(self.params.lookback)],
                                    columns=feature_names)
            
            # 数据标准化并重塑为LSTM输入形状
            scaled_data = self.scaler.transform(stock_data)
            features.append(scaled_data.reshape(1, self.p.lookback, 7))
            indices.append(index)
        
        if not features:
            return None, None
            
        return np.vstack(features), indices

def load_stock_data(code):
    stock_data = StockData(data_type='fund')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180 + 60)

    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)

    if df is None:
        print(f"获取数据失败: {code}")
        return code, None

    if len(df) < 30:
        print(f"数据长度不足: {code}")
        return code, None

    df = df[['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']]
    
    return code, df


def run_strategy(strategy: bt.Strategy):
    cerebro = bt.Cerebro()

    stock_data = StockData(data_type='fund')
    stocks = stock_data.get_data_list(update=False)
    if not stocks:
        print("获取股票列表失败")
        return
    num_random_stocks = 1
    import random
    random.shuffle(stocks)
    # selected_indices = np.random.choice(len(stocks), size=num_random_stocks, replace=False)
    selected_indices = []
    #提取stock['code']=518880的idx
    for idx in range(len(stocks)):
        if stocks[idx]['code'] in ['518880', '510880', '512880', '588190', '510300']:
            selected_indices.append(idx)
    
    for idx in selected_indices:
        stock = stocks[idx]
        code = stock['code']
        code, df = load_stock_data(code)
        if df is not None:
            data = CustomData(dataname=df, name=code,
                                open='open',
                                high='high',
                                low='low',
                                close='close',
                                volume='volume',
                                amount='amount',
                                turnover='turnover')
            cerebro.adddata(data)
            print(f'成功加载股票: {code}')
        else:
            print(f'股票加载失败: {code}')

    print(f"成功加载 {len(cerebro.datas)} 支股票数据")
    cerebro.broker.setcash(1000000.0)

    cerebro.addstrategy(strategy)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio)
    cerebro.addanalyzer(bt.analyzers.DrawDown)

    results = cerebro.run()

    strategy = results[0]
    for idx in selected_indices:
        stock = stocks[idx]
        print(f'股票: {stock["code"]}, {stock["name"]}')
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    sharpe_ratio = strategy.analyzers.sharperatio.get_analysis()["sharperatio"]
    if sharpe_ratio is None:
        sharpe_ratio = 0.0
    print(f'夏普比率: {sharpe_ratio:.2f}')
    print(f'最大回撤: {strategy.analyzers.drawdown.get_analysis()["max"]["drawdown"]:.2f}%')


    cerebro.plot(style='candlestick', volume=False, barup='red', bardown='green', barupfill= False, bardownfill= True)

if __name__ == '__main__':
    run_strategy(LSTMStrategy)