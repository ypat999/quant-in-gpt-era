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

class FundData:
    def __init__(self, data_type='fund'):
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
                # 读取时指定所有列都作为字符串，避免日期等列被自动转换为数字
                df = pd.read_csv(filepath, encoding='utf-8-sig', dtype=str)
                if self.verbose_output:
                    print(f"加载数据: {os.path.abspath(filepath)}")
                return df.to_dict(orient='records')
            except Exception as e:
                print(f"读取文件出错 {filename}: {str(e)}")
                return None
        return None

    def _get_fund_list(self, update = False, cache_file = 'fund_list.csv'):
        """获取基金列表 (LOF/ETF/封闭式基金)"""
        try:
            if not update:
                # 尝试从缓存加载
                cached_data = self.load_from_csv(cache_file)
                if cached_data and (datetime.now() - datetime.strptime(cached_data[0]['update_time'], '%Y-%m-%d %H:%M:%S')).days < 30:
                    print(f"使用缓存的基金列表: {os.path.join(self.data_dir, cache_file)}")
                    return [fund for fund in cached_data if fund['update_time']]

            # 在线获取
            print("获取最新基金列表...")
            
            # 获取LOF基金列表(带重试)
            df_lof = None
            for attempt in range(3):
                try:
                    df_lof = ak.fund_lof_spot_em()
                    if df_lof is not None and not df_lof.empty:
                        print(f"成功获取LOF基金列表: {len(df_lof)} 只")
                        break
                except Exception as e:
                    print(f"获取LOF基金列表第 {attempt + 1}/3 次失败: {e}")
                    if attempt < 2:
                        time.sleep(3 * (attempt + 1))
            
            # 获取ETF基金列表(带重试)
            df_etf = None
            for attempt in range(3):
                try:
                    df_etf = ak.fund_etf_spot_em()
                    if df_etf is not None and not df_etf.empty:
                        print(f"成功获取ETF基金列表: {len(df_etf)} 只")
                        break
                except Exception as e:
                    print(f"获取ETF基金列表第 {attempt + 1}/3 次失败: {e}")
                    if attempt < 2:
                        time.sleep(3 * (attempt + 1))
            
            # 封闭式基金接口已废弃,仅获取ETF和LOF
            df_close = None
            # for attempt in range(3):
            #     try:
            #         df_close = ak.fund_close_spot_em()
            #         if df_close is not None and not df_close.empty:
            #             print(f"成功获取封闭式基金列表: {len(df_close)} 只")
            #             break
            #     except Exception as e:
            #         print(f"获取封闭式基金列表第 {attempt + 1}/3 次失败: {e}")
            #         if attempt < 2:
            #             time.sleep(3 * (attempt + 1))
            
            # 如果所有接口都失败,回退到缓存(即使过期)
            if (df_lof is None or df_lof.empty) and \
               (df_etf is None or df_etf.empty) and \
               (df_close is None or df_close.empty):
                cached_data = self.load_from_csv(cache_file)
                if cached_data:
                    print("在线获取基金列表失败,回退到缓存数据")
                    return [fund for fund in cached_data if fund['update_time']]
                print("获取基金列表失败")
                return []

            # 提取基金信息
            funds = []
            for df, fund_type in [(df_lof, 'LOF'), (df_etf, 'ETF'), (df_close, '封闭式')]:
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        try:
                            funds.append({
                                'name': row['名称'],
                                'code': row['代码'],
                                'price': float(row['最新价']),
                                'type': fund_type,
                                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                        except Exception as e:
                            if self.verbose_output:
                                print(f"处理基金 {row.get('代码', 'unknown')} 数据时出错: {e}")
                            continue
            
            # 按code排序
            funds.sort(key=lambda x: x['code'])
            # 去重（有些基金可能在多个列表中）
            seen = set()
            unique_funds = []
            for fund in funds:
                if fund['code'] not in seen:
                    seen.add(fund['code'])
                    unique_funds.append(fund)
            # 保存到缓存
            self.save_to_csv(unique_funds, cache_file)
            print(f"已获取 {len(unique_funds)} 只基金")

            return unique_funds

        except Exception as e:
            print(f"获取基金列表出错: {str(e)}")
            # 尝试回退到缓存
            cached_data = self.load_from_csv(cache_file)
            if cached_data:
                print("回退到缓存基金列表")
                return [fund for fund in cached_data if fund['update_time']]
            return []
    
    def get_history_data(self, code, start_date=None, end_date=None, local_only=False):
        """获取基金历史行情数据
        
        Args:
            code: 基金代码
            start_date: 开始日期
            end_date: 结束日期
            local_only: 是否仅从本地缓存获取
        """
        code = str(code).split('.')[0]  # 去掉后缀
        
        # 尝试获取基金数据
        fund_data = self._get_generic_history_data(code, start_date, end_date, local_only)
        return fund_data

    def _get_generic_history_data(self, code, start_date=None, end_date=None, local_only=False):
        """通用基金历史数据获取方法
        
        Args:
            code: 基金代码
            start_date: 开始日期
            end_date: 结束日期
            local_only: 是否仅从本地缓存获取
        """
        code = str(code).split('.')[0]  # 去掉后缀
        df = None
        
        try:
            # 确定缓存文件名
            cache_file = f'fund_daily_{code}.csv'
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

            # 获取基金数据
            # 主数据源: 新浪接口 (fund_etf_hist_sina)
            df_new = None  # 初始化变量
            
            # 构建市场前缀 (新浪接口需要)
            # 基金代码以5开头是上交所(sh),以1开头是深交所(sz)
            if code.startswith('5'):
                sina_symbol = f"sh{code}"  # 上交所
            elif code.startswith('1'):
                sina_symbol = f"sz{code}"  # 深交所
            else:
                sina_symbol = f"sz{code}"  # 默认深交所
            
            # 尝试从新浪接口获取数据
            ssl_error_count = 0
            for i in range(5):
                try:
                    # 新浪接口返回全部历史数据,没有日期参数
                    df_new = ak.fund_etf_hist_sina(symbol=sina_symbol)
                    
                    if df_new is not None and not df_new.empty:
                        if self.verbose_output:
                            print(f"成功从新浪接口获取基金数据: {sina_symbol}")
                        break
                    else:
                        print(f"新浪接口返回空数据: {code}")
                except Exception as e:
                    error_msg = str(e)
                    # 检测SSL证书错误
                    if 'SSL' in error_msg or 'CERTIFICATE_VERIFY_FAILED' in error_msg or 'Hostname mismatch' in error_msg:
                        ssl_error_count += 1
                        if ssl_error_count == 1:  # 只在第一次SSL错误时提示
                            print(f"⚠️ SSL证书验证失败 - {code}: 可能是网络代理或证书问题")
                            print(f"   建议检查: 1) 是否使用代理 2) 系统时间是否正确 3) 继续重试...")
                        if ssl_error_count >= 3:  # SSL错误超过3次，跳过该基金
                            print(f"SSL错误持续发生，跳过基金 {code}")
                            df_new = None
                            break
                    else:
                        print(f"新浪接口获取基金数据出错 - {code}: {error_msg}")
                    time.sleep(random.uniform(30, 60))
            
            if df_new is None or df_new.empty:
                print(f"没有获取到数据: {code},新浪接口返回空数据")
                # 返回之前已有的数据(如果有)
                if df is not None and not df.empty: 
                    return df
                else: 
                    return None
            
            # 新浪接口列名已经是英文,只需确保包含必要列
            # 列名: ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'postVol', 'postAmt']
            required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            
            # 确保必要的列存在
            for col in required_columns:
                if col not in df_new.columns:
                    print(f"警告: {code} 数据缺少必要列: {col}")
                    return None
            
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
            print(f"请检查基金代码格式是否正确，例如: '159915.SZ'")
            return None

    def update_daily_data(self, fund_code):
        """更新单只基金的日线数据
        
        Args:
            fund_code: 基金代码
        """
        fund_code = str(fund_code).split('.')[0]  # 去掉后缀
        
        try:
            # 获取基金历史数据
            df = self.get_history_data(fund_code)
            
            if df is not None and not df.empty:
                print(f"成功更新 {fund_code} 的日线数据")
                return True
            else:
                print(f"未能获取到 {fund_code} 的日线数据")
                return False
                
        except Exception as e:
            print(f"更新 {fund_code} 日线数据时出错: {str(e)}")
            return False

    def _batch_update_data_thread(self, items=None, update_func=None, thread_num=100):
        """通用批量更新数据方法（多线程版本）
        
        Args:
            items: 基金列表，None则获取所有基金
            update_func: 更新函数
            thread_num: 线程数量
        """
        # 获取基金列表
        if items is None:
            items = self._get_fund_list()
        if not items:
            print("获取基金列表失败")
            return False
        
        print(f"开始获取 {len(items)} 只基金的数据...")

        # 批量获取数据
        success_count = 0
        fail_count = 0
        
        # 定义线程锁，用于线程间共享资源的安全访问
        lock = threading.Lock()
        
        def update_item_data(item):
            nonlocal success_count, fail_count

            code = str(item['code'])
            name = item['name']

            if self.verbose_output:
                print(f"\n正在获取 {code} {name} 的数据...")

            try:
                # 更新数据
                if update_func(code):
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_num) as executor:
            future_to_item = {executor.submit(update_item_data, item): item for item in items}
            
            for future in concurrent.futures.as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"{item} 生成过程中发生异常: {exc}")
        
        print(f"\n基金数据获取完成!")
        print(f"成功: {success_count} 只")
        print(f"失败: {fail_count} 只")
        print(f"数据保存在: {os.path.abspath(self.data_dir)}")
        return success_count > 0

    def batch_update_daily_data_thread(self, funds=None, thread_num=100):
        """批量更新基金日线数据（多线程版本）"""
        def update_func(code):
            return self.update_daily_data(code)
        
        return self._batch_update_data_thread(funds, update_func, thread_num)
        