# 使用NVIDIA CUDA基础镜像
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# 克隆ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# 安装Python依赖
WORKDIR /app/ComfyUI
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
RUN pip3 install -r requirements.txt
RUN pip3 install flask pyyaml requests  # 合并安装额外依赖

# 复制服务器代码
COPY server.py /app/
COPY startup.sh /app/

# 设置权限
RUN chmod +x /app/startup.sh

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all

# 清理pip缓存
RUN pip3 cache purge && \
    rm -rf /root/.cache/pip/*

# 暴露端口
EXPOSE 9000

# 设置启动命令
CMD ["/app/startup.sh"]