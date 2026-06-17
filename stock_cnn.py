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

def get_random_stock_codes(stocks):
    # 随机取1/5的股票
    import random
    random.shuffle(stocks)
    stocks = stocks[:10]
    return stocks

# 数据加载函数
def load_stock_data(code):
    stock_data = StockData()
    start_date = datetime(2014, 1, 1)
    end_date = datetime(2024, 1, 1)
    df = stock_data.get_history_data(code, start_date=start_date, end_date=end_date, local_only=True)
    if df is None or len(df) < 10:
        print(f"获取数据失败或数据长度不足: {code}")
        return None
    return df[['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']]

# 标签提取
def input_func(data_allstocks, past_days):
    x_li = []
    y_li = []
    for data_onestock in data_allstocks:
        for i in range(past_days, len(data_onestock)):
            x_li.append(data_onestock[i - past_days:i, :])
            y_li.append([data_onestock[i, 3]])  # 修改为二维数组
    return np.array(x_li), np.array(y_li)

# CNN 模型定义
class CNNModel(nn.Module):
    def __init__(self, input_size, output_size):
        super(CNNModel, self).__init__()
        # 卷积层组
        self.features = nn.Sequential(
            nn.Conv1d(input_size, 96, kernel_size=11, padding=5),
            nn.LocalResponseNorm(5, alpha=0.0001, beta=0.75),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),
            
            nn.Conv1d(96, 256, kernel_size=5, padding=2),
            nn.LocalResponseNorm(5, alpha=0.0001, beta=0.75),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),
            
            nn.Conv1d(256, 384, kernel_size=3, padding=1),
            nn.ReLU(),
            
            nn.Conv1d(384, 384, kernel_size=3, padding=1),
            nn.ReLU(),
            
            nn.Conv1d(384, 256, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2)
        )
        
        # 自适应池化解决输入尺寸依赖
        self.adaptive_pool = nn.AdaptiveAvgPool1d(6)
        
        # 全连接层组
        self.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(256 * 6, 4096),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(4096, 2048),
            nn.ReLU(),
            nn.Linear(2048, output_size)
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.features(x)
        x = self.adaptive_pool(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        return x

# 模型训练主函数
if __name__ == '__main__':
    print(f'Using {device}')
    
    stock_data = StockData()
    stocks = stock_data.get_stock_list(update=False)
    if not stocks:
        print("获取股票列表失败")
    df_for_training = []
    df_for_testing = []

    # 随机取1/5的股票
    stocks = get_random_stock_codes(stocks)
    for stock in stocks:
        code = stock['code']
        df_onestock = load_stock_data(code)
        if df_onestock is None:
            continue

        # 划分数据集
        test_split = round(len(df_onestock) * 0.1)
        df_onestock_for_training = df_onestock[:-test_split].dropna(how='any')
        df_for_training.append(df_onestock_for_training)
        df_onestock_for_testing = df_onestock[-test_split:]
        df_for_testing.append(df_onestock_for_testing)

    if not df_for_training:
        print("没有可用的训练数据")
        exit()

    # 对训练、测试数据进行缩放
    scaler = None
    scaler_old = False
    try:
        scaler = joblib.load('D:\\work\\quant\\stock_data\\cnn_scaler.pkl')
        scaler_old = True
    except Exception as e:
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaler_old = False
        df_concatenated = pd.concat(df_for_training)
        scaler.fit(df_concatenated)
    for i in range(len(df_for_training)):
        df_for_training[i] = scaler.transform(df_for_training[i])
    for i in range(len(df_for_testing)):
        df_for_testing[i] = scaler.transform(df_for_testing[i])

    if not scaler_old:
        joblib.dump(scaler, 'D:\\work\\quant\\stock_data\\cnnscaler.pkl')

    # 生成训练和测试数据
    past_days = 60
    train_X, train_Y = input_func(df_for_training, past_days)
    test_X, test_Y = input_func(df_for_testing, past_days)

    train_X = torch.tensor(train_X, dtype=torch.float32).to(device)
    train_Y = torch.tensor(train_Y, dtype=torch.float32).to(device)
    test_X = torch.tensor(test_X, dtype=torch.float32).to(device)
    test_Y = torch.tensor(test_Y, dtype=torch.float32).to(device)

    train_dataset = TensorDataset(train_X, train_Y)
    test_dataset = TensorDataset(test_X, test_Y)

    input_size = 7
    output_size = 1
    model = CNNModel(input_size, output_size).to(device)
    criterion = nn.MSELoss()
    
    try:
        # 加载模型状态
        model.load_state_dict(torch.load('D:\\work\\quant\\stock_data\\best_cnn_model_state.pth'))
        print('成功加载模型状态 best_cnn_model_state.pth')
        model.eval()
    except Exception as e:
        print(f'加载模型失败: {str(e)}')
        

        parameters = {'batch_size': [24], 'epochs': [12], 'optimizer': ['adam']}
        param_grid = list(ParameterGrid(parameters))

        best_loss = float('inf')
        best_params = None

        for params in param_grid:
            batch_size = params['batch_size']
            epochs = params['epochs']
            optimizer_name = params['optimizer']
            optimizer = optim.Adam(model.parameters(), lr=0.001) if optimizer_name == 'adam' else optim.Adadelta(model.parameters())

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
        torch.save(model.state_dict(), 'D:\\work\\quant\\stock_data\\best_cnn_model_state.pth')
        print('模型状态已保存为 best_cnn_model_state.pth')

    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False)
    predictions = []
    with torch.no_grad():
        for inputs, _ in test_loader:
            inputs = inputs.to(device)  # 确保数据在 GPU 上
            outputs = model(inputs)
            predictions.append(outputs.cpu().numpy())
    predictions = np.concatenate(predictions)

    prediction_copies_array = np.repeat(predictions, 7, axis=-1)
    pred = scaler.inverse_transform(np.reshape(prediction_copies_array, (len(predictions), 7)))[:, 0]

    original_copies_array = np.repeat(test_Y.cpu().numpy(), 7, axis=-1)
    original = scaler.inverse_transform(np.reshape(original_copies_array, (len(test_Y), 7)))[:, 0]

    
    plt.plot(original, color='red', label='真实股价')
    plt.plot(pred, color='blue', label='预测股价')
    plt.title('预测股价')
    plt.xlabel('时间')
    plt.ylabel('股票价格')
    plt.legend()
    plt.show()