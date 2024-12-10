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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

COMFY_ROOT = "/app/ComfyUI"
NAS_ROOT = "/mnt/nas/comfyui"
COMFY_PORT = "8188"
comfy_process = None

def verify_nas_structure():
    """验证NAS目录结构并确保必要的目录存在"""
    logger.info("Verifying NAS directory structure...")
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
    
    for dir_name in required_dirs:
        dir_path = os.path.join(NAS_ROOT, dir_name)
        if not os.path.exists(dir_path):
            logger.info(f"Creating directory: {dir_path}")
            os.makedirs(dir_path, exist_ok=True)
    logger.info("NAS directory structure verification completed")

def start_comfyui():
    """启动ComfyUI进程"""
    global comfy_process
    if comfy_process is None:
        logger.info("Starting ComfyUI process...")
        
        # 确保NAS目录结构正确
        verify_nas_structure()
        
        # 启动ComfyUI，指定额外的配置路径
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
        logger.info(f"Executing command: {' '.join(cmd)}")
        
        comfy_process = subprocess.Popen(
            cmd,
            cwd=COMFY_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待ComfyUI启动
        logger.info("Waiting for ComfyUI to start...")
        time.sleep(5)
        
        if comfy_process.poll() is None:
            logger.info("ComfyUI process started successfully")
        else:
            logger.error("Failed to start ComfyUI process")
            stdout, stderr = comfy_process.communicate()
            logger.error(f"stdout: {stdout.decode() if stdout else 'None'}")
            logger.error(f"stderr: {stderr.decode() if stderr else 'None'}")

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    logger.info("Performing health check...")
    try:
        # 检查NAS挂载状态
        nas_mounted = os.path.ismount(NAS_ROOT)
        logger.info(f"NAS mount status: {nas_mounted}")
        
        if not nas_mounted:
            logger.error(f"NAS not mounted at {NAS_ROOT}")
            return jsonify({
                "status": "error",
                "message": "NAS not mounted"
            }), 500
        
        # 检查ComfyUI进程状态
        comfy_running = comfy_process and comfy_process.poll() is None
        logger.info(f"ComfyUI process status: {'running' if comfy_running else 'not running'}")
        
        if comfy_running:
            return jsonify({
                "status": "healthy",
                "nas_mounted": True,
                "comfyui_running": True
            }), 200
        else:
            return jsonify({
                "status": "warning",
                "message": "ComfyUI not running",
                "nas_mounted": True
            }), 200
            
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/workflow', methods=['POST'])
def handle_workflow():
    """处理工作流请求"""
    logger.info("Handling workflow request...")
    try:
        workflow_data = request.json
        logger.info("Received workflow data")
        
        # 确保ComfyUI运行
        if comfy_process is None or comfy_process.poll() is not None:
            logger.info("ComfyUI not running, starting it...")
            start_comfyui()
        
        # 保存工作流到NAS
        workflow_path = os.path.join(NAS_ROOT, 'workflows', f'workflow_{time.time()}.json')
        logger.info(f"Saving workflow to: {workflow_path}")
        with open(workflow_path, 'w') as f:
            json.dump(workflow_data, f)
        
        # TODO: 实现与ComfyUI API的交互
        # 这里需要添加具体的工作流处理逻辑
        
        logger.info("Workflow processed successfully")
        return jsonify({
            "status": "success",
            "message": "Workflow received and processed",
            "workflow_saved": workflow_path
        }), 200
        
    except Exception as e:
        logger.error(f"Error handling workflow: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/nas/status', methods=['GET'])
def nas_status():
    """检查NAS存储状态"""
    logger.info("Checking NAS status...")
    try:
        nas_info = {
            "mounted": os.path.ismount(NAS_ROOT),
            "directories": {}
        }
        
        if nas_info["mounted"]:
            for dir_name in ['models', 'custom_nodes', 'extensions']:
                dir_path = os.path.join(NAS_ROOT, dir_name)
                exists = os.path.exists(dir_path)
                items = len(os.listdir(dir_path)) if exists else 0
                logger.info(f"Directory {dir_name}: exists={exists}, items={items}")
                nas_info["directories"][dir_name] = {
                    "exists": exists,
                    "items": items
                }
        
        logger.info("NAS status check completed")
        return jsonify(nas_info), 200
    except Exception as e:
        logger.error(f"Error checking NAS status: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """处理所有到 ComfyUI 的请求"""
    logger.info(f"Handling request for path: {path}")
    try:
        if comfy_process is None or comfy_process.poll() is not None:
            logger.info("ComfyUI not running, starting it...")
            start_comfyui()

        url = f'http://127.0.0.1:{COMFY_PORT}/{path}'
        logger.info(f"Proxying request to: {url}")
        
        # 转发请求到 ComfyUI
        resp = requests.request(
            method=request.method,
            url=url,
            headers={key: value for key, value in request.headers if key != 'Host'},
            data=request.get_data(),
            params=request.args,
            allow_redirects=False
        )

        logger.info(f"Received response from ComfyUI with status code: {resp.status_code}")

        # 转发响应
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for name, value in resp.raw.headers.items()
                  if name.lower() not in excluded_headers]

        return Response(resp.content, resp.status_code, headers)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error proxying request: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting application...")
    logger.info("Initializing ComfyUI...")
    start_comfyui()
    logger.info("Starting Flask server on port 9000")
    app.run(host='0.0.0.0', port=9000)