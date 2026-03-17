import subprocess
import time
import json
import os

# ==================== 本地化配置 ====================
# 你的笔记本只有一张显卡，我们只定义一个本地 GPU 任务槽
available_gpus = ["localhost:0"]

jobs_folder = "jobs"
# 这里的路径改为你容器内的实际工作目录
project_dir = "/home/jsyoon/mctd" 

# 跟踪运行中的进程
running_experiments = {gpu: None for gpu in available_gpus}

def start_experiment(gpu_id, config):
    """直接在当前容器内启动 Python 进程，不再使用 SSH 和 Docker"""
    command_args = ""
    for key, value in config.items():
        command_args += f"{key}={value} "
    
    # 构造直接运行的命令
    # 强制指定设备为 gpu_id (通常是 0)
    cmd = f"CUDA_VISIBLE_DEVICES={gpu_id} python3 main.py {command_args} wandb.mode=online experiment.validation.batch_size=1"
    print(f"执行命令: {cmd}")
    # 使用 Popen 后台运行，这样脚本可以继续监控
    process = subprocess.Popen(cmd, shell=True, stdout=open(f"log_gpu{gpu_id}.txt", "w"), stderr=subprocess.STDOUT)
    return process

def check_gpu_memory_usage(server, gpu_id):
    """本地环境直接返回空闲，绕过 nvidia-smi 检查"""
    return 0, 24000

def is_experiment_running(process):
    """检查本地进程是否还在运行"""
    if process is None:
        return False
    return process.poll() is None

# ==================== 核心逻辑 ====================

# 确保 jobs 文件夹存在
assert os.path.exists(jobs_folder), f"jobs folder does not exist"

queue_is_empty = False
config_files = sorted(os.listdir(f"{jobs_folder}/"))

if config_files:
    config_file = config_files[0]
    with open(f"{jobs_folder}/{config_file}", "r") as f:
        config = json.load(f)
else:
    queue_is_empty = True

print(f"检测到任务队列，准备开始...")

while not queue_is_empty:
    for gpu, process in list(running_experiments.items()):
        server, gpu_id = gpu.split(":")
        
        # 1. 检查当前 GPU 上的任务是否跑完了
        if process is not None and not is_experiment_running(process):
            print(f"GPU {gpu} 的任务已完成。")
            running_experiments[gpu] = None
        
        # 2. 如果 GPU 空闲，启动新任务
        if running_experiments[gpu] is None and not queue_is_empty:
            current_time = time.strftime("%Y%m%d-%H%M%S")
            print(f"正在 GPU {gpu} 上启动任务: {config_file}")
            
            # 启动进程
            new_process = start_experiment(gpu_id, config)
            running_experiments[gpu] = new_process
            
            # 从队列中移除已领取的任务
            os.remove(f"{jobs_folder}/{config_file}")
            
            # 尝试读取下一个任务
            time.sleep(2) # 稍微等一下防止文件系统冲突
            config_files = sorted(os.listdir(f"{jobs_folder}/"))
            if config_files:
                config_file = config_files[0]
                with open(f"{jobs_folder}/{config_file}", "r") as f:
                    config = json.load(f)
            else:
                print("队列已全部处理完毕！")
                queue_is_empty = True
                break
                
    time.sleep(10)  # 每 5 秒巡检一次