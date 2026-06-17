#导入函数库
from jqdataimport*
import copy
import numpy as np
#初始化函数，设定基准，等等
# 更新基金池的日期
CHANGE STOCKPOOLDAYUMBER60
# 检查收益的间隔天数
CHECK FUNDS RETURNS=10
def initialize(context):
#设定沪深 300指数作为基准
set benchmark(000300.XSHG')
#开启动态复权模式(真实价格)
set option('use realprice'True)
#输出内容到日志 1og.info()
1og.info('初始函数开始运行且全局只运行一次')
# 过滤掉 order 系列 API 产生的比 error 级别低的 log
log.set level('order'"error')
#设置手续费是:买入时佣金的万分之一，卖出时佣金的万分之一,无印花税，每笔交易佣金最低扣 0 块钱
set order cost(OrderCost(open commission=0.0001,close commission=0.0001 close tax=0,min commission=0),type='fund')#设置滑点
set slippage(FixedSlippage(0.01))
g.funds pool={}
g.stock pool={}
# 基金池更新的天数
g.update funds days=0
g.refresh rate=20 #每10 天执行一次技术面策略，todo
g.days=0
g.rates={1:0 14 2:0 13 3:0.12 4:0.11 5:0.1 6:0.1 7:0.09 8:0.08 9:0.0710:0.06}
# 开盘时运行
run daily(market open,time='9:30')
run daily(update funds pool,time='after close',reference security='000300.XSHG')
##开盘时运行函数
def market open(context):
check returns(context)
sell not in funds pool(context)
buy FoF(context)
pas s
def check returns(context):
11!
每隔 30 天检查一次收益，如果大于30号,卖出
如果跌幅大于 10号，卖出。
1!!
if g.update funds days CHECK FUNDS RETURNS==0:for code in context.portfolio.positions.keys():current data=qet current data()[code]cost=context.portfolio.positionslcodel.acc avg cost#跌幅大于10号
current price=current data.lastprice
# if(current price<cost*0.90):井order target(code,0)del g.funds pool[code]if(current price>cost*1.20):order target(code,0)del g.funds pool[code]
pass
# 找到所有的基金
def findFund(start day,today):
df=get all securities(['lof''etf'])
# df=get all securities(['stock fund'])codelist=df[df['end date']>today.date()].index.tolist()
stock list f1=[]
for t in codelist:
t info=get security info(t)
start dt=t info.start dateif start dt>start day:
continuestock list fl.append(t)
return stock list fl#计算 IR
def cal info rate(start day,end day,code):
11T
计算信息比率
!!!
df=get price(code,start day,end day,frequency='ld'fields=['close']fq='post')
df hs300=
get price('000300.XSHG',start date=start day,end date=end day,frequency='ld',fields=['close'lfq='post')df hs300 returns=df hs300.pct change()
计算收益
并
fund return=df.pct change()df concat=pd.concat([fund return,df hs300 returns],axis=1)df concat.columns=['f''b']
计算超额收益
excess returns=df concat['f']df concat['b']avg excess returnexcess returns.mean()#跟踪误差/技术周期
trace err=np.sqrt(np.square(excess returns).sum()/(60-1))女
info rate=avg excessreturn/trace er
return info rate
def get FoF rank(context):
111
取得基金信息比率的排名
T1!
split=60
co鶉倖隳舫鐒泾絲杯抃鵑谧nt幀鐒浰甯簹猿拋蛱醍背545
#计算 IR 的周期
priod=(int(count/split))
1og.info(priod)
today=context.currentdt
tradingday=get trade days(start date=None,end date=today
count=count)
start=tradingday[0]
fundCodeList=findFund(start,today)
all fund df=pd.DataFrame (fundCodeList,columns=['code']index=fundCodeList)
for jin range(priod):k=j*60
array=tradingday[k:k+60]
st=array[0]
ed=array[59]
info rates=[]
for code in fundCodeList:
info rate=cal info rate(st,ed,code)info rates.append([code,info rate])infostr='info rate'+str(j)
#把当前时间段所有基金的 ir转化成一个 df，以便排名。df2=pd.DataFrame(info rates,columns=['code' infostr]index=fundCodeList)
#对 DF2 进行排名
rank series=df2[infostr].rank(ascending=False)#把rank series 转成df
rank df=pd.DataFrame(rank series)
#把每次的排名进行拼接，all fund df=pd.merge(all fund df,rank df,left index=Trueriqht index=True)
#对每个 fund 的排名，按行计算方差#
var df=pd.DataFrame(all fund df.var(axis=1))
var df=var df.sort values(by=0)
return var df[0:10]
def set FoF pool(context):
111
根据选择的基金，设置基金池
111
log.info("更新股票池日期:{}".format(context.current dt))fund df=get FoF rank(context)
# 清空基金池
g.funds pool={}
#将资金分为 10 份
j=1
for i row in fund df.iterrows():r=g.rates [j]
#设定每个的系数
g.funds pool[i]=r
j=j+1
pass
def update funds pool(context):I1!
每日收盘后要运行这个方法，进行基金池更新
11!
if g.update funds days号CHANGE STOCK POOL DAY NUMBER==0:set FoF pool(context)
g.update funds days=(g.update funds days+1)号CHANGE STOCK POOL DAYNUMBERpas s
def sell not in funds pool(context):11!
每天开仓时，卖掉不在基金池的股票
T
for code in context.portfolio.positions.keys():
if code not in g.funds pool.keys():
order = order target(security=code,amount=0)if order is not None and order .filled:log.info("交易卖出平仓",code,order .filled)
pas s
def buy FoF(context):
111
开仓买入，
!:!
log.info("当前账户总价值:{}".format(context.portfolio.total value))for code in g.funds pool.keys():
if code in context.portfolio.positions.keys():
c讎朧曩暖è郚钩开唇薀晩亞淀妺鴯硪愚娈啱嫰鉄瘐围碥渗嗓翠nue
rate=g.funds pool[code]m=rate*context.portfolio.total valuelog.info("买入基金{0}数量{1}".format(code,int(m)))order=order target value(code,int(m))
pass
米