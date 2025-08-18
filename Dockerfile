# Minimal CUDA runtime; RunPod GPUs are compatible with this base
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# --- system deps ---
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ffmpeg libsndfile1 python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*

# Python up-to-date
RUN python3 -m pip install --upgrade pip

# --- clone MultiTalk (brings in generate_multitalk.py) ---
WORKDIR /
RUN git clone --depth 1 https://github.com/MeiGen-AI/MultiTalk.git /MultiTalk

# --- Python deps ---
# 1) Torch with CUDA
RUN pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio
# 2) MultiTalk requirements (allow best-effort in case of extras)
RUN pip install -r /MultiTalk/requirements.txt || true
# 3) Worker deps
RUN pip install --no-cache-dir runpod requests soundfile librosa numpy scipy pillow tqdm \
    opencv-python-headless

# --- our handler ---
WORKDIR /workspace
COPY rp_handler.py /workspace/rp_handler.py

# RunPod looks for a Python process that calls runpod.serverless.start(...)
CMD ["python3", "-u", "/workspace/rp_handler.py"]
