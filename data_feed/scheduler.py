# -*- coding: utf-8 -*-

# scheduler.py
# 数据更新调度器：每个交易日(周一~周五)17:00 启动 data_feed_new.py
# data_feed_new.py 作为独立子进程运行，跑完自动退出并释放内存，
# 调度进程本身保持最小占用，适合后台常驻。

import subprocess
import time
from datetime import datetime
from pathlib import Path

# 依赖 data_feed_new.py 的相对 import(from data_feed_stock import StockData)，
# 必须把工作目录设为脚本所在目录
WORK_DIR = Path(__file__).parent
SCRIPT = WORK_DIR / "data_feed_new.py"
PYTHON = r"D:\work\git\clip-vq\venv\Scripts\python.exe"
LOG_FILE = WORK_DIR / "update_log.txt"


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_update():
    """启动 data_feed_new.py 子进程，输出重定向到日志文件"""
    log("开始运行 data_feed_new.py ...")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as out:
            proc = subprocess.run(
                [PYTHON, str(SCRIPT)],
                cwd=str(WORK_DIR),
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        log(f"更新完成, exit code={proc.returncode}")
    except Exception as e:
        log(f"更新失败: {e}")


def main():
    log("调度器已启动, 将于每个交易日(周一~周五)17:00 运行数据更新")
    while True:
        now = datetime.now()
        # weekday: 周一=0 ... 周五=4, 周六=5, 周日=6
        if now.weekday() < 5 and now.hour == 17 and now.minute == 0:
            run_update()
            time.sleep(120)  # 跳过17:00整点，避免同分钟重复触发
        else:
            time.sleep(30)   # 每30秒检查一次，占用极小


if __name__ == "__main__":
    main()
