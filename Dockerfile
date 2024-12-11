# 使用NVIDIA CUDA基础镜像
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    tree \
    && rm -rf /var/lib/apt/lists/*

# 创建非root用户
RUN useradd -m -u 1000 fcuser

# 克隆ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# 安装Python依赖
WORKDIR /app/ComfyUI
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
RUN pip3 install -r requirements.txt
RUN pip3 install flask pyyaml requests

# 备份ComfyUI原始文件
RUN mkdir -p /app/ComfyUI_backup && \
    cp -r /app/ComfyUI/* /app/ComfyUI_backup/

# 复制服务器代码
COPY server.py /app/
COPY startup.sh /app/

# 设置权限
RUN chmod +x /app/startup.sh && \
    chown -R fcuser:fcuser /app && \
    chmod -R 755 /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV HOME=/app

# 切换到非root用户
USER fcuser

# 暴露端口
EXPOSE 9000

# 设置启动命令
ENTRYPOINT ["/app/startup.sh"]