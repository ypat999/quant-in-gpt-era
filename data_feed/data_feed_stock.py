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

class StockData:
    def __init__(self, data_type='stock'):
        """
        :param data_type: None (默认，同时支持股票和基金) | 'stock' 股票模式 | 'fund' 基金模式
        """
        self.data_type = data_type
        self.data_dir = f'D:/work/quant/stock_data/csv'
        self.ensure_data_dir()
        self.min_request_interval = timedelta(milliseconds=200)
        self.last_request_time = datetime.now()
        self.verbose_output = False
        # self.quering_thread = 0
        self.single_thread = True
        
    def ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def save_to_csv(self, data, filename):
        """保存数据到CSV文件"""
        filepath = os.path.join(self.data_dir, filename)
        try:
            df = pd.DataFrame(data)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')  # 修改编码为utf-8-sig
            if self.verbose_output:
                print(f"数据已保存到: {os.path.abspath(filepath)}")
            return True
        except Exception as e:
            print(f"保存数据失败 - {filename}: {str(e)}")
            return False

    def load_from_csv(self, filename):
        """从CSV文件加载数据"""
        filepath = os.path.join(self.data_dir, filename)
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, encoding='utf-8', dtype={'code': str})
                if self.verbose_output:
                    print(f"加载数据: {os.path.abspath(filepath)}")
                return df.to_dict(orient='records')
            except Exception as e:
                print(f"读取文件出错 {filename}: {str(e)}")
                return None
        return None

    def _get_stock_list(self, update = False, cache_file = 'stock_list.csv'):
        """获取股票列表"""
        try:
            if not update:
                # 尝试从缓存加载
                cached_data = self.load_from_csv(cache_file)
                if cached_data and (datetime.now() - datetime.strptime(cached_data[0]['update_time'], '%Y-%m-%d %H:%M:%S')).days < 30:
                    print(f"使用缓存的股票列表: {os.path.join(self.data_dir, cache_file)}")
                    return [stock for stock in cached_data if stock['update_time']]

            # 在线获取
            print("获取最新股票列表...")
            df = ak.stock_zh_a_spot_em()

            # 提取股票信息
            stocks = []
            for _, row in df.iterrows():
                stocks.append({
                    'name': row['名称'],
                    'code': row['代码'],
                    'price': float(row['最新价']),
                    'pe': float(row['市盈率-动态']) if row['市盈率-动态'] != '-' else None,
                    'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            #按code排序
            stocks.sort(key=lambda x: x['code'])
            # 保存到缓存
            self.save_to_csv(stocks, cache_file)
            print(f"已获取 {len(stocks)} 只股票")

            return stocks

        except Exception as e:
            print(f"获取股票列表出错: {str(e)}")
            return []
    
    def get_history_data(self, code, start_date=None, end_date=None, local_only=False):
        """获取股票历史行情数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            local_only: 是否仅从本地缓存获取
        """
        code = str(code).split('.')[0]  # 去掉后缀
        
        # 尝试获取股票数据
        stock_data = self._get_generic_history_data(code, start_date, end_date, local_only)
        return stock_data

    def _get_generic_history_data(self, code, start_date=None, end_date=None, local_only=False):
        """通用股票历史数据获取方法
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            local_only: 是否仅从本地缓存获取
        """
        code = str(code).split('.')[0]  # 去掉后缀
        df = None
        
        try:
            # 确定缓存文件名
            cache_file = f'daily_{code}.csv'
            cached_data = self.load_from_csv(cache_file)
            
            # 设置默认日期范围
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=365*40)
            
            if cached_data:
                df = pd.DataFrame(cached_data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # 检查是否需要更新
                last_date = df.index.max() + timedelta(hours=15)
                if pd.Timestamp(last_date) >= pd.Timestamp(end_date - timedelta(hours=19)) or local_only:
                    # 截取所需时间段的数据
                    mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
                    if self.verbose_output:
                        print(f"使用缓存数据: {os.path.abspath(cache_file)}")
                    return df[mask]
                else:
                    start_date = last_date + timedelta(days=1) - timedelta(hours=15)
                    if self.verbose_output:
                        print(f"缓存数据已过期，重新获取缺失的最新数据: ", start_date)
            
            if local_only:
                return None
                
            # 请求延迟控制
            while datetime.now() < self.last_request_time + self.min_request_interval + timedelta(milliseconds=random.randint(200,2000)):
                time.sleep(0.5)
            
            self.last_request_time = datetime.now()

            if self.verbose_output:
                print(f"外部查询时间范围: {start_date} 到 {end_date}")

            # 获取股票数据
            symbol = code  # 股票代码格式处理
            for i in range(5):
                try:
                    # 从akshare获取数据
                    df_new = ak.stock_zh_a_hist(
                        symbol=symbol,
                        start_date=start_date.strftime('%Y%m%d'),
                        end_date=end_date.strftime('%Y%m%d'),
                        adjust='qfq'  # 前复权数据
                    )
                    
                    if df_new is None or df_new.empty:
                        print(f"没有获取到数据: {code},akshare返回空数据")
                    break
                except Exception as e:
                    print(f"获取股票数据接口出错 - {code}: {str(e)}")
                    time.sleep(random.uniform(30, 60))
            
            if df_new is None or df_new.empty:
                print(f"没有获取到数据: {code},akshare返回空数据")
                if df: 
                    return df
                else: 
                    return None
            
            # 重命名列以匹配backtrader要求
            rename_dict = {
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'pct_change',
                '涨跌额': 'change',
                '换手率': 'turnover',
                '股票代码': 'code'
            }
            
            df_new.rename(columns=rename_dict, inplace=True)
            
            # 转换日期列为datetime
            df_new['date'] = pd.to_datetime(df_new['date'])
            
            # 设置日期为索引
            df_new.set_index('date', inplace=True)
            
            # 按日期升序排序
            df_new.sort_index(inplace=True)
            
            # 确保数值列为float类型
            numeric_columns = ['open', 'close', 'high', 'low', 'volume']
            for col in numeric_columns:
                df_new[col] = pd.to_numeric(df_new[col], errors='coerce')
            
            # 检查数据完整性
            if df_new[numeric_columns].isnull().any().any():
                print(f"警告: {code} 数据中存在空值")
                df_new = df_new.dropna(subset=numeric_columns)
            
            # 检查数据是否有效
            if df_new.empty:
                print(f"数据无效: {code} (数据条数: {len(df_new)})")
                return None
            
            # 合并新旧数据
            if cached_data:
                df = pd.concat([df, df_new])
            else:
                df = df_new
            
            # 保存到缓存
            df_to_save = df.reset_index()
            # 将datetime转换为字符串
            df_to_save['date'] = df_to_save['date'].dt.strftime('%Y-%m-%d')
            self.save_to_csv(df_to_save.to_dict('records'), cache_file)

            # 打印数据基本信息
            if self.verbose_output:
                print(f"获取到 {code} 的历史数据:")
                print(f"时间范围: {df.index.min()} 到 {df.index.max()}")
                print(f"数据条数: {len(df)}")
            
            return df
            
        except Exception as e:
            print(f"获取历史数据出错 - {code}: {str(e)}")
            print(f"请检查股票代码格式是否正确，例如: '600754.SH' 或 '000001.SZ'")
            return None

    def update_daily_data(self, stock_code):
        """更新单只股票的日线数据
        
        Args:
            stock_code: 股票代码
        """
        stock_code = str(stock_code).split('.')[0]  # 去掉后缀
        
        try:
            # 获取股票历史数据
            df = self.get_history_data(stock_code)
            
            if df is not None and not df.empty:
                print(f"成功更新 {stock_code} 的日线数据")
                return True
            else:
                print(f"未能获取到 {stock_code} 的日线数据")
                return False
                
        except Exception as e:
            print(f"更新 {stock_code} 日线数据时出错: {str(e)}")
            return False

    def _batch_update_data_thread(self, items=None, update_func=None, thread_num=100):
        """通用批量更新数据方法（多线程版本）
        
        Args:
            items: 股票列表，None则获取所有股票
            update_func: 更新函数
            thread_num: 线程数量
        """
        # 获取股票列表
        if items is None:
            items = self._get_stock_list()
        if not items:
            print("获取股票列表失败")
            return False
        
        print(f"开始获取 {len(items)} 只股票的数据...")

        # 批量获取数据
        success_count = 0
        fail_count = 0
        
        # 定义线程锁，用于线程间共享资源的安全访问
        lock = threading.Lock()
        
        def update_item_data(item):
            nonlocal success_count, fail_count

            code = str(item['code'])
            name = item['name']
            if np.isnan(item['price']):
                print(f"股票 {code} 价格为空，跳过数据更新")
                return False  
            if self.verbose_output:
                print(f"\n正在获取 {code} {name} 的数据...")

            try:
                # 更新数据
                if update_func(code):
                    with lock:
                        success_count += 1
                    print(f"处理股票 {code} 完成，总成功数量: {success_count}，总失败数量: {fail_count}")
                    return True
                else:
                    print(f"处理股票 {code} 时出错")
                    with lock:
                        fail_count += 1
                    return False

            except Exception as e:
                print(f"处理股票 {code} 时出错: {str(e)}")
                with lock:
                    fail_count += 1
                return False
        

        if self.single_thread:
            # 单线程代码
            for item in items:
                try:
                    update_item_data(item)
                except Exception as exc:
                    print(f"{item} 生成过程中发生异常: {exc}")
        else:
            # # 使用线程池执行任务
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_num) as executor:
                future_to_item = {executor.submit(update_item_data, item): item for item in items}
                
                for future in concurrent.futures.as_completed(future_to_item):
                    item = future_to_item[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"{item} 生成过程中发生异常: {exc}")
        
        print(f"\n股票数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0

    def batch_update_daily_data_thread(self, stocks=None, thread_num=100):
        """批量更新股票日线数据（多线程版本）"""
        def update_func(code):
            # 判断股票代码类型并获取数据
            if code.startswith('6'):
                market = 'SH'
            elif code.startswith('3') or code.startswith('0'):
                market = 'SZ'
            elif code.startswith('8') or code.startswith('9') or code.startswith('4'):
                market = 'BJ'  # 北交所
            else:
                print(f"未知股票代码类型: {code}")
                return False
            return self.update_daily_data(f"{code}.{market}")
        
        return self._batch_update_data_thread(stocks, update_func, thread_num)

    def batch_update_report_data(self, stocks=None):
        """批量更新股票报告数据
        
        Args:
            stocks: 股票列表，None则获取所有股票
        """
        def update_func(code):
            # 获取财务数据
            report_data = self.get_stock_report(code)
            return report_data is not None
        
        return self._batch_update_data_thread(stocks, update_func)

    def get_stock_report(self, stock_code):
        """获取单个股票的财务数据"""
        stock_code = str(stock_code)
        stock_code = stock_code.split('.')[0]  # 去掉后缀
        try:
            # 检查是否已有数据

            filename = f'finance_{stock_code}.csv'
            cached_data = self.load_from_csv(filename)
            
            filepath = os.path.join(self.data_dir, filename)
            
            if cached_data:
                # 检查数据是否超过3个月
                if '日期' in cached_data[0]:
                    # 解析最新财务数据的日期
                    latest_date_str = str(cached_data[0]['日期'])
                    latest_date = datetime.strptime(latest_date_str, '%Y%m%d')
                    current_date = datetime.now()
                    
                    # 如果数据超过3个月，则重新获取
                    if (current_date - latest_date).days > 90:
                        print(f"财务数据已超过3个月，重新获取: {stock_code}")
                    else:
                        if self.verbose_output:
                            print(f"使用缓存的财务数据: {os.path.abspath(filepath)}")
                        return cached_data
            
            # 在线获取数据
            print(f"在线获取股票财务数据: {stock_code}")
            df = ak.stock_financial_abstract(symbol=stock_code)
            
            if df is None or df.empty:
                print(f"无法获取股票财务数据: {stock_code}")
                return None
            
            # print(df)
            # 删除df第一列
            df = df.drop(df.columns[0], axis=1)
            #将df的index设置为df的第一列
            df.index = df.iloc[:, 0]
            df = df.drop(df.columns[0], axis=1)
            # print(df)
            #复制df的标题并复制到第一行

            
            df = df.T
            df.reset_index(inplace=True)
            df.rename(columns={'index': '日期'}, inplace=True)
            # print(df)

            # 保存到文件

            self.save_to_csv(df, filename)
            if self.verbose_output:
                print(f"已保存 {stock_code} 的财务数据")
            return df

            
        except Exception as e:
            print(f"获取财务数据出错 - {stock_code}: {str(e)}")
            time.sleep(random.uniform(100, 200))
            return None

    def get_random_stock_code(self):
        """获取随机股票代码"""
        stocks = self._get_stock_list()
        if stocks:
            stock = random.choice(stocks)
            return stock['code']
        return None
