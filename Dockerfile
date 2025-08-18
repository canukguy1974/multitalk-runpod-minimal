# Dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# base
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ffmpeg libsndfile1 python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --upgrade pip

# app code
WORKDIR /
RUN git clone --depth 1 https://github.com/MeiGen-AI/MultiTalk.git /MultiTalk

# Torch (CUDA 12.1) — pin matching versions
RUN pip install --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1

# xformers built for the same torch (works with 2.3.x)
RUN pip install -U xformers==0.0.28 --index-url https://download.pytorch.org/whl/cu121

# Prevent requirements.txt from re-installing torch/vision/audio (common cause of mismatch)
RUN sed -i 's/^\s*torch[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchvision[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchaudio[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt
# OPTIONAL (faster attention; comment in if you want)
#RUN pip install flash_attn==2.7.4.post1 --no-build-isolation

# python deps
RUN pip install --no-cache-dir --no-deps -r /MultiTalk/requirements.txt || true
RUN pip install --no-cache-dir runpod requests boto3 soundfile librosa numpy scipy pillow tqdm opencv-python-headless

# (optional) cache locations for HF to speed re-runs
ENV HUGGINGFACE_HUB_CACHE=/workspace/.cache/huggingface
ENV HF_HOME=/workspace/.cache/huggingface
ENV TRANSFORMERS_CACHE=/workspace/.cache/huggingface

WORKDIR /workspace
COPY rp_handler.py /workspace/rp_handler.py

CMD ["python3", "-u", "/workspace/rp_handler.py"]
