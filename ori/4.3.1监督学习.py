#查询个股在2022年7月1日至2022年9月1日的行情数据

#从 tushare 接口提取一些示例数据
import tushare as ts
import pandas as pd

# 设置token
ts.set_token('查取的token值')
api = ts.pro_api()

# 获取股票数据
prices = api.daily(
    ts_code='000001.SZ,600000.SH',
    start_date='20220701',
    end_date='20220901'
)[['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol']]

# 按日期排序
prices = prices.sort_values(by='trade_date', ascending=True).reset_index(drop=True)

# 对成交量进行对数变换
import numpy as np
prices['vol_log'] = prices['vol'].apply(np.log)

# 对close价格进行标准化
zscore_scaling = lambda x: (
    (x - x.rolling(window=100, min_periods=40).mean()) / 
    x.rolling(window=100, min_periods=40).std()
)
prices['z_close'] = prices.groupby('ts_code')['close'].apply(zscore_scaling)

# 添加TA库所有特征
import ta
ta_exmdata = prices.loc[prices['ts_code'] == "600000.SH"].copy()
ta_exmdata = ta.add_all_ta_features(
    ta_exmdata,
    "open", "high", "low", "close", "vol",
    fillna=False
)

# 提取月份信息并进行独热编码
prices['date_mon'] = pd.to_datetime(prices.trade_date).dt.month
one_hot_frame = pd.DataFrame(pd.get_dummies(prices['date_mon']))
month_names = ['mon_' + str(num) for num in one_hot_frame.columns]
one_hot_frame.columns = month_names

# 合并数据
prices = pd.concat([prices, one_hot_frame], axis=1)

# 添加 TA 库所有特征示例
import ta
ta_exmdata =prices.loc[prices["ts_code"]== "600000.SH"].copy()
ta_exmdata=ta.add_all_ta_features(ta_exmdata, "open","high","low","close","vol",fillna=False)

import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score
import matplotlib.pyplot as plt
import seaborn as sns

# 直接读取获取的行情数据
stock_data = pd.read_csv(r"filename.csv")

# 计算每只股票的每日收益值
stock_data[['open', 'high', 'low', 'close', 'vol']] = stock_data[['open', 'high', 'low', 'close', 'vol']].astype(float)
stock_data['trade_date'] = pd.to_datetime(stock_data.trade_date)
stock_data = stock_data.sort_values(by=['trade_date'], ascending=True).reset_index(drop=True)

target_lambda1 = lambda x: x.shift(-1)
target_lambda2 = lambda x: x.shift(-2)

stock_data['close_1'] = stock_data.groupby('ts_code').close.apply(target_lambda1)
stock_data['close_2'] = stock_data.groupby('ts_code').close.apply(target_lambda2)
stock_data['target'] = stock_data.apply(lambda x: (x['close_2'] - x['close_1'])/x['close_1'], axis=1)
stock_data.target = stock_data.target.fillna(0)

pivot_stock_data = stock_data.pivot(index='trade_date', values='target', columns='ts_code')
pivot_stock_data = pivot_stock_data.ffill().fillna(0)  # 存在2017年还没有开放证券的公司，填充空值为零

def generate_fe(data, pl, time_horizon, test_horizon, up=200):
    """
    生成模型的输入数据，取前10条数据的收益值作为特征，后10条数据的累计收益作为是否为上涨股的评判依据。
    取前200只股票标记为"上涨股"，作为此次训练的标签。
    
    Args:
        data: 每只股票每天的收益值
        pl: 交易日期
        time_horizon: 特征数据时间长度
        test_horizon: 累计收益时间长度
        up: 划定"上涨股"的数量
    Returns:
        特征、标签及当前数据切片的最后一个交易日
    """
    train_df = data.loc[:pl].iloc[-time_horizon-1:-1]
    test_df = data.loc[pl:].iloc[:test_horizon]
    cum_val = test_df.cumsum()
    sort_li = cum_val.iloc[-1].sort_values()
    up_index = sort_li.iloc[-up:].index
    y = [1 if ii in up_index else 0 for ii in test_df.T.index]
    X = train_df.T
    last_date = test_df.index[-1]
    return X, y, last_date

while True:
    X1, y1, p1 = generate_fe(pivot_stock_data, p1, time_horizon, test_horizon, up)
    pl = p1 + pd.offsets.Day(1)
    if pl > start_test:
        break
    Xtrain.append(X1)
    ytrain.append(y1)

# 模型训练
Xtrain = np.vstack([X1])
ytrain = np.hstack([y1])
model = LGBMClassifier(num_leaves=25, n_estimators=100)
model.fit(Xtrain, ytrain)

# 查看模型训练情况
print(f'训练数据上的 auc 值: {round(roc_auc_score(ytrain, model.predict_proba(Xtrain)[:, 1]), 3)}')



predict = []
while True:
    X = pivot_stock_data.loc[:start_test].iloc[-time_horizon-1:-1].T
    future_variation = pivot_stock_data.loc[start_test:].iloc[:test_horizon]
    
    # 预测
    pro = pd.Series(model.predict_proba(X)[:, 1], index=X.index)  # 修改：使用X而不是X1
    
    # 计算优质股票的预估收益
    goods = future_variation.loc[:, pro.sort_values().index[-200:]]
    goods = goods * pd.Series(np.arange(200)/199+1, index=goods.columns)
    predict.append((goods.sum(axis=1))/200)
    
    start_test = future_variation.index[-1] + pd.offsets.Day(1)
    if start_test > pd.to_datetime(end_test):  # 注意：需要事先定义end_test
        break

# 绘图
plt.figure(figsize=(10, 5))
plt.plot(pivot_stock_data.index, pivot_stock_data.cumsum(), color='b', label='基线收益')
plt.plot(predict.index, predict.cumsum(), color='q', label='预测股票累计收益')
plt.legend(loc='upper left')
plt.xlabel('时间')
plt.ylabel('收益')
plt.show()




