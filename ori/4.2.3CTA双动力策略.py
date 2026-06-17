#coding:gbk
IT VY VV IV
CTA 双动力策略:
HH:N天最高价的最高价，LC:N天收盘价的最低价
HC:N天收盘价的最高价，LL:N天最低价的最低价
Range:取HHLC与HC-LL的最大值
上轨BL:open+Kl*Range
做多:
进场:hight>上轨
出场:low<下轨
做空:
进场:low<下轨
出场:hight>上轨
IT IT WV T
import pandas as pd
import numpyasnp
importtime
import datetime
def init(ContextInfo):
ContextInfo.tradestock=601398.SH'
ContextInfo.set universe([ContextInfo.tradestock])
ContextInfo.K1=0.4
ContextInfo.K2=0.6
ContextInfo.N=5#N天内进行判断
ContextInfo.buy=0
ContextInfo.holdings=l
ContextInfo.profit=0
ContextInfo.accountID='testS
def handlebar(ContextInfo):
d =ContextInfo.barpos
井
#不够 N天则不计算if d< ContextInfo.N:
鱅嵬龊瞋嬙谬謳櫨畦萸氡宪慧蜃闞泽沧ě幄ю霪胆髈端獷b硌n
并
# 计算调仓买、卖列表buys，sells，BL，SL=signal(ContextInfo)
#根据买、卖列表进行交易
trade(ContextInfo,buys，sells，BLSL)
def signal(ContextInfo):
buy ={}
sell={}
井
H=ContextInfo.get history data(ContextInfo.N,'ld'
high')[ContextInfo.tradestock]
C=ContextInfo.get history data(ContextInfo.N,'ld''close')[ContextInfo.tradestockl
L=ContextInfo.get history data(ContextInfo.N,'ld''low')[ContextInfo.tradestockl
open =ContextInfo.get history data(l,'ld'open')[ContextInfo.tradestockl[0]
print('H'H)print('C'，C)print('')
print('open'open)
井
HH = max(H)
LC = min(C)
HC = max(C)
LL = min(L)
#Range:取值
Ra = max(HH-LC，HC-LL)
# 上轨
BL =open +ContextInfo.Kl*Ra
# 下轨
SL =open +ContextInfo.K2 *Ra
将
k= ContextInfo.tradestock
# 只做多
#进场:hight>上轨
if H[-1]> BL:# buy signalhold =ContextInfo.holdings.get(k，0)if hold == 0:buy[k]= 1#出场:low<下轨if L[-1]< SL:# sell signalfor k,hold in ContextInfo.holdings.items():if hold == 1:sell[k]=1
#print buy
#print sell
return buy,sell，BL,SL
#买入卖出备选
def trade(ContextInfo,buys,sells,BL,SL):order ={}井
for k in sells:
print('ready to sell'k)order shares(k,-ContextInfo.holdings[k]*100，'fix'，SLContextInfo,ContextInfo.accountID)ContextInfo.holdings[k]=0
办
for k in buys:
print('ready to buy',k)order shares(k,100,'fix',BL,ContextInfo,ContextInfo.accountID)ContextInfo.holdings[k]=1