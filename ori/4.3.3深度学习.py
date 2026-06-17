from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.wrappers.scikit_learn import KerasRegressor
from sklearn.model_selection import GridSearchCV
import matplotlib.pyplot as plt

# 已经获取的历史行情数据
prices = pd.read_csv(r"file_name.csv")[['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol']]

# 划分数据集
test_split = round(len(prices) * 0.1)
df_for_training = prices[:-test_split][features]
print(df_for_training.shape)

df_for_training = df_for_training.dropna(how='any')
print(df_for_training.shape)

df_for_testing = prices[-test_split:][features]
print(df_for_testing.shape)

# 对训练、测试数据进行缩放
scaler = MinMaxScaler(feature_range=(0, 1))
# 缩放数据
df_for_training_scaled = scaler.fit_transform(df_for_training)
df_for_testing_scaled = scaler.transform(df_for_testing)

# 标签提取
def input_func(data, past_days):
    """
    创建模型训练时的输入数据，划分特征x和Y值
    :param data: 预测股票的历史行情数据
    :param past_days: 设置用于预测的数据天数
    :return: 模型输入的特征及Y值
    """
    x_li = []
    y_li = []
    for i in range(past_days, len(data)):
        x_li.append(data[i-past_days:i,:])
        y_li.append(data[i,-2])
    return np.array(x_li), np.array(y_li)

# 生成测试数据
train_X, train_Y = input_func(df_for_training_scaled, 30)
test_X, test_Y = input_func(df_for_testing_scaled, 30)

# 模型搭建
def build_model(optimizer):
    grid_model = Sequential()
    grid_model.add(LSTM(50, return_sequences=True, input_shape=(30, 5)))
    grid_model.add(LSTM(50))
    grid_model.add(Dropout(0.2))
    grid_model.add(Dense(1))
    grid_model.compile(loss='mse', optimizer=optimizer)
    return grid_model

grid_model = KerasRegressor(build_fn=build_model, verbose=1, validation_data=(test_X, test_Y))
parameters = {'batch_size': [16, 20], 'epochs': [8, 10, 12], 'optimizer': ['adam', 'Adadelta']}
grid_search = GridSearchCV(estimator=grid_model, param_grid=parameters, cv=2)
grid_search = grid_search.fit(train_X, train_Y)
print(grid_search.best_params)
best_model = grid_search.best_estimator_.model
prediction = best_model.predict(test_X)

# 对预测结果逆缩放后绘图
plt.plot(original, color='red', label='真实股价')
plt.plot(pred, color='blue', label='预测股价')
plt.title('预测股价')
plt.xlabel('时间')
plt.ylabel('股票价格')
plt.legend()
plt.show()