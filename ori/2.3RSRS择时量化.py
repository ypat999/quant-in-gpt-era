# RSRS 择时量化交易策略代码实现
# 导入函数库
import statsmodels.api as sm
from jqlib.technical analysisimport*
def initialize(context):
#设定上证指数作为基准
set benchmark(000300.XSHG')
#开启动态复权模式(真实价格)
set option('use real price',True)
#输出内容到日志 log.info()
1og.info('初始函数开始运行且全局只运行一次')
#每笔股票类交易的手续费是:买入时佣金的万分之三，卖出时佣金的万分之三加千分之一印花税，每笔交易佣金最低扣5元
set order cost(OrderCost(close tax=0.001,open commission=0.0003close commission=0.0003,min commission=5)type='stock')
# 开盘前运行
run daily(before market opentime='before open'reference security='000300.XSHG')
# 开盘时运行
run daily(market open,time='open'reference security='000300.XSHG')

#收盘后运行
run daily(after market close,time='after close'reference security='000300.XSHG')
# 设置 RSRS 指标中 N，M的值
g.N=18
g.M=300
g.init = True
g.security=000300.XSHG'
# 絹鳘疗澜最蹯卧靬簋囡ц諼稹臌膜疟臉鋇饜饌郗誹邝影沌Ⅷるⓚ器恙
g.buy =0.7
g.sell=-0.7
g.ans =[]
g.ans rightdev=[]
# 计算2005年1月5 日至回测开始日期的 RSRS 斜率指标
prices =get price(g.security,'2005-01-05',context.previous date"1d'['high',low']).dropna()hiqhs =prices.high
lows =prices.low
g.ans =[]
for i in range(len(highs))[g.N:]:
data high = highs.iloc[i-g.N+1:i+1]data low=lows.iloc[i-g.N+1:i+1]
X=sm.add constant(data low)
model=sm.0LS(data high,X)
results = model.fit()
g.ans.append(results.params.low#计算r2
g.ans rightdev.append(results.rsquared)
##开盘前运行函数
def before market open(context):
# 输出运行时间
log.info('函数运行时间(before market open):'+str(context.current dt.time()))
#给微信发送消息(添加模拟交易，并绑定微信生效)send message('美好的一天')
## 开盘时运行函数

def market open(context):log.info('函数运行时间(market open):'+str(context.current dt.time()))security=g.security
#取得当前的现金
cash =context.portfolio.available cash
#填入各个日期的 RSRS 斜率值
security=g.security
beta=0
r2=0
if g.init:
g.init =False
else:
#RSRS 斜率指标定义
prices =attribute history(security,g.N,'ld',['high''1ow']，fq=None)#指数无复权，个股应该使用前复权
highs =prices.high
lows =prices.low
X=sm.add constant(lows)
model=sm.0LS(highs，X)
beta = model.fit().params.low
g.ans.append(beta)
#计算 r2
r2=model.fit().rsquared
q.ans rightdev.append(r2)
# 计算标准化的 RSRS 指标
# 计算均值序列
section=g.ans[-g.M:]
#计算均值序列
mu =np.mean(section)
# 计算标准化 RSRS 指标序列
sigma =np.std(section)
zscore =(section[-1]-mu)/siqma
#计算右偏 RSRS 标准分
zscore rightdev=zscore*beta*r2
if zscore rightdev>g.buy :
#if zscore riqhtdev>g.buy and ma5lg.security]>ma20lg.security]:#记录这次买入
log.info("标准化 RSRS 斜率大于买入阈值，买入s"号(security))#用所有 cash 买入股票
order value(security,cash)#若上一时间点的 RSRS 斜率小于卖出阈值，则空仓卖出
elif zscore rightdev<g.sell and
context.portfolio.positions[security].closeable amount>0:
#elif zscore rightdev< g.sell and ma5[g.security]<ma20[g.security]

and context.portfolio.positionssecurity].closeable amount >0:# 记录这次卖出log.info("标准化RSRS 斜率小于卖出阈值，卖出s"号(security))#卖出所有股票，使这只股票的最终持有量为 0
order target(security，0)
##收盘后运行函数def after market close(context):log.info(str('所数运行时间(after market close):'+str(context.current dt.time())))#得到当天所有成交记录
trades =get trades()
trade in trades.values():forlog.info('成交记录:'+str(trade))