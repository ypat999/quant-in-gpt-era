import os
os.environ['PYTHON_GIL'] = '0'

import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime, timedelta
from data_feed import StockData
import joblib
import concurrent.futures
from threading import Lock
import time


class ModelTrainer:
    def __init__(self):
        self.scaler = MinMaxScaler()
        self.model = LGBMClassifier(device='gpu')

    def prepare_data(self):
        if os.path.exists('D:\\work\\quant\\stock_data\\features.csv') and os.path.exists('D:\\work\\quant\\stock_data\\targets.csv'):
            features = pd.read_csv('D:\\work\\quant\\stock_data\\features.csv').values
            targets = pd.read_csv('D:\\work\\quant\\stock_data\\targets.csv').values.flatten()
            return features, targets

        
        """准备训练数据"""
        stock_data = StockData()
        stocks = stock_data.get_stock_list(update=False)
        features = []
        targets = []
        lock = Lock()

        def process_stock(stock):
            start = time.time()
            code = stock['code']
            
            df = stock_data.get_history_data(code, start_date=datetime.now() - timedelta(days=365*6), end_date=datetime.now()- timedelta(days=365*1), local_only=True)
            
            if df is not None:
                df['date'] = pd.to_datetime(df.index)
                df.set_index('date', inplace=True)
                if df is None or len(df) < 100:
                    print(f"获取数据失败: {code}")
                    return
                step1 = time.time()

                # 计算技术指标
                df['return'] = df['close'].pct_change()
                df['ma_10'] = df['close'].rolling(window=10, min_periods=1).mean()
                df['ma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
                df['volatility'] = df['close'].rolling(window=10, min_periods=1).std()
                df['amount'] = df['volume'] * df['close']
                df.dropna(inplace=True)
                step2 = time.time()

                # 生成特征和目标
                num_rows = len(df) - 11
                stock_features = np.empty((num_rows, 50))
                stock_targets = np.empty(num_rows, dtype=int)
                for i in range(10, len(df)-1):
                    stock_features[i - 10] = df.iloc[i-10:i][['close', 'volume', 'ma_10', 'ma_20', 'volatility']].values.reshape(-1, 50)
                    stock_targets[i - 10] = 1 if df.iloc[i+1]['close'] > df.iloc[i]['close'] else 0
                step3 = time.time()

                with lock:
                    features.extend(stock_features)
                    targets.extend(stock_targets)

                print(f"处理股票 {code} 完成，耗时：{time.time() - start}，计算技术指标耗时：{step2 - step1}，生成特征和目标耗时：{step3 - step2}")
            else:
                print(f"获取数据失败: {code}")

        # 使用线程池处理股票数据
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            executor.map(process_stock, stocks)
        
        # 保存特征和目标数据为CSV文件
        print("保存特征和目标数据为CSV文件")
        pd.DataFrame(features).to_csv('D:\\work\\quant\\stock_data\\features.csv', index=False)
        pd.DataFrame(targets).to_csv('D:\\work\\quant\\stock_data\\targets.csv', index=False)
        return np.array(features), np.array(targets)
        
    def train(self):
        """训练模型"""
        features, targets = self.prepare_data()
        if len(features) == 0:
            raise ValueError("没有可用的训练数据，请检查数据源或股票筛选条件")
        print("开始训练模型")
        features = self.scaler.fit_transform(features)
        self.model.fit(features, targets)
        print("模型训练完成")
        self.save_model()

    def save_model(self):
        """保存模型"""
        joblib.dump(self.model, 'D:\\work\\quant\\stock_data\\lgbm_model.pkl')
        joblib.dump(self.scaler, 'D:\\work\\quant\\stock_data\\scaler.pkl')

if __name__ == '__main__':
    trainer = ModelTrainer()
    trainer.train()