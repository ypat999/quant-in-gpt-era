def handlebar(ContextInfo):
rankl ={}
rank2 ={}
rank total ={}
tmp stock={}
d = ContextInfo.barposprice =ContextInfo.get history data(l,'ld','open'if d>5and d号5 ==0:#每5 天一调仓nowDate =timetag to datetime(ContextInfo.get bar timetag(d),'号Y号m号d')print(调仓日:"nowDate)buys，sells=signal(ContextInfo)#计算调仓买，卖列表order ={}for k in sells:print('ready to sell')
order shares(k,-ContextInfo.holdings[k]*100
'fix',price[k][-1],ContextInfo,ContextInfo.accountID)ContextInfo.money +=price[k][-1]*ContextInfo.holdings[k]*100-0.0003*ContextInfo.holdings[k]*100*price[k][-1]#手续费按万三设定
ContextInfo.profit+=(price[k][-1]-ContextInfo.buypoint[k])ContextInfo.holdingskl*100-0.0003*ContextInfo.holdings[k]*100*price[k][-1]#print price[k][-1]print(k)#print ContextInfo.moneyContextInfo.holdings[k]=0
for k in buys:print('ready to buy')order[k]= int(ContextInfo.money distribution[k]/(price[k][-1]))/100
order shares(k,order[k]*100,'fix',price[k][-1]ContextInfo,ContextInfo.accountID)
ContextInfo.buypoint[k]= price[k][-1]ContextInfo.money-=price[k][-1]*order[k]*1000.0003*order[k]*100*price[k][-1]ContextInfo.profit -=0.0003*order[k]*100*price[k][-1]print(k)ContextInfo.holdingsk=orderklprint(ContextInfo.money,ContextInfo.profit,ContextInfo.capital)
profit = ContextInfo.profit/ContextInfo.capitalif not ContextInfo.do back test:ContextInfo.paint('profit ratio',profit，-1，0)
def signal(ContextInfo):
buy ={i:0 for i in ContextInfo.s}sell ={i:0 for i in ContextInfo.s}filter(ContextInfo)
sort candidate to buy(ContextInfo)candidate buy30 =ContextInfo.candidate buy[:30]for k in candidate buy30:hold =ContextInfo.holdings.get(k，0)if hold ==0:
buy[k]=1 #如果在待买列表，且没有持有，则买入for k,hold in ContextInfo.holdings.items():if not(k in candidate buy30):if hold ==1:
sell[k]=1#如果不在待买列表，且持有，则卖出return buy,sell#买入卖出备选
def filter(ContextInfo):
IT IT IT
筛选因子:
选取利润总额较大的股票，比如单季利润大于 1000万元
选取股票价格/每股自由现金流小于 10 的股票
选取资产负债率低的股票，比如低于 25号
选取市盈率/净利率同比增长率小于1的股票
I IT H
ContextInfo.candidate={}
# 选取利润总额较大的股票，比如单季利润大于1000万元
filter tot profit(ContextInfo)
#选取股票价格/每股自由现金流小于10的股票
filter price CashEquivalentPS(ContextInfo)
#选取资产负债率低的股票，比如低于25号
filter qear ratio(ContextInfo)
#选取市盈率/净利率同比增长率小于1的股票
filter PE net profit incl min int inc(ContextInfo)
def filter tot profit(ContextInfo):
index=ContextInfo.barposfor one in ContextInfo.s:market,code =one.split('.')v= ContextInfo.get financial data('ASHAREINCOME','tot profit'market,code,index);if v> 1000:#利润大干1000万元
ContextInfo,candidatelonel=ContextInfo.candidate.qet(one,1)
and 1
else:
ContextInfo.candidate[one]=0
def filter price CashEquivalentPS(ContextInfo):井颃
index= ContextInfo.barpos
nowDate =
timetag to datetime(ContextInfo.get bar timetag(ContextInfo.barpos),'名Y号m号d')
hisdict =ContextInfo.get history data(l,'1d','close')for stockcode inContextInfo.s:
if not(stockcode in hisdict):
continue
close=hisdict[stockcode][0]
井
fieldList='Per Share Analysis.CashEquivalentPs']
Cash=
ContextInfo.get factor data(fieldList ,stockcode,nowDate,nowDate)if(close /cash)<10: #选取股票价格/每股自由现金流小干 10 的股票ContextInfo.candidateone]=ContextInfo.candidate.qet(one,1)
and 1
else:ContextInfo.candidateone]=0def filter gear ratio(ContextInfo):index=ContextInfo.barposfor one in ContextInfo.s:market,code =one.split('.')v=ContextInfo.get financial data('PERSHAREINDEX','gear ratio'market,code,index);#选取资产负债率低的股票，比如低于25号if v< 0.25:ContextInfo,candidate[one]=ContextInfo.candidate.get(one,1)
and 1
else:
ContextInfo.candidatelone]=0
def filter PE net profit incl min int inc(ContextInfo):index=ContextInfo.barposfor stockcode inContextInfo.s:
fieldList='Valuation and Market Cap.PE']pe =ContextInfo.get factor data(fieldList,stockcode,nowDate,nowDate)market,code=one.split('.')
du profit rate= ContextInfo.get financial data('PERSHAREINDEX'du profit rate',market,code,index);
if(pe /du profit rate)< 1:
#选取市盈率/净利率同比增长率小于1的股票ContextInfo.candidatelone]=ContextInfo.candidate.get(one,1)
and 1
else:
ContextInfo.candidateone]=0
def sort candidate buy(ContextInfo):data =]for stockcode,flag in ContextInfo.candidate.items():if not flag:continuefieldList =['Operation.InventoryTRate']InventoryTRate=
ContextInfo.qet factor data(fieldList,stockcode,nowDate,nowDate)fieldList='Analyst Estimation.SFY12P'1
SFY12PContextInfo.get factor data(fieldList,stockcode,nowDate,nowDate)data.append({'code':stockcode，'存货周转率':InventoryTRate，，预期营收增长率':SFY12P})
df = pd.DataFrame(data)
df= df.sort values(by=['存货周转率'，'预期营收增长率’]，ascending=[True,Falsel)
ContextInfo.candidate buy=dfl'code'].tolist()
