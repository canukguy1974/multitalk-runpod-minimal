# Dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Quiet the "pip as root" warning during build (optional)
ENV PIP_ROOT_USER_ACTION=ignore

# System deps
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ffmpeg libsndfile1 python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --upgrade pip

# Pull MultiTalk
WORKDIR /
RUN git clone --depth 1 https://github.com/MeiGen-AI/MultiTalk.git /MultiTalk

# --- Torch stack (CUDA 12.1) pinned and protected ---

# 0) Prevent requirements.txt from touching torch/vision/audio (and remove UI extras we don't need)
RUN sed -i 's/^\s*torch[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchvision[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchaudio[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i '/^gradio[[:space:]=<>]/ s/^/# not needed in serverless /' /MultiTalk/requirements.txt && \
    sed -i '/^optimum-quanto[[:space:]=<>]/ s/^/# not needed in serverless /' /MultiTalk/requirements.txt

# 1) Remove any preinstalled torch wheels (just in case)
RUN pip uninstall -y torch torchvision torchaudio || true

# 2) Install matching cu121 wheels (these versions work together)
RUN pip install --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1

# 3) xformers built for the same stack
RUN pip install -U xformers==0.0.28 --index-url https://download.pytorch.org/whl/cu121

# 4) Install the rest of MultiTalk deps WITHOUT deps (so torch stack stays intact)
RUN pip install --no-cache-dir --no-deps -r /MultiTalk/requirements.txt || true

# 4.1) Minimal runtime deps some libs expect (keeps warnings away; safe, small)
RUN pip install --no-cache-dir \
    "huggingface-hub>=0.34.0,<1.0" \
    "safetensors>=0.4.3" \
    "regex!=2019.12.17" \
    "tifffile>=2022.8.12" \
    "future>=0.16.0"

# 4.2) MultiTalk needs einops
RUN pip install --no-cache-dir einops==0.8.0

# Worker libs
RUN pip install --no-cache-dir runpod requests boto3 soundfile librosa numpy scipy pillow tqdm opencv-python-headless

# Optional: cache locations for HF to speed subsequent runs
ENV HF_HOME=/workspace/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/workspace/.cache/huggingface \
    TRANSFORMERS_CACHE=/workspace/.cache/huggingface

# 5) Build-time sanity check — fail the build if torchvision ops (nms) are missing
RUN python3 - <<'PY'
import torch, torchvision
import einops
print("Torch:", torch.__version__, "| CUDA:", torch.version.cuda, "| CUDA avail:", torch.cuda.is_available())
print("TorchVision:", torchvision.__version__)
from torchvision.ops import nms
print("torchvision.ops.nms OK")
print("einops:", einops.__version__)
PY

# Runtime
WORKDIR /workspace
COPY rp_handler.py /workspace/rp_handler.py
CMD ["python3", "-u", "/workspace/rp_handler.py"]
