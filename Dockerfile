# Dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# base
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ffmpeg libsndfile1 python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --upgrade pip

# app code
WORKDIR /
RUN git clone --depth 1 https://github.com/MeiGen-AI/MultiTalk.git /MultiTalk

# torch + performance deps
RUN pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio
RUN pip install -U xformers==0.0.28 --index-url https://download.pytorch.org/whl/cu121
# OPTIONAL (faster attention; comment in if you want)
# RUN pip install flash_attn==2.7.4.post1 --no-build-isolation

# python deps
RUN pip install -r /MultiTalk/requirements.txt || true
RUN pip install --no-cache-dir runpod requests boto3 soundfile librosa numpy scipy pillow tqdm opencv-python-headless

# (optional) cache locations for HF to speed re-runs
ENV HUGGINGFACE_HUB_CACHE=/workspace/.cache/huggingface
ENV HF_HOME=/workspace/.cache/huggingface
ENV TRANSFORMERS_CACHE=/workspace/.cache/huggingface

WORKDIR /workspace
COPY rp_handler.py /workspace/rp_handler.py

CMD ["python3", "-u", "/workspace/rp_handler.py"]
