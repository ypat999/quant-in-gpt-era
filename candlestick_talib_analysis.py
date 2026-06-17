import pandas as pd
import talib
from candlestick import candlestick

# 示例数据
data = {
    'date': ['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05'],
    'open': [100, 102, 101, 103, 104],
    'high': [105, 106, 104, 107, 108],
    'low': [99, 100, 98, 102, 103],
    'close': [104, 101, 99, 106, 107],
    'volume': [1000, 1200, 1100, 1500, 1300]
}

# 转换为DataFrame
df = pd.DataFrame(data)

# 使用candlestick-patterns库识别锤头线形态
df['Hammer'] = candlestick.hammer(df)

# 使用talib计算技术指标（例如，简单移动平均线）
df['SMA_5'] = talib.SMA(df['close'], timeperiod=5)

# 打印结果
print(df)