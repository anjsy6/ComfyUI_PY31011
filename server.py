from flask import Flask, request, jsonify
import sys
import os
import json
import subprocess
import threading
import time
import shutil
import yaml

app = Flask(__name__)

COMFY_ROOT = "/app/ComfyUI"
NAS_ROOT = "/mnt/nas/comfyui"
comfy_process = None

def verify_nas_structure():
    """验证NAS目录结构并确保必要的目录存在"""
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
            os.makedirs(dir_path, exist_ok=True)
            print(f"Created directory: {dir_path}")

def start_comfyui():
    """启动ComfyUI进程"""
    global comfy_process
    if comfy_process is None:
        # 确保NAS目录结构正确
        verify_nas_structure()
        
        # 启动ComfyUI，指定额外的配置路径
        comfy_process = subprocess.Popen(
            [
                "python3", 
                "main.py", 
                "--listen", 
                "0.0.0.0", 
                "--port", 
                "8188",
                "--extra-model-paths-config", 
                "extra_model_paths.yaml"
            ],
            cwd=COMFY_ROOT
        )

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    try:
        # 检查NAS挂载状态
        if not os.path.ismount(NAS_ROOT):
            return jsonify({
                "status": "error",
                "message": "NAS not mounted"
            }), 500
        
        # 检查ComfyUI进程状态
        if comfy_process and comfy_process.poll() is None:
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
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/workflow', methods=['POST'])
def handle_workflow():
    """处理工作流请求"""
    try:
        workflow_data = request.json
        
        # 确保ComfyUI运行
        if comfy_process is None or comfy_process.poll() is not None:
            start_comfyui()
        
        # 保存工作流到NAS
        workflow_path = os.path.join(NAS_ROOT, 'workflows', f'workflow_{time.time()}.json')
        with open(workflow_path, 'w') as f:
            json.dump(workflow_data, f)
        
        # TODO: 实现与ComfyUI API的交互
        # 这里需要添加具体的工作流处理逻辑
        
        return jsonify({
            "status": "success",
            "message": "Workflow received and processed",
            "workflow_saved": workflow_path
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/nas/status', methods=['GET'])
def nas_status():
    """检查NAS存储状态"""
    try:
        nas_info = {
            "mounted": os.path.ismount(NAS_ROOT),
            "directories": {}
        }
        
        if nas_info["mounted"]:
            for dir_name in ['models', 'custom_nodes', 'extensions']:
                dir_path = os.path.join(NAS_ROOT, dir_name)
                nas_info["directories"][dir_name] = {
                    "exists": os.path.exists(dir_path),
                    "items": len(os.listdir(dir_path)) if os.path.exists(dir_path) else 0
                }
        
        return jsonify(nas_info), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # 启动ComfyUI
    start_comfyui()
    # 启动Flask服务器
    app.run(host='0.0.0.0', port=9000)