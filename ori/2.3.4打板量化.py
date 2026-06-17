##连板打板量化交易策略代码实现
##开盘前运行函数
def before market open(context):
# 输出运行时间
log.info('承数运行时间(before marketopen):+str(context.current dt.time()))
#更新一下股票池
stock pool(context)
#更新账户股票的 atrfor code in context.portfolio.positions.keys():position= context.portfolio,positionscode]high price=get price(code,start date=position.init time,end date=context.current dt,frequency="1m",fields=['high'],skip paused=True,fq="pre",count=None)['high'].max()
if code not in g.cache data.keys():
g.cache data[code]=dict()g.cache datalcode]['high price']= high price
atr = calc history atr(code=code,end time=get last time(position.init time),timeperiod=ATR WINDOW,unit=LONG UNIT)if code not in g.cache data.keys():
g.cache datalcode]= dict()g.cache datalcode]['atr']= atr
##开盘时运行函数
def market open(context):
buy(context)
sell(context)
##收盘后运行函数
def after market close(context):1og.info(str('函数运行时间
(after market close):'+str(context.current dt.time())))#得到当天所有成交记录trades =get trades()log.info("收盘时的账户记录:",str(context.portfolio.positions))for trade in trades.values():
log.info('成交记录:'+str(trade))
#if g.stock pool update day号CHANGE STOCK POOL DAY NUMBER ==0:# 更新股票池stock pools =set()log.info('-天结束')
1〇g.in£O('#并井并并井并并并并井并并井并并并井井井并井井并井并井并并井井井井并井并并井井井井井井井并井井井井并井井并井井井井井井井井井·)
def load fundamentals data(context):
I11
加载财务数据,选出市值大于 10 亿元到 350 亿元的个股
11!
# names=get all securities(types=['stock'],date=None)df=get fundamentals(query(valuation).filter(valuation.marketcap>10).filter(valuation.market cap<350))
return df['code'].tolist()
def buy(context):
I11
买入逻Ấ概般睐傢宫，开仓前买入
!1I
for code in g.stock pool:
if code in context.portfolio.positions.keys():
continue
current data=get current data()[code]ifcurrent data==None:
return
if is high limit(code):
continue
position amount=calc position(context code)log.info("计算出来的仓位量:"position amount)num=g.stockNum-len(context.portfolio.positions)
if(num>0):
order =order target(security=code,amount=position amount)log.info("成交记录2022:"str(order))
1og.info("当前的账户记录:",str(context.portfolio.positions))
if((order is not None)and(order .filled>0)):log.info("成交了吗?")
1og.info("交易 买入",code,"成交均价",order .price,"买入的股数"
order .filled)
atr = calc history atr(code=code,end time=get last time(context.current dt),timeperiod=ATR WINDOW,Unit=LONG UNIT)
if code not in g.cache data.keys():g.cache datalcodel=dict()g.cache data[code]['atr']= atrg.cache data[code]['high price']=current data.last price
g.bar number=g.bar number+1
g.stock pool=[]pass
def is high limit(code):
current data=get current data()[code]if current data.last price>=current data.high limit:return Trueif current data.paused:return Truereturn False
def is low limit(code):
current data=get current data()[code]
current data.last price<=current data.low limit:i f
return True
if current data.paused:
return True
return False
# m 卖票策略
def sell(context):
sell list=list(context.portfolio.positions.keys())if(len(sell list)>0):
for stock in sell list:close datal=get bars(stock,count=l,unit='lm'fields=['close'])[0]['close']
cost=context.portfolio.positions[stock】.acc avg costclose data=attribute history(stock,5,'ld'['close'])current price=get price(stock,start date=None,end date=context.current dt,frequency='1m'fields=['close']skip paused=True,count=1).iloc[0]['close']pre close=close data['close'][-1]if(current price<cost*0.90):order target(stock,0)log.info("亏本卖出:号s"号(stock))elif current price>=cost*1.20:if (is high limit(stock)):
continue
order target(stock,0)
log.info("赚钱卖出:号s"号(stock))
pass
def stop loss(context):
111
跟踪止损
111
for code in context.portfolio.positions.keys():position =context.portfolio.positions[code]if position.closeableamount<=0:
Continue
if is low limit(code):
Continue
current data=get current data()[code]if current data ==one:
continue
current price =current data.last price
#获取持仓期间最高价
start date= context.current dt.strftime("名Y-号m-号d")+ " 00:00:00"
# 为防止发生 start date 遭遇建仓时间，这里需要进行判断
# 当前时间和建仓时间在同一天时，startdate设置为建仓时间
if context.current dt.strftime("Y-号m-号d")<=position.init time.strftime("号Y-号m-号d"):
start date=position.init time
high price =get price(security=code,start date=start date,end date=context.current dt,frequency='1m',fields=「'high'1,skip paused=True,fq='pre',count=None)['hiqh'].max()#每日9:30时，getprice获取00:00到09:30之间的最高价时，数据返回的为NaN，需要特殊处理。这里采用当前价格和缓存的最高价进行比较
if not np.isnan(high price):
high price = max(high price,g.cache data[code]['high price'])else:
high price =max(current price,g.cache datalcode]['high price'])g.cache datalcode]['high price']= high priceatr =g.cache datalcodel'atr']avg cost=position.avg cost
卖梗出垱戎戦
if current price<= high price-atr *TRAILING STOP LOSS ATR:#当前价格小于等于最高价回撤TRAILING STOP LOSS ATR倍ATR，进行止损
=order target(security=code，amount=0)orderif order is not None and order .filled>0:flag ="WIN*"if current price >avg cost else "FAIL"log.info("交易 卖出 跟踪止损"
code,"卖出数量"order .filled,
"当前价格"current price,
"持仓成本"avg cost,
"最高价"high price,
"ATR"(atr*TRAILING STOP LOSS ATR)"价差"(high price -current price)
pas s
def stock pool(context):current dt=context.current dt.strftime("号Y-号m-号d")codeList=load fundamentals data(context)
current datas=qetcurrentdata()log.info("----股票池更新------")
i=0
for code in codeList:
codeStart=code[0:3]
current data=current datas[code]
I1
交易日期
11!
trade days=get trade days("2014-01-01",current dt)yesterDay=trade days[-2]
if current data.is st:
continueif current data.paused:
continue
name= current data.nameif'ST'in name or*'inname or退'in name:
continue
if(codeStart=="300"or codeStart=="301" or codeStart =="688"):continue
# if(capFilter(code)is False):
并
continue
# log.info("昨日换手率:号s"号zrtr)
if not(tr(code,context)):
continue
11
进行各种选股条件的判断
11!
price=get price(code,count=30,end date=current dt panelFalse,fields=['close','open','high','low','volume','paused'])
111
XG:(进2强势OR每日强势)AND超预期AND清洗AND高开;
!1!
if((j2qs(price)or mrqs(price))and cyq(price,code,current dt)and gaokai(price)):# if(qs(price)):
log.info("日期",current dt,"选出股:",code)g.stock pool.append(code)
if(len(g.stock pool)==0):log.info("没有选到股票")
else:
log.info("选出股票个数:"len(g.stock pool))
pas s
def tr(code,context):current dt=context.current dt.strftime("号Y-号m-号d")tr=get valuation(code,fields=["turnover ratio" ]end date=current dtcount=4)
# print(tr)
#昨日换手率
if(len(tr)>2):
zrtr=tr.iloc[-2]['turnover ratio']# print(zrtr)
if((not zrtr is None)and zrtr>3):
return True
else:
return False
else:
return False
def gaokai(priceList):currOpen=priceList.iloc[-1,1]preClose=priceList.iloc[-2，0]if(currOpen>=preClose*1.002 and currOpen<preClose *1.092):return Trueelse:
return False
#定义黄金线
def hjx(code,current dt,price):
df2=price.iloc[-32:-2]
gl=df2['high'].mean()
return gl*(1+13/100)#定义超预期#超预期:=REF(C,1)>黄金线*1.03;
def cyq(priceList,name,current dt):
gl=hjx(name,current dtpriceList)
if(priceList.iloc[-2,0]>gl*1.03):
return True
else:
return False
#只要中小市值的股票
def capFilter(code):
g = query(
valuation.code,
valuation.market cap
).filter(valuation.code==code)
df =get fundamentals(g)
cap=df.iloc[0]['market cap']
if(cap>10 and cap<35):
return True
else:
return False
def aal(price,i):
b=False
c=price.iloc[i,0]#收盘
h=price.iloc[i 2]#high
r=price.iloc[i,0]/price.iloc[i-1 0]# 瀵镫耐滑停返回 True
if(r>1.094 and c==h):
return True
else:
return False
def vv(price,dp,i):
b=False
s=price.iloc[dp,4]/price.iloc[dp-i,4]
if(s>1.2):
# log.info(i ":"s)
return True
else:
return False
#定义前日未涨停
def qrwzt(priceList):
if aal(priceList,-3):
return True
else:
return False
#定义进二强势
def j2qs(price):
zrzt=aal(price,-2)
zrln=(vv(price,-2,1)or vv(price,-2，2))
if(qrwzt(price)is False and rztand rn):
return True
else:
return False
#定义每日强势
def mrgs(price):
qrzt=aal(price,-3)
zrzt=aa1(price,-2)
zrln=(vv(price,-21)or vv(price,-2,2))if(qrzt and zrzt and zrln):
return Trueelse:
return False
----卖出所需要的工具函数---#一一一def calc history atr(code,end time,timeperiod=14,unit='1d'):I1!
计算标的的 ATR 值
Args :
code 标的的编码
end time 计算 ATR 的时间点
timeperiod 计算 ATR 的窗
unit 计算ATR的bar的单位
Returns :
计算的标的在 end time 的ATR 值
11!
security data = get price(security=code, end date=end time,frequency=unit,fields=['close','high','low'],skip paused=Truefq='pre',count=timeperiod+1)
nan count=list(np.isnan(security data['close'])).count(True)if nan count == len(security datal'close']):
1oq.info("股票 号s 输入数据全是 NaN，该股票可能已退市或刚上市，返回 NaN 值数据。"号stock)
return np.nan
else:
return tl.ATR(np.array(security data['high'])np.array(security data['low']),np.array(security data['close'])timeperiod)[-1]
pass
def calc position(context,code):
11!
计算建仓头寸依据:资金池每份现金*风险因子/波动率Args :
context上下文
code 要计算的标的的代码
Returns :
计算得到的头寸，单位为股数
11!
#计算 risk adjust factor 用到的 sigma的窗囗大小
RISK WINDOW=60
#计算 risk adjust factor 用到的两个 sigma 间隔大小
RISK DIFF=30
#计算 sigma 的窗口大小
SIGMA WINDOW60
# 计算头寸需要用到的数据的数量
COunt=RISKWINDOW+RISKDIE*2
count = max(SIGMA WINDOW,count)
history values =get price(security=code
end date=get last time(context.current dt),frequenCy=LONG UNITfields=['close','high','low'],skip paused=True, fq='pre', count=count)
h array=history values['high']
l array = history values['low']
c array=historyvalues'close'1
log.info("当前现金:",context.portfolio.starting cash)
if(len(history values.index)<count)or(list(np.isnan(h array)).count(True)>0)or(list(np.isnan(l array)).count(True)>0)or(list(np.isnan(c array)).count(True)>0):# 数据不足或者数据错误存在 NaN
return 0
# 数据转换
value array=[]
for i in range(len(h array)):
value array.append((h array[i]+l array[i]+c array[i]*2)/4)
first sigma=np.std(value array[-RISK WINDOW-(RISK DIFF*2):-(RISK DIFF*2)])#
-120:-60center siqma=np.std(value array[-RISK WINDOW-(RISK DIF*1):-(RISK DIFF*1)])-90:-30
last sigma= np.std(value array[-RISK WINDOW
井-60:
:])
=np.std(value array[-SIGMA WINDOW:])s iqmarisk adjust factor= 0
if last siqma>center sigma :risk adjust factor=0.5elif last sigma < center siqma and last sigma > first siqma:risk adjust factor =1.0elif last sigma<center sigma and last sigma< first sigma:risk adjust factor=1.5
return int(context.portfolio.starting cash*0.055 *risk adjust factor /((POSITION SIGMA*sigma)*100))*100