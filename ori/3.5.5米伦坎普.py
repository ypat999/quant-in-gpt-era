#导入函数库
from jqdata import巜繪忌礪使
from jqlib.technical analysis import*
import numpyas np
import talib as tl
import math
# 初始化函数，设定基准
import datetime asdatetime
importpandas as pdATR WINDOW=20
# 更新股票池的间隔天数
CHANGE STOCK POOL DAYNUMBER15def initialize(context):
# 设定沪深 300 指数作为基准
set benchmark('000300.XSHG')
#开启动态复权模式(真实价格)
set option('use real price'True)#初始化全局变量
init global(context)
# 输出内容到日志 log.info()
log.info('初始函数开始运行且全局只运行一次')
#过滤掉 order 系列 API产生的比 error 级别低的 log
g.stockNum=10
#每笔股票类交易时的手续费是:买入时佣金的万分之三，卖出时佣金的万分之三加千分之印花税，每笔交易佣金最低扣5元
set order cost(OrderCost(close tax=0.001,open commission=0.0003close commission=0.0003,min commission=5)，type='stock')#开盘时运行
run daily(market open，time='9:30reference security=000300.XSHG')
#收盘后运行
run daily(update pool,time='after closereference security='000300.XSHG')def init global(context):
111
初始化全局变量
T11
g.stock pool=[]
g.stock pool update day=0
g.current date=context.currentdt##开盘时运行函数
def market open(context):
buy(context)
sell(context)
def buy(context):
11!
买入逻辑，开仓前买入
!
buy num=0
buy codes=[]
if(len(g.stock pool)>0):
for code in g.stock pool:if code in context.portfolio.positions.keys():continuecurrent data=qetcurrentdata()codeif current data==None:
returnbuy num=buy num+1print("buy num" buy num)buy codes.append(code)#每份的金额cost=context.portfolio.totalvalue/buy numfor code in buy codes:
order =order target(code,int(cost))log.info("买入{0}价值{1}".format(code,cost)
pas s
# m 讜蝸著鬟趙黄謬処敘蠖晨鄴嚇犠诮圏饈覽⑮轵卄Ⓔ牽诀缬走
def sell(context):
for code in context.portfolio.positions.keys():if code not in g.stock pool:order =order target(security=code,amount=0)if order is not None and order .filled:log.info("卖出:"code order .filled)
pass
#---------------------------------------策路开始
一一一一一一一一一一----
def update pool(context):
I1!
更新股票池
I!!
if g.stock pool update dayCHANGE STOCK POOL DAY NUMBER==0:set stock pool(context)
g.stock pool update day=(g.stock pool update day+1)号CHANGE STOCK POOL DAYUBER
pas s
def set stock pool(context):
I坣踬尻箇饯伩诜仍铧才疝锸倉诧撟埂
设置股票池
1!!
df=get industries("jq ll")
indust codes=df.index.tolist()
filter pools=[]
for ins in indust codes:
codelist=get industry stocks(ins,date=None)print("该行业代码:"，len(codelist))井
roeList,roe rank df=get cur roe(codelist)roe5List=get 5y roe(roeList)
peCodeList=get pe codeList(roe5List)
epsList=get eps codeList(peCodeList)
filter pools.extend(epsList)
crRankDF=get currentRatio rank(filter pools)
print("cr ratio df :",crRankDr.shape)
# 要和 ROE 的排名进行合并。获得一个流动比率 df 代码对应的 ROE
g=query(indicator.code,indicator.roe)filter(indicator.code.in(filter pools))
filter roe df=get fundamentals(q)
filter roe df'rank']=filter roe df.roe.rank(method"first",ascending=False,na option='bottom')
rank df=pd.merge(crRankDF,filter roe df,on='code',how='left')rank df['rank sum']=rank df['cr rank']+rank df['rank']rank df=rank df.sort values (by='rank sum',ascending=False)print(rank df.shape)
print(rank df[['code','cr rank','rank','rank sum']])g.stock pool=[1
g.stock pool=rank df['code'].tolist()
pas s#函数
def create code set(list):
set2=set(list)
return set2
#需要返回一个排序后的 code list,以及 ROE 的排名
def get cur roe(codeList):
q=query(indicator.codeindicator.roe).filter(indicator.code.in (codeList)).order by(indicator.roe.desc())
df=get fundamentals(q)
n=df.shape[0]roe num=int(n*0.5)df roe=df[0:roe num]list=df roel'code'].tolist()井print (type(list))df roe['rank']=df roe.roe.rank(method="first",ascending=False,na option='bottom')
return list df roe
# 取得 5年的 ROE
def get 5y roe(codeList):q=query(indicator.code indicator.roe).filter(indicator.code.in(codeList)).order by(indicator.roe.desc())df=qet fundamentals(q)
n=df.shape[0]
roe num=int(n*0.5)
df roe=df「0:roe numl
先做个空的 df，用来合并计算5年的 ROE
roe5 df=pd.DataFrame(codeList,index=codeList,columns=['code'])month=g.current date.monthday=g.current date.dayfor i in range(5):y5=q.current date.year-(i+1)
并
statDate=str(y5)+"-"+str(month)+"-"+str(day)per roe df=get fundamentals(q,date=statDate)per roe df.columns=['code''roe'+str(i)]print(df2)
roe5 df=pd.merge(roe5 df,per roe df,left on=
"code" left index=True,
right on="code")
# 把行索引用股票代码替换
df3=roe5 df.set index("code")
d3=df3.iloc[:1:].mean(axis=1)
d3=d3.sort values(ascending=False)
d3 num=int(d3.shape[0]*0.5)
d4=d3[0:d3 num，]
roelist=d4.index.tolist()
return roelist# 计算pe,过滤:pe>0,pb ratio<2，pcf ratio >0def get pe codeList(codeList):
pe q=query(valuation.code,valuation.pe ratio).filter(valuation.pe ratio>0,valuation.pb ratio<2,valuation.pcf ratio>0valuation.code.in(codeList)).order by(valuation.pe ratio.asc())df pe=get fundamentals(pe q)sp=df pe.shape[0]n=math.ceil(sp*0.5)df pe2=df pe[0:n]pelist=df pe2['code'].tolist()return pelist# 筛选 eps
def get eps codeList(codeList):
q eps=query(indicator.code indicator.eps).filter(indicator.eps>0,indicator.code.in(codeList))eps init df=pd,DataFrame(codeList,index=codeList,columns=['code'])month=g.current date.month
day=g.current date.day
for jin range(4):
y4=g.current date.year-(j+1)statDate=str(y4)+"-"+str(month)+"-"+str(day)df eps=get fundamentals(g eps date=statDate)df eps.columns=['code','eps'+str(j)]
eps init df=pd.merge(eps init df,df eps,left on="code"right on="code")
eps2=eps init df.set index('code')
eps mean=eps2.mean(axis=1)
eps sort=eps mean.sort values(ascending=False)
n=int(eps sort.shape[0]*0.5)
eps sort=eps sort[0:n]
codeList=eps sort.index.tolist()
return codelist
# 取得流动比率的排名
def get currentRatio rank(codeList):
#计算流动比率,流动比率=流动资产/流动负债
cr query=query(balance.code ,balance.total current assets,balance.total current liability),filter(balance.code.in(codeList))cr df=get fundamentals(cr query)
cr df['cr ratio']=cr df['total current assets']/cr df['total current liability']
cr sort=cr df.sort values(by='cr ratio'ascending=False)cr sort2=cr sortIcr sort['cr ratio'1>2]cr sort2'cr rank']=cr sort2.cr ratio.rank(ascending=False)return cr sort2
共---策略结束