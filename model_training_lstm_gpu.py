import backtrader as bt
import numpy as np
import pandas as pd
from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout
from scikeras.wrappers import KerasRegressor
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime, timedelta
from data_feed import StockData
import matplotlib.pyplot as plt
from keras.losses import MeanSquaredError  # 显式导入损失函数
from keras.models import load_model
import joblib
import tensorflow as tf
from keras.callbacks import EarlyStopping, ModelCheckpoint
import matplotlib.font_manager as fm


# 设置字体以支持中文显示
font_path = 'C:/Windows/Fonts/simhei.ttf'  # 黑体字体路径
font_prop = fm.FontProperties(fname=font_path)
plt.rcParams['font.family'] = font_prop.get_name()

# 配置GPU
physical_devices = tf.config.list_physical_devices('GPU')
if len(physical_devices) > 0:
    tf.config.experimental.set_memory_growth(physical_devices[0], True)
    print('GPU is available')
else:
    print('No GPU available')

# 数据加载函数
def load_stock_data(code):
    stock_data = StockData()
    # end_date = datetime.now()
    # start_date = end_date - timedelta(days=365 + 10)
    # 获取从2012年1月1日至2022年6月1日的历史数据
    start_date = datetime(2012, 1, 1)
    end_date = datetime(2022, 6, 1)

    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)
    if df is None:
        print(f"获取数据失败: {code}")
        return None

    df = df[['open', 'high', 'low', 'close', 'volume']]

    if df is None:
        print(f"获取数据失败: {code}")
        return None

    if len(df) < 10:
        print(f"数据长度不足: {code}")
        return None
    
    return df

# 标签提取
def input_func(data_allstocks, past_days):
    x_li = []
    y_li = []
    for data_onestock in data_allstocks:
        for i in range(past_days, len(data_onestock)):
            x_li.append(data_onestock[i - past_days:i, :])
            y_li.append(data_onestock[i, -2])
    return np.array(x_li), np.array(y_li)

# 模型搭建函数
def build_model(optimizer='adam', input_shape=(30, 5)):
    grid_model = Sequential()
    grid_model.add(LSTM(128, return_sequences=True, input_shape=input_shape, 
                       kernel_initializer='he_normal'))
    grid_model.add(Dropout(0.3))
    grid_model.add(LSTM(64, return_sequences=False))
    grid_model.add(Dropout(0.3))
    grid_model.add(Dense(32, activation='relu'))
    grid_model.add(Dense(1))
    
    mse = MeanSquaredError()
    grid_model.compile(loss=mse, optimizer=optimizer)
    return grid_model


# 模型训练主函数
if __name__ == '__main__':
    
    stock_data = StockData()
    stocks = stock_data.get_stock_list(update=False)
    if not stocks:
        print("获取股票列表失败")
    df_for_training = []
    df_for_testing = []

    #取前5只股票
    for stock in stocks[:1]:

        # 加载股票数据（示例使用平安银行）
        code = stock['code']
        code = '300218.SZ'
        df_onestock = load_stock_data(code)
        if df_onestock is None:
            print(f"加载数据失败: {code}")
            continue

        # 划分数据集
        test_split = round(len(df_onestock) * 0.1)
        df_onestock_for_training = df_onestock[:-test_split]
        print(df_onestock_for_training.shape)

        df_onestock_for_training = df_onestock_for_training.dropna(how='any')
        print(df_onestock_for_training.shape)
        df_for_training.append(df_onestock_for_training)

        df_onestock_for_testing = df_onestock[-test_split:]
        print(df_onestock_for_testing.shape)
        df_for_testing.append(df_onestock_for_testing)

    if not df_for_training:
        print("没有可用的训练数据")
        exit()
    # 对训练、测试数据进行缩放
    scaler = None
    scaler_old = False
    try:
        # 尝试加载 scaler
        scaler = joblib.load('D:\\work\\quant\\stock_data\\lstm_scaler.pkl')
        print('成功加载 scaler')
        scaler_old = True
    except Exception as e:
        print(f'加载 scaler 失败: {str(e)}')
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaler_old = False
        df_concatenated = pd.concat(df_for_testing)
        scaler.fit(df_concatenated)
    for i in range(len(df_for_training)):
        df_for_training[i] = scaler.transform(df_for_training[i])
    for i in range(len(df_for_testing)):
        df_for_testing[i] = scaler.transform(df_for_testing[i])

    # 保存 scaler
    if not scaler_old:
        joblib.dump(scaler, 'D:\\work\\quant\\stock_data\\lstm_scaler.pkl')
        print('scaler 已保存为 lstm_scaler.pkl')
        
    # 生成测试数据
    train_X, train_Y = input_func(df_for_training, 30)
    test_X, test_Y = input_func(df_for_testing, 30)

    best_model = None
    try:
        best_model = load_model('D:\\work\\quant\\stock_data\\best_lstm_model.h5')
        print('成功加载模型 best_lstm_model.h5')
    except Exception as e:
        print(f'加载模型失败: {str(e)}')

        grid_model = KerasRegressor(
            build_fn=build_model,
            verbose=1
        )
        
        # 修改参数网格，适应GPU训练
        parameters = {
            'batch_size': [32, 64], 
            'epochs': [15, 20], 
            'optimizer': ['adam']
        }

        # 添加回调函数
        callbacks = [
            EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
            ModelCheckpoint('D:\\work\\quant\\stock_data\\best_lstm_model.h5', 
                          monitor='val_loss', 
                          save_best_only=True)
        ]

        grid_search = GridSearchCV(
            estimator=grid_model, 
            param_grid=parameters, 
            cv=2,
            n_jobs=1  # 使用GPU时保持为1
        )
        
        # 使用更大的batch_size进行训练
        grid_search = grid_search.fit(
            train_X, 
            train_Y,
            callbacks=callbacks
        )

        if not hasattr(grid_search, 'best_estimator_'):
            raise ValueError("网格搜索失败，请检查训练日志")

        print("最佳参数:", grid_search.best_params_)
        print("验证集最佳得分:", grid_search.best_score_)

        # 检查输入数据维度
        print("训练数据维度:", train_X.shape)
        print("测试数据维度:", test_X.shape)
        best_estimator = grid_search.best_estimator_
        if best_estimator is None:
            raise ValueError("未找到有效模型，请检查参数组合和训练日志")
        best_model = best_estimator.model_
        if best_model is None:
            raise RuntimeError("模型加载失败，请检查模型构建函数")
        # 保存模型和 scaler
        best_model.save('D:\\work\\quant\\stock_data\\best_lstm_model.h5')
        print('模型已保存为 best_lstm_model.h5')

        # 检查模型是否可预测
        test_sample = test_X[:1]  # 取第一个样本测试
        try:
            best_model.predict(test_sample)
            # 保存模型
            best_model.save('D:\\work\\quant\\stock_data\\best_lstm_model.h5')
            print('模型已保存为 best_lstm_model.h5')
        except Exception as e:
            raise RuntimeError(f"模型预测测试失败: {str(e)}")
    prediction = best_model.predict(test_X)
    print("预测数据维度:", prediction.shape)  # 添加打印预测数据维度的代码

    prediction_copies_array = np.repeat(prediction,5, axis=-1)
    pred=scaler.inverse_transform(np.reshape(prediction_copies_array,(len(prediction),5)))[:,0]

    original_copies_array = np.repeat(test_Y,5, axis=-1)
    original=scaler.inverse_transform(np.reshape(original_copies_array,(len(test_Y),5)))[:,0]

    plt.plot(original, color='red', label='真实股价')
    plt.plot(pred, color='blue', label='预测股价')
    plt.title('预测股价')
    plt.xlabel('时间')
    plt.ylabel('股票价格')
    plt.legend()
    plt.show()

