#!/bin/bash

# 设置日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /tmp/comfyui_startup.log
}

# ComfyUI的主要目录结构
COMFY_ROOT="/app/ComfyUI"
NAS_ROOT="/mnt/nas/comfyui"
BACKUP_ROOT="/app/ComfyUI_backup"

log "开始初始化环境..."

# 首先备份ComfyUI原始文件
log "备份ComfyUI原始文件..."
if [ ! -d "$BACKUP_ROOT" ]; then
    for dir in checkpoints embeddings loras vae models configs custom_nodes extensions; do
        if [ -d "$COMFY_ROOT/$dir" ]; then
            log "备份目录: $dir"
            mkdir -p "$BACKUP_ROOT/$dir"
            cp -r "$COMFY_ROOT/$dir"/* "$BACKUP_ROOT/$dir"/ 2>/dev/null || true
        fi
    done
fi

# 确保NAS目录结构存在
mkdir -p $NAS_ROOT/{models,configs,custom_nodes,embeddings,loras,vae,checkpoints,extensions,workflows}

# 模型相关目录映射
MODEL_DIRS=(
    "checkpoints"
    "embeddings"
    "loras"
    "vae"
    "models"
    "configs"
    "custom_nodes"
    "extensions"
)

# 同步默认文件到NAS（如果NAS目录为空）
log "检查并同步默认文件到NAS..."
for dir in "${MODEL_DIRS[@]}"; do
    nas_dir="$NAS_ROOT/$dir"
    backup_dir="$BACKUP_ROOT/$dir"
    
    # 如果NAS目录为空且存在备份文件，则复制备份文件到NAS
    if [ -d "$backup_dir" ] && [ ! "$(ls -A $nas_dir 2>/dev/null)" ]; then
        log "同步默认文件到NAS目录: $dir"
        cp -r "$backup_dir"/* "$nas_dir"/ 2>/dev/null || true
    fi
done

# 确保ComfyUI原始目录存在
for dir in "${MODEL_DIRS[@]}"; do
    comfy_dir="$COMFY_ROOT/$dir"
    if [ ! -d "$comfy_dir" ]; then
        log "创建ComfyUI原始目录: $dir"
        mkdir -p "$comfy_dir"
    fi
done

# 设置权限
chmod -R 755 $COMFY_ROOT || log "权限设置失败，但继续执行"
chmod -R 755 $NAS_ROOT || log "NAS权限设置失败，但继续执行"

# 安装NAS中的custom_nodes依赖
if [ -d "$NAS_ROOT/custom_nodes" ]; then
    log "开始安装NAS中的custom_nodes依赖..."
    for nodedir in "$NAS_ROOT/custom_nodes"/*/ ; do
        if [ -f "$nodedir/requirements.txt" ]; then
            log "正在安装依赖: $(basename "$nodedir")"
            pip3 install -r "$nodedir/requirements.txt" || log "安装依赖失败: $(basename "$nodedir")"
        fi
    done
fi

# 创建配置文件，优先使用原始路径，然后是NAS路径
log "创建ComfyUI配置文件..."
cat > $COMFY_ROOT/extra_model_paths.yaml << EOF
checkpoints_path:
  - $COMFY_ROOT/checkpoints
  - $NAS_ROOT/checkpoints
config_path:
  - $COMFY_ROOT/configs
  - $NAS_ROOT/configs
embeddings_path:
  - $COMFY_ROOT/embeddings
  - $NAS_ROOT/embeddings
loras_path:
  - $COMFY_ROOT/loras
  - $NAS_ROOT/loras
vae_path:
  - $COMFY_ROOT/vae
  - $NAS_ROOT/vae
custom_nodes_path:
  - $COMFY_ROOT/custom_nodes
  - $NAS_ROOT/custom_nodes
extensions_path:
  - $COMFY_ROOT/extensions
  - $NAS_ROOT/extensions
EOF

log "配置文件内容："
cat $COMFY_ROOT/extra_model_paths.yaml

log "目录结构："
tree $COMFY_ROOT || ls -R $COMFY_ROOT
log "NAS目录结构："
tree $NAS_ROOT || ls -R $NAS_ROOT

log "配置完成，准备启动服务..."

# 启动Flask服务器
exec python3 /app/server.py 2>&1 | tee -a /tmp/comfyui_startup.log