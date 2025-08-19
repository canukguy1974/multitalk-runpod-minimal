FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# OS deps (minimal, headless)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ffmpeg libsndfile1 python3 python3-pip python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Fresh pip
RUN python3 -m pip install --upgrade pip setuptools wheel

# Pull MultiTalk
WORKDIR /
RUN git clone --depth 1 https://github.com/MeiGen-AI/MultiTalk.git /MultiTalk

# Prevent MultiTalk's requirements from overwriting our pinned torch stack or pulling gradio
RUN sed -i 's/^\s*torch[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchvision[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchaudio[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i '/^gradio[[:space:]=<>]/ s/^/# not needed in serverless /' /MultiTalk/requirements.txt && \
    sed -i '/^optimum-quanto[[:space:]=<>]/ s/^/# not needed in serverless /' /MultiTalk/requirements.txt

# ---- Pinned Torch stack (CUDA 12.1) ----
# Use the matching cu121 wheels for torch/vision/audio 2.4.x
RUN pip install --index-url https://download.pytorch.org/whl/cu121 --extra-index-url https://pypi.org/simple \
    torch==2.4.1+cu121 torchvision==0.19.1+cu121 torchaudio==2.4.1+cu121

# xformers for this stack (has prebuilt cu121 wheel) + einops
RUN pip install --index-url https://download.pytorch.org/whl/cu121 xformers==0.0.28 && \
    pip install einops==0.8.0

# Rest of MultiTalk deps WITHOUT touching the torch stack
RUN pip install --no-cache-dir --no-deps -r /MultiTalk/requirements.txt || true

# Runtime deps used by the handler
RUN pip install --no-cache-dir runpod requests soundfile librosa numpy scipy pillow tqdm opencv-python-headless

# Build-time sanity checks (fail fast if kernels/ops missing)
RUN python3 - <<'PY'
import torch, torchvision, xformers, einops
print("Torch:", torch.__version__, "CUDA:", torch.version.cuda, "CUDA avail:", torch.cuda.is_available())
print("TorchVision:", torchvision.__version__)
from torchvision.ops import nms
import xformers.ops as xo
print("torchvision.ops.nms OK; xformers.ops OK; einops", einops.__version__)
PY

# Worker
WORKDIR /workspace
COPY rp_handler.py /workspace/rp_handler.py
CMD ["python3", "-u", "/workspace/rp_handler.py"]
