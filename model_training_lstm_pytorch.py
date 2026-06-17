import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime
from data_feed import StockData
import matplotlib.pyplot as plt
import joblib
from sklearn.model_selection import ParameterGrid
import matplotlib.font_manager as fm

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# 设置字体以支持中文显示
font_path = 'C:/Windows/Fonts/simhei.ttf'  # 黑体字体路径
font_prop = fm.FontProperties(fname=font_path)
plt.rcParams['font.family'] = font_prop.get_name()

# 数据加载函数
def load_data(code, data_type='stock'):
    """
    :param data_type: 'stock'股票 | 'fund'基金
    """
    stock_data = StockData(data_type=data_type)
    start_date = datetime(1990, 1, 1)
    end_date = datetime(2025, 1, 1)
    
    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)
    if df is None or len(df) < 100:
        print(f"获取{data_type}数据失败或数据长度不足: {code}")
        return None
    
    df = df[['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']]
    # 去除close为0的行
    # df = df[df['close'] != 0]
    # df = df[df['volume'] != 0]
    # #open、high、low、close、volume做pct_change, amount、turnover不变
    
    # df_pct = df[1:].reset_index(drop=True).copy()
    # df_cut = df[:-1].reset_index(drop=True).copy()
    # df_pct['close'] = (df_pct['close'] - df_cut['close']) / df_cut['close']
    # df_pct['open'] = (df_pct['open'] - df_cut['close']) / df_cut['close']
    # df_pct['high'] = (df_pct['high'] - df_cut['close']) / df_cut['close']
    # df_pct['low'] = (df_pct['low'] - df_cut['close']) / df_cut['close']
    # df_pct['volume'] = (df_pct['volume'] - df_cut['volume']) / df_cut['volume']
    #   # 将NaN替换为1，表示没有变化
    
    # return df_pct
    return df

# 标签提取
def input_func(data_allstocks, past_days):
    x_li = []
    y_li = []
    for data_onestock in data_allstocks:
        # 确保 data_onestock 是 NumPy 数组
        if isinstance(data_onestock, pd.DataFrame):
            data_onestock = data_onestock.values
        for i in range(past_days, len(data_onestock)):
            x_li.append(data_onestock[i - past_days:i, :])  # 输入特征
            y_li.append([data_onestock[i, 3]])  # 标签，假设第4列是目标值
    return np.array(x_li), np.array(y_li)

# LSTM 模型定义
class LSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size1, hidden_size2, output_size):
        super(LSTMModel, self).__init__()
        self.lstm1 = nn.LSTM(input_size, hidden_size1, batch_first=True)
        self.dropout1 = nn.Dropout(0.3)
        self.lstm2 = nn.LSTM(hidden_size1, hidden_size2, batch_first=True)
        self.dropout2 = nn.Dropout(0.3)
        self.fc1 = nn.Linear(hidden_size2, 32)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, output_size)
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f'Using {device}')
    
    def forward(self, x):
        h_0 = torch.zeros(1, x.size(0), self.lstm1.hidden_size).to(self.device)
        c_0 = torch.zeros(1, x.size(0), self.lstm1.hidden_size).to(self.device)
        out, _ = self.lstm1(x, (h_0, c_0))
        out = self.dropout1(out)
        
        h_1 = torch.zeros(1, x.size(0), self.lstm2.hidden_size).to(self.device)
        c_1 = torch.zeros(1, x.size(0), self.lstm2.hidden_size).to(self.device)
        out, _ = self.lstm2(out, (h_1, c_1))
        out = self.dropout2(out)
        
        out = self.fc1(out[:, -1, :])
        out = self.relu(out)
        out = self.fc2(out)
        return out

# 模型训练主函数
if __name__ == '__main__':
    print(f'Using {device}')
    
    # 通过参数控制数据类型
    data_type = 'fund'  # 切换为基金模式时修改此处
    stock_data = StockData(data_type=data_type)
    data_list = stock_data.get_data_list(update=False)
    if not data_list:
        print("获取股票列表失败")
    df_for_training = []
    df_for_testing = []
    df_all = []
    train_X = []
    train_Y = []
    test_X = []
    test_Y = []

    # 随机取1/5的股票
    import random
    random.shuffle(data_list)
    # data_list = data_list[:1]
    # 根据数据类型处理数据项
    print('加载数据')
    for item in data_list:
        code = item['code']
        df_onestock = load_data(code, data_type=data_type)
        if df_onestock is None:
            continue
        df_all.append(df_onestock)

        #######
        df_x, df_y = input_func([df_onestock], 60)
        data = list(zip(df_x, df_y))

        
        np.random.shuffle(data)  # 打乱顺序
        df_x, df_y = zip(*data)  # 解压回 df_x 和 df_y
        df_x = np.array(df_x)  # 转换为 NumPy 数组
        df_y = np.array(df_y)  # 转换为 NumPy 数组
        #划分数据集
        train_X.append(df_x[:-int(len(df_x) * 0.1)])
        train_Y.append(df_y[:-int(len(df_y) * 0.1)])
        test_X.append( df_x[-int(len(df_x) * 0.1):])
        test_Y.append( df_y[-int(len(df_y) * 0.1):])

        # # 划分数据集
        # test_split = round(len(df_onestock) * 0.1)
        # df_onestock_for_training = df_onestock[:-test_split]
        # df_for_training.append(df_onestock_for_training)
        # df_onestock_for_testing = df_onestock[-test_split:]
        # df_for_testing.append(df_onestock_for_testing)

    # if not df_for_training:
    if not train_X:
        print("没有可用的训练数据")
        exit()
    
    print('读取scaler')
    scaler = None
    scaler_old = False
    try:
        scaler = joblib.load('models/lstm_scaler_etf.pkl')
        scaler_old = True
    except Exception as e:
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaler_old = False
        # df_concatenated = pd.concat(df_for_training)
        df_concatenated = pd.concat(df_all)
        scaler.fit(np.array(df_concatenated))
    # for i in range(len(df_for_training)):
    #     df_for_training[i] = scaler.transform(df_for_training[i])
    # for i in range(len(df_for_testing)):
    #     df_for_testing[i] = scaler.transform(df_for_testing[i])

    print('对训练、测试数据进行缩放')
    # for i in range(len(train_X)):
    #     for j in range(len(train_X[i])):
    #         train_X[i][j] = scaler.transform(train_X[i][j])
    #         train_Y_copies_array = np.repeat(train_Y[i][j], 7, axis=-1)
    #         train_Y[i][j] = scaler.transform(np.reshape(train_Y_copies_array, (1, 7)))[0][3]

    # for i in range(len(test_X)):
    #     for j in range(len(test_X[i])):
    #         test_X[i][j] = scaler.transform(test_X[i][j])
    #         test_Y_copies_array = np.repeat(test_Y[i][j], 7, axis=-1)
    #         test_Y[i][j] = scaler.transform(np.reshape(test_Y_copies_array, (1, 7)))[0][3]
    train_X = np.concatenate(train_X)
    train_Y = np.concatenate(train_Y)
    train_X_shape = train_X.shape
    train_X_reshaped = train_X.reshape(-1, 7)
    train_X_scaled = scaler.transform(train_X_reshaped)
    train_X = train_X_scaled.reshape(train_X_shape)

    train_Y_copies = np.repeat(train_Y, 7, axis=-1)
    train_Y_reshaped = train_Y_copies.reshape(-1, 7)
    train_Y_scaled = scaler.transform(train_Y_reshaped)
    train_Y = train_Y_scaled[:, 3].reshape(train_Y.shape)

    # 向量化处理测试数据
    test_X = np.concatenate(test_X)
    test_Y = np.concatenate(test_Y)
    test_X_shape = test_X.shape
    test_X_reshaped = test_X.reshape(-1, 7)
    test_X_scaled = scaler.transform(test_X_reshaped)
    test_X = test_X_scaled.reshape(test_X_shape)

    test_Y_copies = np.repeat(test_Y, 7, axis=-1)
    test_Y_reshaped = test_Y_copies.reshape(-1, 7)
    test_Y_scaled = scaler.transform(test_Y_reshaped)
    test_Y = test_Y_scaled[:, 3].reshape(test_Y.shape) 

    if not scaler_old:
        joblib.dump(scaler, 'models/lstm_scaler_etf.pkl')

 
    # # 生成训练和测试数据
    # train_X, train_Y = input_func(df_for_training, 60)
    # test_X, test_Y = input_func(df_for_testing, 60)   
    # train_X = np.array(train_X)
    # train_Y = np.array(train_Y)
    # test_X  = np.array(test_X)
    # test_Y  = np.array(test_Y)

    #train_X由(1, 1477, 60, 7)reshape到(1477, 60, 7)
    train_X = train_X.reshape(-1, 60, 7)
    train_Y = train_Y.reshape(-1, 1)
    test_X = test_X.reshape(-1, 60, 7)
    test_Y = test_Y.reshape(-1, 1)
    

    # 新增数据验证
    print(f'训练数据维度: {train_X.shape if isinstance(train_X, np.ndarray) else "N/A"}')
    print(f'测试数据维度: {test_X.shape if isinstance(test_X, np.ndarray) else "N/A"}')
    
    # 修复测试数据集为空的检查
    if len(test_X) == 0 or len(test_Y) == 0:
        print("错误：测试数据集为空，请检查数据划分和输入参数")
        exit()

    train_X = torch.tensor(train_X, dtype=torch.float32).to(device)
    train_Y = torch.tensor(train_Y, dtype=torch.float32).to(device)
    test_X = torch.tensor(test_X, dtype=torch.float32).to(device)
    test_Y = torch.tensor(test_Y, dtype=torch.float32).to(device)

    train_dataset = TensorDataset(train_X, train_Y)
    test_dataset = TensorDataset(test_X, test_Y)

    input_size = 7
    hidden_size1 = 128
    hidden_size2 = 64
    output_size = 1
    model = LSTMModel(input_size, hidden_size1, hidden_size2, output_size).to(device)
    criterion = nn.MSELoss()
    
    try:
        # 加载模型状态
        model.load_state_dict(torch.load('models/best_lstm_model_state_etf.pth'))
        # model = torch.load('models/best_lstm_model_state_etf.pth')
        print('成功加载模型状态 best_lstm_model_state_etf.pth')
        model.eval()
    except Exception as e:
        print(f'加载模型失败: {str(e)}')
        

        parameters = {'batch_size': [20], 'epochs': [15], 'optimizer': ['adam']}
        param_grid = list(ParameterGrid(parameters))

        best_loss = float('inf')
        best_params = None

        for params in param_grid:
            batch_size = params['batch_size']
            epochs = params['epochs']
            optimizer_name = params['optimizer']
            
            # 添加 L2 正则化 (weight_decay 参数)
            optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4) if optimizer_name == 'adam' else \
                        optim.Adadelta(model.parameters(), weight_decay=1e-4)

            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

            for epoch in range(epochs):
                model.train()
                for inputs, targets in train_loader:
                    inputs, targets = inputs.to(device), targets.to(device)  # 确保数据在 GPU 上
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                print(f'Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.8f}')  # 调整损失值显示格式

            model.eval()
            total_loss = 0
            with torch.no_grad():
                for inputs, targets in test_loader:
                    inputs, targets = inputs.to(device), targets.to(device)  # 确保数据在 GPU 上
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                    total_loss += loss.item()
            avg_loss = total_loss / len(test_loader)
            print(f'Params: {params}, Avg Loss: {avg_loss:.8f}')  # 调整损失值显示格式

            if avg_loss < best_loss:
                best_loss = avg_loss
                best_params = params

        print(f'Best Params: {best_params}, Best Loss: {best_loss:.8f}')  # 调整损失值显示格式

        # # 使用最佳参数重新训练模型
        # batch_size = best_params['batch_size']
        # epochs = best_params['epochs']
        # optimizer_name = best_params['optimizer']
        # optimizer = optim.Adam(model.parameters(), lr=0.001) if optimizer_name == 'adam' else optim.Adadelta(model.parameters())

        # train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        # test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

        # for epoch in range(epochs):
        #     model.train()
        #     for inputs, targets in train_loader:
        #         inputs, targets = inputs.to(device), targets.to(device)  # 确保数据在 GPU 上
        #         outputs = model(inputs)
        #         loss = criterion(outputs, targets)
        #         optimizer.zero_grad()
        #         loss.backward()
        #         optimizer.step()
        #     print(f'Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.8f}')  # 调整损失值显示格式

        # 保存模型状态字典
        torch.save(model.state_dict(), 'models/best_lstm_model_state_etf.pth')
        print('模型状态已保存为 best_lstm_model_state_etf.pth')

    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False)
    predictions = []
    with torch.no_grad():
        for inputs, _ in test_loader:
            inputs = inputs.to(device)  # 确保数据在 GPU 上
            outputs = model(inputs)
            predictions.append(outputs.cpu().numpy())
    predictions = np.concatenate(predictions)

    prediction_copies_array = np.repeat(predictions, 7, axis=-1)
    pred = scaler.inverse_transform(np.reshape(prediction_copies_array, (len(predictions), 7)))[:, 3]
    # pred = predictions

    original_copies_array = np.repeat(test_Y.cpu().numpy(), 7, axis=-1)
    original = scaler.inverse_transform(np.reshape(original_copies_array, (len(test_Y), 7)))[:, 3]
    # original = test_Y.cpu().numpy()

    # ratio = np.mean(pred / original)
    # print(f'预测值与真实值的比率: {ratio:.4f}')
    # pred = pred / ratio
    
    plt.plot(original, color='red', label='真实股价')
    plt.plot(pred, color='blue', label='预测股价')
    plt.title('预测股价')
    plt.xlabel('时间')
    plt.ylabel('股票价格')
    plt.legend()
    plt.show()
