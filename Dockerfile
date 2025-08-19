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

# 0) Make sure MultiTalk requirements cannot override torch stack (and drop UI extras)
RUN sed -i 's/^\s*torch[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchvision[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i 's/^\s*torchaudio[^#]*/# pinned in Dockerfile/g' /MultiTalk/requirements.txt && \
    sed -i '/^gradio[[:space:]=<>]/ s/^/# not needed in serverless /' /MultiTalk/requirements.txt && \
    sed -i '/^optimum-quanto[[:space:]=<>]/ s/^/# not needed in serverless /' /MultiTalk/requirements.txt

# 1) Clean any preinstalled torch wheels
RUN pip uninstall -y torch torchvision torchaudio || true

# 2) Install matching CUDA 12.1 wheels (explicit +cu121 tags)
RUN pip install --upgrade pip setuptools wheel && \
    pip install --index-url https://download.pytorch.org/whl/cu121 --extra-index-url https://pypi.org/simple \
        torch==2.3.1+cu121 torchvision==0.18.1+cu121 torchaudio==2.3.1+cu121

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

# 5) Build-time sanity check — prints detailed traceback if ops are missing
RUN python3 - <<'PY'
import sys, traceback
try:
    import torch, torchvision, einops
    print("Torch:", torch.__version__, "| CUDA:", torch.version.cuda, "| CUDA avail:", torch.cuda.is_available())
    print("TorchVision:", torchvision.__version__)
    # This will raise if the compiled ops aren't present
    from torchvision.ops import nms
    print("torchvision.ops.nms OK")
    print("einops:", einops.__version__)
except Exception as e:
    traceback.print_exc()
    sys.exit(1)
PY

# Runtime
WORKDIR /workspace
COPY rp_handler.py /workspace/rp_handler.py
CMD ["python3", "-u", "/workspace/rp_handler.py"]
