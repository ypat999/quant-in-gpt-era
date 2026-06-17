#巴菲特量化交易策略代码实现
import threading
import backtrader as bt
from datetime import datetime
import concurrent
import pandas as pd
from data_feed import StockData

class StockSelector:
    def __init__(self):
        self.stock_data = StockData()
        
    def select_stocks(self):
        """选股主函数"""
        try:
            # 获取股票列表
            stocks = self.stock_data.get_stock_list()
            if not stocks:
                print("无法获取股票列表")
                return []
            
            print(f"\n开始处理 {len(stocks)} 只股票...")
            qualified_stocks = []

            lock = threading.Lock()

            def select_stock_thread(stock):
                finance_data = self.stock_data.get_stock_finance(stock['code'])
                if finance_data is None:
                    return
                
                # 获取最新一期数据
                latest_period = finance_data[0]['日期']
                latest_data = finance_data[0]
                for finance_data_single in finance_data:
                    if finance_data_single['日期'] > latest_period:
                        latest_period = finance_data_single['日期']
                        latest_data = finance_data_single
                # 检查是否满足条件，原始条件为20/40/5
                try:
                    if (float(latest_data['净资产收益率(ROE)']) > 20 and
                        float(latest_data['毛利率']) > 40 and
                        float(latest_data['销售净利率']) > 5):
                        stock.update({
                            'roe': float(latest_data['净资产收益率(ROE)']),
                            'gross_margin': float(latest_data['毛利率']),
                            'net_margin': float(latest_data['销售净利率']),
                            'report_date': latest_period
                        })
                        with lock:
                            qualified_stocks.append(stock)
                            self._print_stock_info(stock)
                except Exception as e:
                    return
                

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                future_to_stock = {executor.submit(select_stock_thread, stock): stock for stock in stocks}
                
                for future in concurrent.futures.as_completed(future_to_stock):
                    stock = future_to_stock[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"{stock} 生成过程中发生异常: {exc}")
            '''
            for idx, stock in enumerate(stocks, 1):
                print(f"\r处理进度: {idx}/{len(stocks)} ({idx/len(stocks)*100:.1f}%)", end='')
                
                # 获取财务数据
                finance_data = self.stock_data.get_stock_finance(stock['code'])
                if finance_data is None:
                    continue
                
                # 获取最新一期数据
                latest_period = finance_data[0]['日期']
                latest_data = finance_data[0]
                for finance_data_single in finance_data:
                    if finance_data_single['日期'] > latest_period:
                        latest_period = finance_data_single['日期']
                        latest_data = finance_data_single
                
                # 检查是否满足条件，原始条件为20/40/5
                try:
                    if (float(latest_data['净资产收益率(ROE)']) > 10 and
                        float(latest_data['毛利率']) > 20 and
                        float(latest_data['销售净利率']) > 3):
                        stock.update({
                            'roe': float(latest_data['净资产收益率(ROE)']),
                            'gross_margin': float(latest_data['毛利率']),
                            'net_margin': float(latest_data['销售净利率']),
                            'report_date': latest_period
                        })
                        qualified_stocks.append(stock)
                        self._print_stock_info(stock)
                except Exception as e:
                    continue
                        
            '''
            self._print_summary(qualified_stocks)
            return qualified_stocks
            
        except Exception as e:
            print(f"选股过程出错: {str(e)}")
            return []
    
    def _print_stock_info(self, stock):
        """打印单个股票信息"""
        print(f"\n股票符合条件: {stock['code']} {stock['name']}")
        print(f"ROE: {stock['roe']}%")
        print(f"毛利率: {stock['gross_margin']}%")
        print(f"净利率: {stock['net_margin']}%")
    
    def _print_summary(self, qualified_stocks):
        """打印选股结果汇总"""
        print(f"\n\n选股结果:")
        print(f"符合条件的股票数: {len(qualified_stocks)}")
        print(f"符合条件的股票列表: ")
        for stock in qualified_stocks:
            print(f"{stock['code']} {stock['name']} ROE: {stock['roe']}% 毛利率: {stock['gross_margin']}% 净利率: {stock['net_margin']}% 报告期: {stock['report_date']}")
        
        if qualified_stocks:
            # 保存选股结果
            self.stock_data.save_json({
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stocks': qualified_stocks
            }, 'selected_stocks.json')

def main():
    selector = StockSelector()
    selector.select_stocks()

if __name__ == '__main__':
    main() 