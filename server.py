from flask import Flask, request, jsonify, Response
import sys
import os
import json
import subprocess
import threading
import time
import shutil
import yaml
import requests
import logging
from logging.handlers import RotatingFileHandler
import traceback

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加文件处理器以确保日志持久化
file_handler = RotatingFileHandler('comfyui_server.log', maxBytes=10000000, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

app = Flask(__name__)

COMFY_ROOT = "/app/ComfyUI"
NAS_ROOT = "/mnt/nas/comfyui"
COMFY_PORT = "8188"
comfy_process = None

def verify_nas_structure():
    """验证NAS目录结构并确保必要的目录存在"""
    logger.info("开始验证NAS目录结构...")
    required_dirs = [
        'models',
        'configs',
        'custom_nodes',
        'embeddings',
        'loras',
        'vae',
        'checkpoints',
        'extensions',
        'workflows'
    ]
    
    try:
        for dir_name in required_dirs:
            dir_path = os.path.join(NAS_ROOT, dir_name)
            if not os.path.exists(dir_path):
                logger.info(f"创建目录: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"目录创建成功: {dir_path}")
            else:
                logger.info(f"目录已存在: {dir_path}")
        logger.info("NAS目录结构验证完成")
    except Exception as e:
        logger.error(f"创建目录结构时发生错误: {str(e)}", exc_info=True)
        raise

def verify_config_file():
    """验证ComfyUI配置文件"""
    config_path = os.path.join(COMFY_ROOT, "extra_model_paths.yaml")
    logger.info(f"检查配置文件: {config_path}")
    
    try:
        if not os.path.exists(config_path):
            logger.error("配置文件不存在")
            return False
            
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"配置文件内容: {config}")
            return True
    except Exception as e:
        logger.error(f"读取配置文件时发生错误: {str(e)}", exc_info=True)
        return False

def read_process_output(process, name="ComfyUI"):
    """持续读取进程输出"""
    while True:
        output = process.stdout.readline()
        if output:
            logger.info(f"{name} 输出: {output.strip()}")
        error = process.stderr.readline()
        if error:
            logger.error(f"{name} 错误: {error.strip()}")
        if output == '' and error == '' and process.poll() is not None:
            break

def wait_for_comfyui(timeout=60):
    """等待ComfyUI启动并测试连接"""
    logger.info(f"等待ComfyUI启动，超时时间: {timeout}秒")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"http://127.0.0.1:{COMFY_PORT}/", timeout=5)
            if response.status_code == 200:
                logger.info("ComfyUI服务已就绪")
                return True
            logger.info(f"ComfyUI返回状态码: {response.status_code}")
        except requests.exceptions.RequestException:
            logger.info("ComfyUI尚未就绪，继续等待...")
        time.sleep(5)
    logger.error("等待ComfyUI启动超时")
    return False

def start_comfyui():
    """启动ComfyUI进程"""
    global comfy_process
    if comfy_process is None:
        try:
            logger.info("准备启动ComfyUI进程...")
            verify_nas_structure()
            verify_config_file()
            
            cmd = [
                "python3", 
                "main.py", 
                "--listen", 
                "0.0.0.0", 
                "--port", 
                COMFY_PORT,
                "--extra-model-paths-config", 
                "extra_model_paths.yaml"
            ]
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            comfy_process = subprocess.Popen(
                cmd,
                cwd=COMFY_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            logger.info("ComfyUI进程已启动，进程ID: %d", comfy_process.pid)
            
            # 创建线程来监控输出
            threading.Thread(target=read_process_output, args=(comfy_process,), daemon=True).start()
            
            # 等待服务就绪
            if not wait_for_comfyui(timeout=60):
                raise Exception("ComfyUI服务启动失败")
            
            logger.info("ComfyUI进程启动成功")
            
        except Exception as e:
            logger.error(f"启动ComfyUI时发生错误: {str(e)}", exc_info=True)
            if comfy_process:
                comfy_process.terminate()
                comfy_process = None
            raise
@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    logger.info("执行健康检查...")
    try:
        response_data = {
            "timestamp": time.time(),
            "checks": {}
        }
        
        # 检查NAS挂载状态
        nas_mounted = os.path.ismount(NAS_ROOT)
        response_data["checks"]["nas_mount"] = {
            "status": "ok" if nas_mounted else "error",
            "message": "NAS mounted" if nas_mounted else "NAS not mounted",
            "path": NAS_ROOT
        }
        logger.info(f"NAS挂载状态: {nas_mounted}")
        
        # 检查ComfyUI进程状态
        comfy_running = comfy_process and comfy_process.poll() is None
        response_data["checks"]["comfyui_process"] = {
            "status": "ok" if comfy_running else "error",
            "message": "ComfyUI running" if comfy_running else "ComfyUI not running",
            "pid": comfy_process.pid if comfy_running else None
        }
        logger.info(f"ComfyUI进程状态: {'运行中' if comfy_running else '未运行'}")
        
        # 检查配置文件
        config_ok = verify_config_file()
        response_data["checks"]["config_file"] = {
            "status": "ok" if config_ok else "error",
            "message": "Config file valid" if config_ok else "Config file invalid"
        }
        
        # 汇总状态
        overall_status = "ok" if all(check["status"] == "ok" for check in response_data["checks"].values()) else "error"
        response_data["overall_status"] = overall_status
        
        status_code = 200 if overall_status == "ok" else 500
        return jsonify(response_data), status_code
            
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/workflow', methods=['POST'])
def handle_workflow():
    """处理工作流请求"""
    request_id = f"workflow_{time.time()}"
    logger.info(f"处理工作流请求 [{request_id}]...")
    try:
        workflow_data = request.json
        logger.info(f"接收到工作流数据 [{request_id}]: {json.dumps(workflow_data, indent=2)}")
        
        if comfy_process is None or comfy_process.poll() is not None:
            logger.info(f"ComfyUI未运行，正在启动... [{request_id}]")
            start_comfyui()
        
        workflow_path = os.path.join(NAS_ROOT, 'workflows', f'workflow_{request_id}.json')
        logger.info(f"保存工作流到: {workflow_path}")
        
        with open(workflow_path, 'w') as f:
            json.dump(workflow_data, f, indent=2)
            logger.info(f"工作流文件保存成功 [{request_id}]")
        
        logger.info(f"工作流处理成功 [{request_id}]")
        return jsonify({
            "status": "success",
            "message": "Workflow processed",
            "request_id": request_id,
            "workflow_saved": workflow_path
        }), 200
        
    except Exception as e:
        logger.error(f"处理工作流时发生错误 [{request_id}]: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e),
            "request_id": request_id,
            "traceback": traceback.format_exc()
        }), 500

@app.route('/nas/status', methods=['GET'])
def nas_status():
    """检查NAS存储状态"""
    logger.info("检查NAS状态...")
    try:
        nas_info = {
            "timestamp": time.time(),
            "mounted": os.path.ismount(NAS_ROOT),
            "mount_point": NAS_ROOT,
            "directories": {}
        }
        
        if nas_info["mounted"]:
            total_size = 0
            total_files = 0
            
            for dir_name in ['models', 'custom_nodes', 'extensions', 'workflows']:
                dir_path = os.path.join(NAS_ROOT, dir_name)
                
                if os.path.exists(dir_path):
                    files = os.listdir(dir_path)
                    size = sum(os.path.getsize(os.path.join(dir_path, f)) for f in files if os.path.isfile(os.path.join(dir_path, f)))
                    
                    logger.info(f"目录 {dir_name}: {len(files)} 个文件, {size/1024/1024:.2f}MB")
                    
                    nas_info["directories"][dir_name] = {
                        "exists": True,
                        "files": len(files),
                        "size_bytes": size,
                        "size_mb": size/1024/1024
                    }
                    
                    total_size += size
                    total_files += len(files)
                else:
                    logger.warning(f"目录不存在: {dir_path}")
                    nas_info["directories"][dir_name] = {
                        "exists": False
                    }
            
            nas_info["total_files"] = total_files
            nas_info["total_size_mb"] = total_size/1024/1024
            
        logger.info("NAS状态检查完成")
        return jsonify(nas_info), 200
    except Exception as e:
        logger.error(f"检查NAS状态时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """处理所有到 ComfyUI 的请求"""
    request_id = f"request_{time.time()}"
    logger.info(f"处理请求 [{request_id}] PATH: {path}")
    try:
        logger.info(f"请求方法: {request.method}")
        logger.info(f"请求头: {dict(request.headers)}")
        logger.info(f"请求参数: {dict(request.args)}")
        
        if comfy_process is None or comfy_process.poll() is not None:
            logger.info(f"ComfyUI未运行，正在启动... [{request_id}]")
            start_comfyui()

        url = f'http://127.0.0.1:{COMFY_PORT}/{path}'
        logger.info(f"转发请求到: {url} [{request_id}]")
        
        request_start_time = time.time()
        resp = requests.request(
            method=request.method,
            url=url,
            headers={key: value for key, value in request.headers if key != 'Host'},
            data=request.get_data(),
            params=request.args,
            allow_redirects=False
        )
        request_duration = time.time() - request_start_time
        
        logger.info(f"收到ComfyUI响应 [{request_id}] - 状态码: {resp.status_code}, 耗时: {request_duration:.2f}秒")

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for name, value in resp.raw.headers.items()
                  if name.lower() not in excluded_headers]

        return Response(resp.content, resp.status_code, headers)

    except requests.exceptions.RequestException as e:
        logger.error(f"转发请求时发生错误 [{request_id}]: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "request_id": request_id,
            "traceback": traceback.format_exc()
        }), 500
    except Exception as e:
        logger.error(f"处理请求时发生未预期的错误 [{request_id}]: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "request_id": request_id,
            "traceback": traceback.format_exc()
        }), 500

if __name__ == '__main__':
    logger.info("=== 启动应用服务器 ===")
    logger.info(f"工作目录: {os.getcwd()}")
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"ComfyUI路径: {COMFY_ROOT}")
    logger.info(f"NAS挂载点: {NAS_ROOT}")
    
    try:
        logger.info("初始化ComfyUI...")
        start_comfyui()
        
        logger.info(f"启动Flask服务器，监听端口: 9000")
        app.run(host='0.0.0.0', port=9000)
    except Exception as e:
        logger.error(f"启动服务器时发生错误: {str(e)}", exc_info=True)
        sys.exit(1)