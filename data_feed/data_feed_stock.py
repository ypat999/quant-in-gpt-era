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
                # 读取时指定所有列都作为字符串，避免日期等列被自动转换为数字
                df = pd.read_csv(filepath, encoding='utf-8-sig', dtype=str)
                if self.verbose_output:
                    print(f"加载数据: {os.path.abspath(filepath)}")
                return df.to_dict(orient='records')
            except Exception as e:
                print(f"读取文件出错 {filename}: {str(e)}")
                return None
        return None

    def _is_cache_fresh(self, filename):
        """快速判断缓存是否新鲜，通过文件修改时间而非解析数据
        
        规则：如果文件修改时间在今天15:00之后（收盘后），则数据是新鲜的
        返回: (is_fresh, filepath)
        """
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            return False, filepath
        
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            now = datetime.now()
            
            # 今天15:00后更新的文件，数据是新鲜的
            today_cutoff = now.replace(hour=15, minute=0, second=0, microsecond=0)
            
            if now >= today_cutoff:
                # 当前在收盘后，文件必须是今天15:00后更新的
                return mtime >= today_cutoff, filepath
            else:
                # 当前在开盘前/盘中，文件必须是昨天15:00后更新的
                yesterday_cutoff = (now - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
                return mtime >= yesterday_cutoff, filepath
        except Exception:
            return False, filepath

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
            df = None
            last_err = None
            
            # 优先尝试新浪接口
            try:
                df = ak.stock_zh_a_spot()
                print("成功从新浪接口获取股票列表")
            except Exception as e:
                last_err = e
                print(f"新浪接口获取失败: {e}")
            
            # 新浪失败,尝试东财接口(备选)
            if df is None:
                print("新浪接口失败,尝试东财接口...")
                for attempt in range(3):
                    try:
                        df = ak.stock_zh_a_spot_em()
                        print("成功从东财接口获取股票列表")
                        break
                    except Exception as e:
                        last_err = e
                        print(f"东财接口第 {attempt + 1}/3 次获取失败: {e}")
                        time.sleep(3 * (attempt + 1))
            
            # 所有接口都失败,回退到缓存(即使过期)
            if df is None:
                cached_data = self.load_from_csv(cache_file)
                if cached_data:
                    print(f"在线获取失败,回退到缓存股票列表: {last_err}")
                    return [stock for stock in cached_data if stock['update_time']]
                print(f"获取股票列表失败: {last_err}")
                return []

            # 提取股票信息
            stocks = []
            for _, row in df.iterrows():
                try:
                    # 处理股票代码,去除前缀(如"sz", "sh", "bj")
                    code = str(row['代码'])
                    if code.startswith(('sz', 'sh', 'bj')):
                        code = code[2:]  # 去除前2个字符的前缀
                    
                    # 新浪接口没有市盈率字段,设置为None
                    pe_value = None
                    # 如果是东财接口,尝试获取市盈率
                    if '市盈率-动态' in df.columns:
                        pe_value = float(row['市盈率-动态']) if row['市盈率-动态'] != '-' else None
                    
                    stocks.append({
                        'name': row['名称'],
                        'code': code,
                        'price': float(row['最新价']),
                        'pe': pe_value,
                        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                except Exception as e:
                    if self.verbose_output:
                        print(f"处理股票 {row.get('代码', 'unknown')} 数据时出错: {e}")
                    continue
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
            cache_file = f'daily_{code}.csv'
            
            # 设置默认日期范围
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=365*40)
            
            # 快速判断缓存是否新鲜（通过文件修改时间，不解析CSV）
            is_fresh, filepath = self._is_cache_fresh(cache_file)
            
            if is_fresh:
                # 缓存新鲜，直接加载返回
                cached_data = self.load_from_csv(cache_file)
                if cached_data:
                    df = pd.DataFrame(cached_data)
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    
                    if local_only:
                        return df
                    
                    # 截取所需时间段
                    mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
                    return df[mask]
            
            # 缓存不新鲜或不存在，需要判断是加载旧缓存增量更新，还是全新获取
            cached_data = self.load_from_csv(cache_file)
            
            if cached_data:
                df = pd.DataFrame(cached_data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                if local_only:
                    return df
                
                # 检查缓存最新日期，决定增量更新的起始日期
                last_date = df.index.max() + timedelta(hours=15)
                if pd.Timestamp(last_date) >= pd.Timestamp(end_date - timedelta(hours=19)):
                    # 数据已是最新（文件修改时间判断不准确时回退验证）
                    mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
                    return df[mask]
                else:
                    start_date = last_date + timedelta(days=1) - timedelta(hours=15)
                    print(f"缓存数据已过期，增量获取: {code} (从 {start_date.strftime('%Y-%m-%d')})")
            
            if local_only:
                return None
                
            # 请求延迟控制
            while datetime.now() < self.last_request_time + self.min_request_interval + timedelta(milliseconds=random.randint(200,2000)):
                time.sleep(0.5)
            
            self.last_request_time = datetime.now()

            if self.verbose_output:
                print(f"外部查询时间范围: {start_date} 到 {end_date}")

            # 获取股票数据
            # 主数据源: 新浪接口 (stock_zh_a_daily)
            # 备选数据源: 雅虎财经 (需安装yfinance: pip install yfinance)
            df_new = None
            
            # 构建市场前缀 (新浪接口需要)
            if code.startswith('6'):
                sina_symbol = f"sh{code}"  # 上交所
            elif code.startswith('92'):
                sina_symbol = f"bj{code}"  # 北交所 (92开头)
            elif code.startswith('0') or code.startswith('3'):
                sina_symbol = f"sz{code}"  # 深交所
            elif code.startswith('8') or code.startswith('4'):
                sina_symbol = f"bj{code}"  # 北交所 (其他)
            else:
                sina_symbol = f"sz{code}"  # 默认深交所
            
            # 尝试从新浪接口获取数据
            ssl_error_count = 0
            for i in range(5):
                try:
                    df_new = ak.stock_zh_a_daily(
                        symbol=sina_symbol,
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d'),
                        adjust='qfq'  # 前复权数据
                    )
                    
                    if df_new is not None and not df_new.empty:
                        if self.verbose_output:
                            print(f"成功从新浪接口获取数据: {sina_symbol}")
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
                        if ssl_error_count >= 3:  # SSL错误超过3次，跳过该股票
                            print(f"SSL错误持续发生，跳过股票 {code}")
                            df_new = None
                            break
                    else:
                        print(f"新浪接口获取数据出错 - {code}: {error_msg}")
                    time.sleep(random.uniform(30, 60))
            
            # 如果新浪接口失败,尝试雅虎财经(如果已安装yfinance)
            if df_new is None or df_new.empty:
                try:
                    import yfinance as yf
                    # 转换股票代码格式: 000001 -> 000001.SZ 或 600000 -> 600000.SS
                    if code.startswith('6'):
                        yf_symbol = f"{code}.SS"  # 上交所
                    elif code.startswith('0') or code.startswith('3'):
                        yf_symbol = f"{code}.SZ"  # 深交所
                    else:
                        yf_symbol = f"{code}.SZ"  # 默认深交所
                    
                    print(f"尝试从雅虎财经获取数据: {yf_symbol}")
                    ticker = yf.Ticker(yf_symbol)
                    df_yf = ticker.history(
                        start=start_date.strftime('%Y-%m-%d'),
                        end=end_date.strftime('%Y-%m-%d')
                    )
                    
                    if df_yf is not None and not df_yf.empty:
                        # 转换雅虎财经数据格式
                        df_new = df_yf.reset_index()
                        df_new.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pct_change']
                        print(f"成功从雅虎财经获取数据: {yf_symbol}")
                except ImportError:
                    if self.verbose_output:
                        print("未安装yfinance库,跳过雅虎财经备选方案")
                except Exception as e:
                    if self.verbose_output:
                        print(f"雅虎财经获取失败: {e}")
            
            if df_new is None or df_new.empty:
                print(f"没有获取到数据: {code},新浪接口返回空数据")
                # 返回之前已有的数据(如果有)
                if df is not None and not df.empty: 
                    return df
                else: 
                    return None
            
            # 新浪接口列名已经是英文,只需确保包含必要列
            # 列名: ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'outstanding_share', 'turnover']
            # 只保留需要的列
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
            print(f"请检查股票代码格式是否正确，例如: '600754.SH' 或 '000001.SZ'")
            return None

    def update_daily_data(self, stock_code):
        """更新单只股票的日线数据
        
        Args:
            stock_code: 股票代码
        Returns:
            True: 数据已最新或更新成功
            'cache_hit': 缓存命中，数据已是最新
            False: 更新失败
        """
        stock_code = str(stock_code).split('.')[0]  # 去掉后缀
        
        # 快速判断缓存是否新鲜，如果新鲜直接返回，不解析CSV
        cache_file = f'daily_{stock_code}.csv'
        is_fresh, _ = self._is_cache_fresh(cache_file)
        if is_fresh:
            return 'cache_hit'
        
        try:
            # 获取股票历史数据（缓存不新鲜时才走这里）
            df = self.get_history_data(stock_code)
            
            if df is not None and not df.empty:
                return True
            else:
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
        
        # 性能统计
        total_start_time = time.time()
        last_report_time = total_start_time
        processed_count = 0
        cache_hit_count = 0  # 缓存命中次数
        
        # 各步骤耗时统计
        step_times = {
            'check_price': 0.0,
            'update_func': 0.0,
            'total': 0.0
        }
        
        # 定义线程锁，用于线程间共享资源的安全访问
        lock = threading.Lock()
        
        def update_item_data(item):
            nonlocal success_count, fail_count, processed_count, last_report_time
            nonlocal step_times, cache_hit_count
            
            item_start_time = time.time()
            
            code = str(item['code'])
            name = item['name']
            
            # 步骤1：检查价格
            step_start = time.time()
            try:
                price = float(item['price']) if item['price'] != 'nan' else np.nan
            except (ValueError, TypeError):
                price = np.nan
            
            if pd.isna(price):
                print(f"股票 {code} 价格为空，跳过数据更新")
                return False  
            step_times['check_price'] += time.time() - step_start
            
            if self.verbose_output:
                print(f"\n正在获取 {code} {name} 的数据...")

            try:
                # 步骤2：更新数据
                step_start = time.time()
                result = update_func(code)
                step_times['update_func'] += time.time() - step_start
                
                if result:  # True 或 'cache_hit'
                    with lock:
                        success_count += 1
                        processed_count += 1
                        if result == 'cache_hit':
                            cache_hit_count += 1
                    print(f"处理股票 {code} 完成，总成功数量: {success_count}，总失败数量: {fail_count}")
                    result = True
                else:
                    print(f"处理股票 {code} 时出错")
                    with lock:
                        fail_count += 1
                        processed_count += 1
                    result = False
                
                # 每分钟输出一次性能统计
                current_time = time.time()
                if current_time - last_report_time >= 60:
                    elapsed = current_time - total_start_time
                    avg_time = elapsed / processed_count if processed_count > 0 else 0
                    
                    print(f"\n{'='*60}")
                    print(f"性能统计（已处理 {processed_count}/{len(items)} 只）:")
                    print(f"  总耗时: {elapsed:.1f}秒")
                    print(f"  平均每只: {avg_time:.3f}秒")
                    print(f"  缓存命中: {cache_hit_count} 只 (跳过网络请求)")
                    print(f"  步骤耗时:")
                    print(f"    - 检查价格: {step_times['check_price']:.2f}秒 ({step_times['check_price']/elapsed*100:.1f}%)")
                    print(f"    - 更新数据: {step_times['update_func']:.2f}秒 ({step_times['update_func']/elapsed*100:.1f}%)")
                    print(f"{'='*60}\n")
                    last_report_time = current_time
                
                return result

            except Exception as e:
                print(f"处理股票 {code} 时出错: {str(e)}")
                with lock:
                    fail_count += 1
                    processed_count += 1
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
            filename = f'finance_{stock_code}.csv'
            filepath = os.path.join(self.data_dir, filename)
            
            # 加载缓存数据（后续无论成功失败都可能用到）
            cached_data = self.load_from_csv(filename)
            
            # 快速判断：缓存新鲜则直接返回
            is_fresh, _ = self._is_cache_fresh(filename)
            if is_fresh and cached_data:
                if self.verbose_output:
                    print(f"使用缓存的财务数据: {stock_code}")
                return cached_data
            
            # 检查是否有"获取失败"的标记文件（7天内不再重试在线获取）
            fail_flag = filepath + '.fail'
            if os.path.exists(fail_flag):
                fail_mtime = datetime.fromtimestamp(os.path.getmtime(fail_flag))
                if (datetime.now() - fail_mtime).days < 7:
                    # 不重试在线获取，但有旧缓存就返回旧数据
                    if cached_data:
                        return cached_data
                    return None
                else:
                    os.remove(fail_flag)  # 超过7天，删除标记重试
            
            # 检查缓存数据是否在有效期内
            # 季度财报每3个月发布，加上1-2个月报告延迟，最新数据可能就有4-5个月"旧"
            # 所以阈值设为150天（5个月），避免反复获取同样"旧"的数据
            if cached_data and '日期' in cached_data[0]:
                try:
                    latest_date_str = str(cached_data[0]['日期'])
                    if '.' in latest_date_str:
                        latest_date_str = latest_date_str.split('.')[0]
                    latest_date = datetime.strptime(latest_date_str, '%Y%m%d')
                    current_date = datetime.now()
                    
                    if (current_date - latest_date).days <= 150:
                        if self.verbose_output:
                            print(f"使用缓存的财务数据: {stock_code}")
                        return cached_data
                    else:
                        print(f"财务数据已超过5个月，尝试重新获取: {stock_code}")
                except (ValueError, TypeError) as e:
                    print(f"财务数据日期解析失败: {stock_code}, 尝试重新获取")
            
            # 在线获取数据
            print(f"在线获取股票财务数据: {stock_code}")
            df = ak.stock_financial_abstract(symbol=stock_code)
            
            if df is None or df.empty:
                print(f"无法获取股票财务数据: {stock_code}")
                # 写入失败标记，7天内不再重试
                with open(fail_flag, 'w') as f:
                    f.write(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                # 在线获取失败，但有旧缓存就返回旧数据（旧数据比没数据好）
                if cached_data:
                    print(f"使用过期缓存的财务数据: {stock_code}")
                    return cached_data
                return None
            
            df = df.drop(df.columns[0], axis=1)
            df.index = df.iloc[:, 0]
            df = df.drop(df.columns[0], axis=1)
            
            df = df.T
            df.reset_index(inplace=True)
            df.rename(columns={'index': '日期'}, inplace=True)

            self.save_to_csv(df, filename)
            if self.verbose_output:
                print(f"已保存 {stock_code} 的财务数据")
            # 获取成功，删除可能存在的失败标记
            if os.path.exists(fail_flag):
                os.remove(fail_flag)
            return df

            
        except Exception as e:
            print(f"获取财务数据出错 - {stock_code}: {str(e)}")
            # 写入失败标记，7天内不再重试
            fail_flag = os.path.join(self.data_dir, f'finance_{stock_code}.csv.fail')
            with open(fail_flag, 'w') as f:
                f.write(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            # 在线获取失败，但有旧缓存就返回旧数据
            cached_data = self.load_from_csv(f'finance_{stock_code}.csv')
            if cached_data:
                print(f"使用过期缓存的财务数据: {stock_code}")
                return cached_data
            return None

    def _prev_trading_day(self, now=None):
        """计算上一个交易日（仅跳过周末，不考虑节假日调休）

        Args:
            now: datetime，默认当前时间
        Returns:
            date，上一个交易日
        """
        now = now or datetime.now()
        d = now.date() - timedelta(days=1)
        while d.weekday() >= 5:  # 周六=5, 周日=6
            d -= timedelta(days=1)
        return d

    def get_latest_date(self, code):
        """读取本地缓存最新日期

        Args:
            code: 股票代码
        Returns:
            str '%Y-%m-%d'，无缓存返回 None
        """
        code = str(code).split('.')[0]
        filepath = os.path.join(self.data_dir, f'daily_{code}.csv')
        if not os.path.exists(filepath):
            return None
        try:
            df = pd.read_csv(filepath, encoding='utf-8-sig', usecols=['date'])
            if df.empty:
                return None
            return pd.to_datetime(df['date']).max().strftime('%Y-%m-%d')
        except Exception:
            return None

    def _spot_to_kline(self, df, trading_date):
        """把全市场实时快照转换为当日K线记录

        Args:
            df: ak.stock_zh_a_spot / stock_zh_a_spot_em 返回的DataFrame
            trading_date: 交易日期 '%Y-%m-%d'
        Returns:
            dict {code: {date, open, high, low, close, volume, amount}}
        """
        def num(v):
            try:
                x = float(v)
                return x if not np.isnan(x) else np.nan
            except (ValueError, TypeError):
                return np.nan

        out = {}
        for _, row in df.iterrows():
            code = str(row['代码'])
            if code.startswith(('sz', 'sh', 'bj')):
                code = code[2:]
            close = num(row.get('最新价'))
            if np.isnan(close):
                continue  # 停牌或无价格的票跳过
            out[code] = {
                'date': trading_date,
                'open': num(row.get('今开')),
                'high': num(row.get('最高')),
                'low': num(row.get('最低')),
                'close': close,
                'volume': num(row.get('成交量')),
                'amount': num(row.get('成交额')),
            }
        return out

    def _fetch_today_spot(self, trading_date):
        """拉取全市场当日行情（新浪优先，东财备用）

        Args:
            trading_date: 交易日期 '%Y-%m-%d'
        Returns:
            dict {code: 当日K线记录}
        """
        # 优先新浪接口
        try:
            df = ak.stock_zh_a_spot()
            if df is not None and '代码' in df.columns:
                return self._spot_to_kline(df, trading_date)
        except Exception as e:
            print(f"新浪全市场接口失败: {e}")
        # 东财备用
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and '代码' in df.columns:
                return self._spot_to_kline(df, trading_date)
        except Exception as e:
            print(f"东财全市场接口失败: {e}")
        return {}

    def _append_kline(self, code, row):
        """把一天K线追加/更新到本地缓存

        Args:
            code: 股票代码
            row: dict，含 date/open/high/low/close/volume/amount
        Returns:
            bool
        """
        code = str(code).split('.')[0]
        filepath = os.path.join(self.data_dir, f'daily_{code}.csv')
        if not os.path.exists(filepath):
            return False
        try:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
            df = df[df['date'] != row['date']]
            new_row = pd.DataFrame([row])
            df = pd.concat([df, new_row], ignore_index=True).sort_values('date')
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            return True
        except Exception as e:
            print(f"追加K线失败 {code}: {e}")
            return False

    def batch_update_daily_hybrid(self, thread_num=20):
        """混合每日更新

        先扫描本地数据：
        - 最新日期==上一交易日 的票：用全市场接口一次性补齐今日K线
        - 最新日期<上一交易日 的票（断档）：用个股接口完整拉取
        不考虑节假日调休，仅跳过周末。

        Args:
            thread_num: 断档个股查询线程数
        Returns:
            bool
        """
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        prev_day = self._prev_trading_day(now)
        prev_str = prev_day.strftime('%Y-%m-%d')

        stocks = self._get_stock_list()
        if not stocks:
            print("获取股票列表失败")
            return False

        fresh_codes = []   # 已到上一交易日，只需补今日
        stale_codes = []   # 断档，需完整查询
        for s in stocks:
            code = str(s['code'])
            latest = self.get_latest_date(code)
            if latest == prev_str:
                fresh_codes.append(code)
            elif latest and latest != today_str:
                stale_codes.append(code)
            # latest==today 已是最新，跳过；无缓存的不处理

        print(f"上一交易日: {prev_str}, 今日: {today_str}")
        print(f"已到上一交易日、需补今日的票: {len(fresh_codes)}")
        print(f"断档、需完整查询的票: {len(stale_codes)}")

        # 1. 全市场接口补齐今日
        if fresh_codes:
            print("拉取全市场当日行情...")
            spot = self._fetch_today_spot(today_str)
            updated = 0
            for code in fresh_codes:
                if code in spot:
                    if self._append_kline(code, spot[code]):
                        updated += 1
            print(f"全市场接口补今日完成: {updated}/{len(fresh_codes)}")

        # 2. 断档票：删除缓存后完整拉取
        if stale_codes:
            print("断档票完整查询中...")
            total, success = len(stale_codes), 0

            def reload(code):
                filepath = os.path.join(self.data_dir, f'daily_{code}.csv')
                if os.path.exists(filepath):
                    os.remove(filepath)  # 强制全新拉取
                try:
                    df = self.get_history_data(code)
                    return df is not None and not df.empty
                except Exception:
                    return False

            if self.single_thread:
                for code in stale_codes:
                    if reload(code):
                        success += 1
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=thread_num) as executor:
                    future_to_code = {executor.submit(reload, c): c for c in stale_codes}
                    for future in concurrent.futures.as_completed(future_to_code):
                        if future.result():
                            success += 1
            print(f"断档票完整查询完成: {success}/{total}")

        return True

    def get_random_stock_code(self):
        """获取随机股票代码"""
        stocks = self._get_stock_list()
        if stocks:
            stock = random.choice(stocks)
            return stock['code']
        return None
