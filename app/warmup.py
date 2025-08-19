# /app/warmup.py
import os, time
from huggingface_hub import snapshot_download

WEIGHTS_DIR = os.environ.get("WEIGHTS_DIR","/workspace/weights")
HF_HOME = os.environ.get("HF_HOME","/workspace/hf_cache")
os.makedirs(WEIGHTS_DIR, exist_ok=True)
os.makedirs(HF_HOME, exist_ok=True)

# MultiTalk model names (choose 480P)
MODELS = {
  "multitalk_base": ("MeiGen-AI/Wan2.1-I2V-14B-480P", f"{WEIGHTS_DIR}/Wan2.1-I2V-14B-480P"),
  "wav2vec": ("jonatasgrosman/wav2vec2-large-xlsr-53-english", f"{WEIGHTS_DIR}/wav2vec2"),
}

def ensure_model(repo, local):
    if os.path.exists(local) and os.listdir(local):
        return
    snapshot_download(repo_id=repo, local_dir=local, local_dir_use_symlinks=False, resume_download=True)

try:
    for _, (repo, local) in MODELS.items():
        ensure_model(repo, local)
except Exception as e:
    print("Warmup: model pull skipped/failed:", e)

print("Warmup done; weights at", WEIGHTS_DIR)
