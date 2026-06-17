from typing import List
import joblib
import numpy as np
import pandas as pd
import torch
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler
from model_training_lstm_pytorch import LSTMModel
from data_feed import StockData

class Stock_Prediction:
    def __init__(self, code, name, current_close, predicted_close, predicted_gain):
        self.code = code
        self.name = name
        self.current_close = current_close
        self.predicted_close = predicted_close
        self.predicted_gain = predicted_gain

    def __repr__(self):
        return f"股票: {self.code}, {self.name}, 当前收盘价: {self.current_close:.3f}, 预测收盘价: {self.predicted_close:.3f}, 预测涨幅: {self.predicted_gain:.3%}"
def load_stock_data(code, lookback=60):
    stock_data = StockData(data_type='fund')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback * 2)

    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)

    if df is None or len(df) < lookback:
        print(f"数据加载失败或长度不足: {code}")
        return None

    df = df[['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']]
    return df

def prepare_features(df, lookback, scaler):
    if len(df) < lookback:
        print("数据长度不足以生成特征")
        return None

    stock_data = np.array([
        [df['open'].iloc[-i], df['high'].iloc[-i], df['low'].iloc[-i],
         df['close'].iloc[-i], df['volume'].iloc[-i],
         df['amount'].iloc[-i], df['turnover'].iloc[-i]]
        for i in range(lookback, 0, -1)
    ])

    scaled_data = scaler.transform(stock_data)
    return scaled_data.reshape(1, lookback, 7)

def detect_signals(code, name, model, scaler, lookback=60, threshold_buy=0.05, threshold_sell=-0.05):
    df = load_stock_data(code, lookback)
    if df is None:
        return

    features = prepare_features(df, lookback, scaler)
    if features is None:
        return

    features_tensor = torch.tensor(features, dtype=torch.float32).to(model.device)
    with torch.no_grad():
        prediction = model(features_tensor).cpu().numpy()

    # 反归一化预测值
    prediction_copies = np.repeat(prediction, 7, axis=-1)
    pred_values = scaler.inverse_transform(prediction_copies)[:, 0]

    # 当前收盘价
    current_close = df['close'].iloc[-1]
    predicted_close = pred_values[0]

    predicted_gain = (predicted_close - current_close) / current_close
    advice = None
    if predicted_gain > threshold_buy:
        advice = "建议买入"
    elif predicted_gain < threshold_sell:
        advice = "建议卖出"
    else:
        advice = "无明显买卖信号"
    print(f"股票: {code}, {name} ", f"当前收盘价: {current_close:.3f}, 预测收盘价: {predicted_close:.3f}, 预测涨幅: {predicted_gain:.3%}, ", advice)
    return Stock_Prediction(code, name, current_close, predicted_close, predicted_gain)

if __name__ == '__main__':
    # 加载模型
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = LSTMModel(input_size=7, hidden_size1=128, hidden_size2=64, output_size=1).to(device)
    model.load_state_dict(torch.load('models/best_lstm_model_state.pth', map_location=device))
    model.eval()

    # 加载Scaler
    scaler = joblib.load('models/lstm_scaler.pkl')

    # 检测信号
    stock_data = StockData(data_type='fund')
    stocks = stock_data.get_data_list(update=False)
    if not stocks:
        print("获取股票列表失败")
        exit()
    import random
    random.shuffle(stocks)
    # stocks = stocks[:1]

    pred_all  = []
    for stock in stocks:
        code = stock['code']
        name = stock['name']
        pred = detect_signals(code, name, model, scaler)
        if pred:
            pred_all.append(pred)
    #按照预测涨幅排序
    pred_all.sort(key=lambda x: x.predicted_gain, reverse=True)
    #打印前5个和后5个
    print("前5个预测结果:")
    for p in pred_all[:5]:
        print(p)
    print("后5个预测结果:")
    for p in pred_all[-5:]:
        print(p)