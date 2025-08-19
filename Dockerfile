# Dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# OS deps
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ffmpeg libsndfile1 python3 python3-pip python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Fresh pip
RUN python3 -m pip install --upgrade pip setuptools wheel

# ---------- Torch stack (cu121 pinned) ----------
RUN pip install --extra-index-url https://download.pytorch.org/whl/cu121 \
    torch==2.4.1+cu121 torchvision==0.19.1+cu121 torchaudio==2.4.1+cu121

# Memory/attn helpers
RUN pip install xformers==0.0.28 einops==0.8.0 \
    huggingface-hub==0.24.6 safetensors==0.4.3 regex==2024.7.24 \
    soundfile librosa pyloudnorm

# ---------- MultiTalk ----------
WORKDIR /
RUN git clone --depth 1 https://github.com/MeiGen-AI/MultiTalk.git /MultiTalk

# prevent torch wheels from requirements
RUN sed -i 's/^\s*torch[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchvision[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchaudio[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt

RUN pip install -r /MultiTalk/requirements.txt --no-deps

# ---------- SadTalker (optional fast engine) ----------
RUN git clone --depth 1 https://github.com/OpenTalker/SadTalker.git /SadTalker
WORKDIR /SadTalker
# lightweight deps; torch already installed
RUN pip install -r requirements.txt --no-deps || true

# ---------- Wav2Lip (fastest lipsync) ----------
WORKDIR /
RUN git clone --depth 1 https://github.com/Rudrabha/Wav2Lip.git /Wav2Lip
WORKDIR /Wav2Lip
RUN pip install opencv-python==4.9.0.80 ffmpeg-python==0.2.0 numba==0.59.1 --no-cache-dir

# Download Wav2Lip weights (small, ~150MB)
RUN curl -L -o /Wav2Lip/Wav2Lip.pth \
    https://github.com/anishhegeman/Wav2Lip-weights/releases/download/v1.0/Wav2Lip.pth

# ---------- ElevenLabs client ----------
RUN pip install elevenlabs==1.9.0

# ---------- App code ----------
WORKDIR /app
COPY rp_handler.py /app/rp_handler.py
COPY warmup.py /app/warmup.py
# Optional: include a small prebaked idle.mp4 (3 sec, 480p, 12fps)
COPY assets/idle_480_12fps.mp4 /app/assets/idle_480_12fps.mp4

# Caches/weights
ENV HF_HOME=/workspace/hf_cache
ENV WEIGHTS_DIR=/workspace/weights
ENV TORCH_ALLOW_TF32=1
ENV NVIDIA_TF32_OVERRIDE=1
ENV OMP_NUM_THREADS=1

# Pre-flight: verify core imports at build time
RUN python3 - <<'PY'
import torch, torchvision, torchaudio
from torchvision.ops import nms
import importlib
importlib.import_module("huggingface_hub")
print("Sanity OK")
PY

# Entrypoint (RunPod serverless expects a module-level handler(event))
CMD ["python3", "-c", "import warmup; import rp_handler; import runpod; runpod.serverless.start({'handler': rp_handler.handler})"]

WORKDIR /app
COPY app/ /app/
