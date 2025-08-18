print("HANDLER_SIGNATURE: url2tmp-inputjson-v2", flush=True)
# /workspace/rp_handler.py
import os, json, base64, subprocess
from urllib.parse import urlparse
import requests

try:
    import runpod
except ImportError as e:
    raise ImportError("Missing 'runpod' package. Add `pip install runpod` in Dockerfile.") from e

TMP = "/tmp"

def _fetch(url, name_hint):
    os.makedirs(TMP, exist_ok=True)
    ext = os.path.splitext(urlparse(url).path)[1] or ""
    path = os.path.join(TMP, f"{name_hint}{ext}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
    return path

def handler(event):
    print("HANDLER_SIGNATURE: url2tmp-inputjson-v2", flush=True)

    inp = event.get("input", {}) or {}

    # 1) download to /tmp
    img = inp.get("image_path")
    if isinstance(img, str) and img.startswith(("http://", "https://")):
        img = _fetch(img, "image")

    cond_audio = {}
    for k, v in (inp.get("audio_paths") or {}).items():
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            cond_audio[k] = _fetch(v, f"audio_{k}")
        else:
            cond_audio[k] = v

    # 2) write the JSON MultiTalk expects
    input_json = {
        "prompt": inp.get("prompt", ""),
        "cond_image": img,                  # <- local image path in /tmp
        "cond_audio": cond_audio,           # <- {"person1": "/tmp/audio_person1.wav"}
        "audio_type": inp.get("audio_type", "speech"),
        "mode": inp.get("mode", "streaming")
    }
    input_json_path = os.path.join(TMP, "input.json")
    with open(input_json_path, "w", encoding="utf-8") as f:
        json.dump(input_json, f)

    # 3) call generate_multitalk.py with CLI flags and a save target
    save_basename = os.path.join(TMP, "out")  # /tmp/out.mp4
    cmd = [
        "python3", "/MultiTalk/generate_multitalk.py",
        "--input_json", input_json_path,
        "--mode", str(inp.get("mode", "streaming")),
        "--sample_steps", str(int(inp.get("sample_steps", 8))),
        "--sample_text_guide_scale", str(float(inp.get("sample_text_guide_scale", 1.0))),
        "--sample_audio_guide_scale", str(float(inp.get("sample_audio_guide_scale", 2.0))),
        "--size", str(inp.get("size", "multitalk-480")),
        "--save_file", save_basename
    ]

    # optional power-user overrides
    if inp.get("ckpt_dir"):
        cmd += ["--ckpt_dir", str(inp["ckpt_dir"])]
    if inp.get("wav2vec_dir"):
        cmd += ["--wav2vec_dir", str(inp["wav2vec_dir"])]
    if inp.get("num_persistent_param_in_dit") is not None:
        cmd += ["--num_persistent_param_in_dit", str(int(inp["num_persistent_param_in_dit"]))]

    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True
    )

    if proc.returncode != 0:
        return {
            "error": "generate_multitalk.py failed",
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:]
        }

    mp4_path = save_basename + ".mp4"
    if not os.path.exists(mp4_path):
        return {
            "video_base64": None,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:]
        }

    with open(mp4_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return {"video_base64": b64}

runpod.serverless.start({"handler": handler})
