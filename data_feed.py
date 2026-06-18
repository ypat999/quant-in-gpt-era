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



class StockDataOld:
    def __init__(self, data_type='stock'):
        """
        :param data_type: 'stock' 股票模式 | 'fund' 基金模式
        """
        self.data_type = data_type
        self.data_dir = f'D:/work/quant/stock_data/csv'
        self.ensure_data_dir()
        self.min_request_interval = 1
        self.last_request_time = datetime.now()
        self.verbose_output = False
        # self.quering_thread = 0
        
    def ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    @staticmethod
    def _to_sina_symbol(code):
        """将股票代码转换为新浪格式 (sh/sz + 代码)
        沪市: 6开头(主板)、9开头(B股)、510/511/512/513/515/516/518/562/588/589(ETF/基金)
        深市: 0开头(主板)、3开头(创业板)、159(ETF)、1开头(基金)、2开头(B股)
        """
        code = code.split('.')[0]  # 去掉可能的后缀
        # 沪市股票
        if code.startswith('6') or code.startswith('9'):
            return f'sh{code}'
        # 沪市ETF/基金 (5开头且第二位为1/6/8)
        if code.startswith('5') and len(code) == 6 and code[1] in ('1', '6', '8'):
            return f'sh{code}'
        # 深市 (0/3开头股票, 159/1/2开头基金等)
        return f'sz{code}'
    
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

    
            
    
        
    def request_with_delay(self, func, *args, **kwargs):
        """带延迟的API请求"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed + random.random())
        self.last_request_time = time.time()
        return func(*args, **kwargs)
    
    def get_data_list(self, update: bool = False):
        """获取数据列表（股票/基金）"""
        try:
            cache_file = f'{self.data_type}_list.csv'
            if self.data_type == 'fund':
                return self._get_fund_list(update, cache_file)
            return self._get_stock_list(update, cache_file)
        except Exception as e:
            print(f"获取数据列表出错: {str(e)}")
            return []

    def _get_stock_list(self, update = False, cache_file = 'stock_list.csv'):
        """获取股票列表"""
        try:
            if not update:
                # 尝试从缓存加载
                cached_data = self.load_from_csv(cache_file)
                if cached_data and (datetime.now() - datetime.strptime(cached_data[0]['update_time'], '%Y-%m-%d %H:%M:%S')).days < 30:
                    print(f"使用缓存的股票列表: {os.path.join(self.data_dir, cache_file)}")
                    return [stock for stock in cached_data if stock['update_time']]

            # 在线获取 - 优先新浪，失败切换东财
            print("获取最新股票列表...")
            df = None
            last_err = None
            # 尝试新浪
            try:
                df = ak.stock_zh_a_spot()
            except Exception as e:
                last_err = e
                print(f"新浪获取失败: {e}")
            # 新浪失败，尝试东财
            if df is None:
                print("新浪获取失败，切换到东财数据源...")
                for attempt in range(3):
                    try:
                        df = ak.stock_zh_a_spot_em()
                        break
                    except Exception as e:
                        last_err = e
                        print(f"东财第 {attempt + 1}/3 次获取失败: {e}")
                        time.sleep(3 * (attempt + 1))
            if df is None:
                # 在线获取失败，回退到缓存（即使过期）
                cached_data = self.load_from_csv(cache_file)
                if cached_data:
                    print(f"在线获取失败，回退到缓存股票列表: {last_err}")
                    return [stock for stock in cached_data if stock['update_time']]
                raise Exception(f"新浪和东财均失败且无缓存: {last_err}")

            # 提取股票信息
            stocks = []
            for _, row in df.iterrows():
                stock_info = {
                    'name': row['名称'],
                    'code': row['代码'],
                    'price': float(row['最新价']),
                    'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                # 东财有市盈率字段，新浪没有
                if '市盈率-动态' in row.index:
                    stock_info['pe'] = float(row['市盈率-动态']) if row['市盈率-动态'] != '-' else None
                else:
                    stock_info['pe'] = None
                stocks.append(stock_info)
            #按code排序
            stocks.sort(key=lambda x: x['code'])
            # 保存到缓存
            self.save_to_csv(stocks, cache_file)
            print(f"已获取 {len(stocks)} 只股票")
            
            return stocks
            
        except Exception as e:
            print(f"获取股票列表出错: {str(e)}")
            return []
    
    def get_stock_finance(self, stock_code):
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
            # df = self.request_with_delay(ak.stock_financial_analysis_indicator, symbol=stock_code)
            df = ak.stock_financial_abstract(symbol=stock_code)
            
            for _ in range(3):
                try:
                    if df is None or df.empty:
                        print(f"无法获取股票财务数据: {stock_code}")
                        return None
                except:
                    continue
            
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

    def get_history_data(self, code: str, start_date=None, end_date=None, local_only=False):
        """获取历史数据（股票/基金）"""
        if self.data_type == 'fund':
            return self._get_fund_history_data(code, start_date, end_date, local_only)
        return self._get_stock_history_data(code, start_date, end_date, local_only)

    def _get_stock_history_data(self, stock_code, start_date, end_date, local_only):
        """获取股票历史数据"""
        stock_code = str(stock_code)
        stock_code = stock_code.split('.')[0]
        try:
            # 检查缓存
            cache_file = f'daily_{stock_code}.csv'
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
                
            # #随机暂停10到30秒
            # self.quering_thread += 1
            # sleep_time = self.quering_thread * random.randint(2,3)
            # print("sleep", sleep_time)
            # time.sleep(sleep_time)
            
            while datetime.now() < self.last_request_time + timedelta(
                                    seconds=(self.min_request_interval + random.randint(1,5))):
                time.sleep(1)

            with threading.Lock():
                self.last_request_time = datetime.now()

            # 处理股票代码格式
            symbol = stock_code.split('.')[0]  # 去掉后缀
            
            if self.verbose_output:
                print(f"外部查询时间范围: {start_date} 到 {end_date}")
            df_new = None
            # 优先从新浪获取数据
            try:
                sina_symbol = self._to_sina_symbol(symbol)
                df_new = ak.stock_zh_a_daily(
                    symbol=sina_symbol,
                    start_date=start_date.strftime('%Y%m%d'),
                    end_date=end_date.strftime('%Y%m%d'),
                    adjust='qfq'
                )
            except Exception as e:
                print(f"新浪获取出错 - {stock_code}: {str(e)}")
            
            # 新浪失败，切换东财
            if df_new is None or df_new.empty:
                print(f"新浪获取失败，切换东财数据源: {stock_code}")
                for i in range(3):
                    try:
                        df_new = ak.stock_zh_a_hist(
                            symbol=symbol,
                            start_date=start_date.strftime('%Y%m%d'),
                            end_date=end_date.strftime('%Y%m%d'),
                            adjust='qfq'
                        )
                        if df_new is not None and not df_new.empty:
                            break
                        print(f"东财返回空数据: {stock_code}")
                    except Exception as e:
                        print(f"东财获取出错 - {stock_code}: {str(e)}")
                        time.sleep(random.uniform(5, 15))
            
            if df_new is None or df_new.empty:
                print(f"没有获取到数据: {stock_code}, 东财和新浪均失败")
            
            # self.quering_thread -= 1

            # 重命名列以匹配backtrader要求
            # 东财返回中文列名，新浪返回英文列名，统一处理
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
                print(f"警告: {stock_code} 数据中存在空值")
                df_new = df_new.dropna(subset=numeric_columns)
            
            # 检查数据是否有效
            if df_new.empty:
                print(f"数据无效: {stock_code} (数据条数: {len(df_new)})")
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
                print(f"获取到 {stock_code} 的历史数据:")
                print(f"时间范围: {df.index.min()} 到 {df.index.max()}")
                print(f"数据条数: {len(df)}")
            
            return df
            
        except Exception as e:
            print(f"获取历史数据出错 - {stock_code}: {str(e)}")
            print(f"请检查股票代码格式是否正确，例如: '600754.SH' 或 '000001.SZ'")

    def update_daily_data(self, stock_code):
        """更新单只股票的日线数据"""
        try:
            # 获取最新数据
           # 今天星期几
            today = datetime.now().weekday()
            if today == 0 and datetime.now().hour < 15: 
                today = 7
            # 如果是周六或周日，获取前一个工作日的数据
            
            # 设置默认日期范围
            end_date = end_date = datetime.now()
            if today >=5:
                end_date = datetime.now() - timedelta(days=(today - 4))
                    
            start_date = end_date - timedelta(days=365*40)  # 获取40年数据
            
            df = self.get_history_data(stock_code, start_date, end_date)
            if df is not None:
                if self.verbose_output:
                    print(f"成功更新 {stock_code} 的日线数据")
                return True
            return False
            
        except Exception as e:
            print(f"更新日线数据失败 - {stock_code}: {str(e)}")
            return False


    def _get_fund_history_data(self, fund_code, start_date=None, end_date=None, local_only=False):
        """获取基金历史数据"""
        fund_code = str(fund_code).split('.')[0]  # 去掉后缀
        df = None
        try:
            # 检查缓存
            cache_file = f'fund_daily_{fund_code}.csv'
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
                
            # #随机暂停10到30秒
            # self.quering_thread += 1
            # sleep_time = self.quering_thread * random.randint(2,3)
            # print("sleep", sleep_time)
            # time.sleep(sleep_time)
            
            while datetime.now() < self.last_request_time + timedelta(
                                    seconds=(self.min_request_interval + random.randint(1,5))):
                time.sleep(random.randint(1,5))

            with threading.Lock():
                self.last_request_time = datetime.now()

            if self.verbose_output:
                print(f"外部查询时间范围: {start_date} 到 {end_date}")

            # 优先从新浪获取数据
            df_new = None
            try:
                sina_symbol = self._to_sina_symbol(fund_code)
                df_new = ak.fund_etf_hist_sina(symbol=sina_symbol)
                if df_new is not None and not df_new.empty:
                    # 新浪返回全量数据，需要按日期筛选
                    df_new['date'] = pd.to_datetime(df_new['date'])
                    mask = (df_new['date'] >= pd.Timestamp(start_date)) & (df_new['date'] <= pd.Timestamp(end_date))
                    df_new = df_new[mask]
            except Exception as e:
                print(f"新浪获取基金数据出错 - {fund_code}: {str(e)}")

            # 新浪失败，切换东财
            if df_new is None or df_new.empty:
                for i in range(3):
                    df_new = None
                    try:
                        df_new = ak.fund_etf_hist_em(
                            symbol=fund_code,
                            start_date=start_date.strftime('%Y%m%d'),
                            end_date=end_date.strftime('%Y%m%d')
                        )
                    except Exception as e:
                        if self.verbose_output:
                            print(f"东财ETF获取失败 - {fund_code}: {str(e)}")
                    if df_new is not None and not df_new.empty:
                        break
                    try:
                        df_new = ak.fund_lof_hist_em(
                            symbol=fund_code,
                            start_date=start_date.strftime('%Y%m%d'),
                            end_date=end_date.strftime('%Y%m%d')
                        )
                    except Exception as e:
                        if self.verbose_output:
                            print(f"东财LOF获取失败 - {fund_code}: {str(e)}")
                    if df_new is not None and not df_new.empty:
                        break
                    time.sleep(3)
            
            # self.quering_thread -= 1

            if df_new is None:
                print(f"没有获取到数据: {fund_code},akshare返回空数据")
                if df: return df
                else : return None
            elif df_new.empty:
                print(f"没有获取到数据: {fund_code},akshare返回空数据")
                if df: return df
                else : return None
            
            # 重命名列以匹配backtrader要求
            # 东财返回中文列名，新浪返回英文列名，统一处理
            rename_dict = {
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '涨跌幅': 'pct_change',
                '涨跌额': 'change',
                '换手率': 'turnover',
                '股票代码': 'code',
                '振幅': 'amplitude'
            }
            
            df_new.rename(columns=rename_dict, inplace=True)
            
            # 新浪数据日期可能已被转换过，确保统一格式
            if not pd.api.types.is_datetime64_any_dtype(df_new['date']):
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
                print(f"警告: {fund_code} 数据中存在空值")
                df_new = df_new.dropna(subset=numeric_columns)
            
            # 检查数据是否有效
            if df_new.empty:
                print(f"数据无效: {fund_code} (数据条数: {len(df_new)}) ")
                return None
            
            # 合并新旧数据
            if cached_data:
                df = pd.concat([df, df_new])
            else:
                df = df_new
            
            # 保存到缓存
            try:
                df_to_save = df.reset_index()
                df_to_save['date'] = df_to_save['date'].dt.strftime('%Y-%m-%d')
                if not self.save_to_csv(df_to_save.to_dict('records'), cache_file):
                    print(f"缓存保存失败: {fund_code}")
            except Exception as save_error:
                print(f"缓存保存异常 - {fund_code}: {str(save_error)}")
            
            # 打印数据基本信息
            if self.verbose_output:
                print(f"获取到 {fund_code} 的历史数据:")
                print(f"时间范围: {df.index.min()} 到 {df.index.max()}")
                print(f"数据条数: {len(df)}")
            
            return df
            
        except Exception as e:
            print(f"获取历史数据出错 - {fund_code}: {str(e)}")
            print(f"请检查基金代码格式是否正确，例如: '510050' ")

    def _get_fund_list(self, update: bool = False, cache_file = 'fund_list.csv'):
        """获取基金列表"""
        try:
            if not update:
                # 尝试从缓存加载
                cached_data = self.load_from_csv(cache_file)
                if cached_data and (datetime.now() - datetime.strptime(cached_data[0]['update_time'], '%Y-%m-%d %H:%M:%S')).days < 30:
                    print(f"使用缓存的基金列表: {os.path.join(self.data_dir, cache_file)}")
                    return [fund for fund in cached_data if fund['update_time']]

            # 在线获取
            print("获取最新基金列表...")
            # 获取不同类型基金数据
            lof_df = ak.fund_etf_category_sina(symbol = "LOF基金")
            etf_df = ak.fund_etf_category_sina(symbol = "ETF基金")
            close_fund_df = ak.fund_etf_category_sina(symbol = "封闭式基金")
            # fund_df = ak.fund_name_em()


            # 处理ETF基金数据
            etf_funds = [{
                'name': row['名称'],
                'code': row['代码'][2:],
                'fund_type': 'ETF',
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            } for _, row in etf_df.iterrows()]

            # 处理LOF基金数据
            lof_funds = [{
                'name': row['名称'],
                'code': row['代码'][2:],
                'fund_type': 'LOF',
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            } for _, row in lof_df.iterrows()]

            # 处理封闭式基金数据
            close_fund = [{
                'name': row['名称'],
                'code': row['代码'][2:],
                'fund_type': '封闭式',
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            } for _, row in close_fund_df.iterrows()]

            # 合并并去重
            seen_codes = set()
            funds = []
            for fund in etf_funds + lof_funds + close_fund:
                if fund['code'] not in seen_codes:
                    seen_codes.add(fund['code'])
                    funds.append(fund)

            # 保存到缓存
            self.save_to_csv(funds, cache_file)

            print(f"已获取 {len(funds)} 只基金")
            
            return funds
            
        except Exception as e:
            print(f"获取基金列表出错: {str(e)}")
            return []
   
    def batch_update_daily_data(self, stocks=None, test_mode=False):
        """批量更新股票日线数据
        
        Args:
            stocks: 股票列表，None则获取所有股票
            test_mode: 测试模式，只处理少量股票
        """
        # 获取股票列表
        if stocks is None:
            stocks = self._get_stock_list()
        if not stocks:
            print("获取股票列表失败")
            return False
            
        if test_mode:
            stocks = stocks[:10]  # 测试模式只处理10只股票
        
        print(f"开始获取 {len(stocks)} 只股票的历史日线数据...")
        
        # 批量获取历史数据
        success_count = 0
        fail_count = 0
        
        for i, stock in enumerate(stocks, 1):
            try:
                price = stock['price']
                if np.isnan(price):
                    print(f"股票 {code} 价格为空，跳过更新")
                    continue
                code = str(stock['code'])
                name = stock['name']
                print(f"\n[{i}/{len(stocks)}] 正在获取 {code} {name} 的历史日线数据...")
                
                if code.startswith('6'):
                    market = 'SH'
                elif code.startswith('3') or code.startswith('0'):
                    market = 'SZ'
                elif code.startswith('8') or code.startswith('9') or code.startswith('4'):
                    market = 'BJ'  # 北交所
                else:
                    print(f"未知股票代码类型: {code}")
                    return False
        
                # 获取历史数据
                if self.update_daily_data(f"{code}.{market}"):
                    success_count += 1
                else:
                    fail_count += 1
                
            except Exception as e:
                print(f"处理股票 {code} 时出错: {str(e)}")
                fail_count += 1
                continue
        
        print("\n日线数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0


    def batch_update_daily_data_thread(self, stocks=None, test_mode=False):
        """批量更新股票日线数据"""
        
        # 获取股票列表
        if stocks is None:
            stocks = self._get_stock_list()
        if not stocks:
            print("获取股票列表失败")
            return False
            
        if test_mode:
            stocks = stocks[:10]  # 测试模式只处理10只股票
        
        print(f"开始获取 {len(stocks)} 只股票的历史日线数据...")

        stocks.reverse()
        
        # 批量获取历史数据
        success_count = 0
        fail_count = 0
        
        # 定义线程锁，用于线程间共享资源的安全访问
        lock = threading.Lock()
        
        def update_stock_data(stock):
            if np.isnan(stock['price']):
                print(f"股票 {code} 价格为空，跳过更新")
                return False
            nonlocal success_count, fail_count

            code = str(stock['code'])
            name = stock['name']
            if self.verbose_output:
                print(f"\n正在获取 {code} {name} 的历史日线数据...")

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

            for retry in range(3):
                time.sleep(random.uniform(1, 2))
                try:
                    if self.update_daily_data(f"{code}.{market}"):
                        with lock:
                            success_count += 1
                        print(f"处理股票 {code}.{market} 完成，总成功数量: {success_count}，总失败数量: {fail_count}")
                        time.sleep(0.5)
                        return True
                    else:
                        print(f"处理股票 {code}.{market} 时出错")

                        # 添加延时，避免请求过于频繁
                        time.sleep(random.uniform(1, 2))

                except Exception as e:
                    print(f"处理股票 {code}.{market} 时出错: {str(e)}，重试 {retry + 1}...")
                    #暂停5秒
                    time.sleep(random.uniform(1, 2))
                    continue
            with lock:
                fail_count += 1
            return False
        
        # 使用线程池执行任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            future_to_stock = {executor.submit(update_stock_data, stock): stock for stock in stocks}
            
            for future in concurrent.futures.as_completed(future_to_stock):
                stock = future_to_stock[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"{stock} 生成过程中发生异常: {exc}")
        
        print("\n日线数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0

    
    def batch_update_finance_data(self, stocks=None, test_mode=False):
        """批量更新股票财务数据
        
        Args:
            stocks: 股票列表，None则获取所有股票
            test_mode: 测试模式，只处理少量股票
        """
        # 获取股票列表
        if stocks is None:
            stocks = self._get_stock_list()
        if not stocks:
            print("获取股票列表失败")
            return False
            
        if test_mode:
            stocks = stocks[:10]  # 测试模式只处理10只股票
        
        print(f"开始获取 {len(stocks)} 只股票的财务数据...")
        
        # 批量获取财务数据
        success_count = 0
        fail_count = 0
        
        for i, stock in enumerate(stocks, 1):
            try:
                if np.isnan(stock['price']):
                    print(f"股票 {code} 价格为空，跳过财务数据更新")
                    continue

                code = str(stock['code'])
                name = stock['name']

                print(f"\n[{i}/{len(stocks)}] 正在获取 {code} {name} 的财务数据...")
                
                # 获取财务数据
                finance_data = self.get_stock_finance(code)
                if  finance_data is not None:
                    success_count += 1
                else:
                    fail_count += 1
                
                # 添加延时，避免请求过于频繁
                time.sleep(random.uniform(1, 2))
                
            except Exception as e:
                print(f"处理财务数据 {code} 时出错: {str(e)}")
                fail_count += 1
                continue
        
        print("\n财务数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0

    def batch_update_funds_data(self, funds=None, test_mode=False):
        """批量更新基金日K线数据
        
        Args:
            funds: 基金列表，None则获取所有基金
            test_mode: 测试模式，只处理少量基金
        """
        # 获取基金列表
        if funds is None:
            funds = self._get_fund_list()
        if not funds:
            print("获取基金列表失败")
            return False
            
        if test_mode:
            funds = funds[:10]  # 测试模式只处理10只基金
        
        print(f"开始获取 {len(funds)} 只基金的日K线数据...")
        
        # 批量获取日K线数据
        success_count = 0
        fail_count = 0
        
        for i, fund in enumerate(funds, 1):
            try:
                code = str(fund['code'])
                name = fund['name']
                print(f"\n[{i}/{len(funds)}] 正在获取 {code} {name} 的日K线数据...")
                
                # 获取日K线数据
                if self._get_fund_history_data(code) is not None:
                    success_count += 1
                else:
                    fail_count += 1
                
                # 添加延时，避免请求过于频繁
                time.sleep(random.uniform(1, 2))
                
            except Exception as e:
                print(f"处理基金 {code} 时出错: {str(e)}")
                fail_count += 1
                continue
        
        print("\n基金日K线数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0

    def batch_update_funds_data_thread(self, funds=None, test_mode=False):
        """批量更新基金日K线数据
        
        Args:
            funds: 基金列表，None则获取所有基金
            test_mode: 测试模式，只处理少量基金
        """
        # 获取基金列表
        if funds is None:
            funds = self._get_fund_list()
        if not funds:
            print("获取基金列表失败")
            return False
            
        if test_mode:
            funds = funds[:10]  # 测试模式只处理10只基金
        
        print(f"开始获取 {len(funds)} 只基金的日K线数据...")
        
        # 批量获取日K线数据
        success_count = 0
        fail_count = 0
        
        # 定义线程锁，用于线程间共享资源的安全访问
        lock = threading.Lock()
        
        def update_fund_data(fund):
            nonlocal success_count, fail_count

            code = str(fund['code'])
            name = fund['name']
            if self.verbose_output:
                print(f"\n正在获取 {code} {name} 的日K线数据...")

            try:
                # 获取日K线数据
                if self._get_fund_history_data(code) is not None:
                    with lock:
                        success_count += 1
                    print(f"处理基金 {code} 完成，总成功数量: {success_count}，总失败数量: {fail_count}")
                    return True
                else:
                    print(f"处理基金 {code} 时出错")
                    with lock:
                        fail_count += 1
                    return False

            except Exception as e:
                print(f"处理基金 {code} 时出错: {str(e)}")
                with lock:
                    fail_count += 1
                return False
        
        # 使用线程池执行任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            future_to_fund = {executor.submit(update_fund_data, fund): fund for fund in funds}
            
            for future in concurrent.futures.as_completed(future_to_fund):
                fund = future_to_fund[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"{fund} 生成过程中发生异常: {exc}")
        
        print("\n基金日K线数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0

    def update_all_data(self, test_mode=False):
        """更新所有数据（包括日线数据和财务数据）
        
        Args:
            test_mode: 测试模式，只处理少量股票
        """
        print("开始全量更新股票数据...")
        
        self.verbose_output = True

        # 获取股票列表
        if test_mode:
            update = False
        else:   
            update = True

        stocks = self._get_stock_list()
        if not stocks:
            print("获取股票列表失败")
            return False

        # stocks = stocks[2900:]
        # stocks逆序
        stocks = stocks[::-1]

        # 更新日线数据
        # daily_result = self.batch_update_daily_data(stocks, test_mode)
        daily_result = self.batch_update_daily_data_thread(stocks, test_mode)

        #等待输入
        # input("按Enter键继续...")

        # 获取基金列表示例
        funds = stock_data._get_fund_list()
        if not funds:
            print("获取基金列表失败")
            return False
        # print(f"基金列表: {funds}")
        # 批量更新基金日K线数据

        # self.batch_update_funds_data(funds=funds, test_mode=False)
        self.batch_update_funds_data_thread(funds=funds, test_mode=False)

        
        # 更新财务数据
        # finance_result = self.batch_update_finance_data(stocks, test_mode)
        
        # return daily_result and finance_result
        
    def get_random_stock_code(self):
        """获取随机股票代码"""
        stocks = self._get_stock_list()
        if stocks:
            stock = random.choice(stocks)
            return stock['code']
        return None


if __name__ == '__main__':
    #配置代理
    # os.environ['HTTP_PROXY'] = 'http://127.0.0.1:10809'
    # os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:10809'
    stock_data = StockDataOld()
    
    # 运行测试模式
    stock_data.update_all_data(test_mode=False)



