# -*- coding: utf-8 -*-

# data_feed_new.py

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import time
import random
import threading
import concurrent.futures
import numpy as np

from data_feed_stock import StockData
from data_feed_fund import FundData

class FinanceData:
    def __init__(self, data_type=None):
        """
        :param data_type: None (默认，同时支持股票和基金) | 'stock' 股票模式 | 'fund' 基金模式
        """
        self.data_type = data_type
        self.min_request_interval = 1.0
        self.last_request_time = 0
        self.verbose_output = False
        # self.quering_thread = 0
        
        # 初始化股票和基金数据对象
        self.stock_data = StockData('stock')
        self.fund_data = FundData('fund')

    def update_all_data(self, thread_num=1):
        """更新所有数据
        
        Args:
            thread_num: 线程数量
        """
        print("开始更新所有数据...")
        
        # 更新股票日线数据
        print("\n更新股票日线数据...")
        self.stock_data.batch_update_daily_data_thread(thread_num=thread_num)
        
        # 更新股票财务数据
        print("\n更新股票财务数据...")
        # self.stock_data.batch_update_report_data(stocks)
        
        # 更新基金日线数据
        print("\n更新基金日线数据...")
        self.fund_data.batch_update_daily_data_thread(thread_num=thread_num)
        
        print("\n所有数据更新完成!")

    def get_random_stock_code(self):
        """获取随机股票代码"""
        return self.stock_data.get_random_stock_code()

# 主程序入口
if __name__ == '__main__':
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:10809'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:10809'
    # 创建FinanceData实例
    stock_data = FinanceData()
    
    # 更新所有数据
    stock_data.update_all_data()



