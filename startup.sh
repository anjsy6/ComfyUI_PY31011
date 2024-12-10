#!/bin/bash

# ComfyUI的主要目录结构
COMFY_ROOT="/app/ComfyUI"
NAS_ROOT="/mnt/nas/comfyui"

# 确保必要的目录存在
mkdir -p $NAS_ROOT/{models,configs,custom_nodes,embeddings,loras,vae,checkpoints,extensions,workflows}

# 模型相关目录映射
MODEL_DIRS=(
    "checkpoints"
    "embeddings"
    "loras"
    "vae"
    "models"
    "configs"
)

# 移动原始目录并创建软链接
for dir in "${MODEL_DIRS[@]}"; do
    # 如果ComfyUI目录存在，先备份
    if [ -d "$COMFY_ROOT/$dir" ]; then
        mv "$COMFY_ROOT/$dir" "$COMFY_ROOT/${dir}_original"
    fi
    # 创建从NAS到ComfyUI的软链接
    ln -sfn "$NAS_ROOT/$dir" "$COMFY_ROOT/$dir"
done

# 处理custom_nodes（插件）目录
if [ -d "$COMFY_ROOT/custom_nodes" ]; then
    mv "$COMFY_ROOT/custom_nodes" "$COMFY_ROOT/custom_nodes_original"
fi
ln -sfn "$NAS_ROOT/custom_nodes" "$COMFY_ROOT/custom_nodes"

# 处理扩展目录
if [ -d "$COMFY_ROOT/extensions" ]; then
    mv "$COMFY_ROOT/extensions" "$COMFY_ROOT/extensions_original"
fi
ln -sfn "$NAS_ROOT/extensions" "$COMFY_ROOT/extensions"

# 设置正确的权限
chown -R root:root $COMFY_ROOT
chmod -R 755 $COMFY_ROOT

# 安装NAS中的custom_nodes依赖
if [ -d "$NAS_ROOT/custom_nodes" ]; then
    echo "Installing custom nodes dependencies..."
    for nodedir in "$NAS_ROOT/custom_nodes"/*/ ; do
        if [ -f "$nodedir/requirements.txt" ]; then
            echo "Installing requirements for $(basename "$nodedir")"
            pip3 install -r "$nodedir/requirements.txt"
        fi
    done
fi

# 设置ComfyUI配置
cat > $COMFY_ROOT/extra_model_paths.yaml << EOF
checkpoints_path: $NAS_ROOT/checkpoints
config_path: $NAS_ROOT/configs
embeddings_path: $NAS_ROOT/embeddings
loras_path: $NAS_ROOT/loras
vae_path: $NAS_ROOT/vae
custom_nodes_path: $NAS_ROOT/custom_nodes
extensions_path: $NAS_ROOT/extensions
EOF

echo "NAS mount configuration completed"

# 启动Flask服务器
python3 /app/server.py