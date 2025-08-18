import os, json, subprocess
from urllib.parse import urlparse
import requests
import runpod

TMP = "/tmp"

def _fetch(url: str, name_hint: str) -> str:
    """Download URL to /tmp and return local path."""
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
    inp = event.get("input", {})

    # --- image_path: allow URL or local path
    image_path = inp.get("image_path")
    if isinstance(image_path, str) and image_path.startswith(("http://", "https://")):
        image_path = _fetch(image_path, "image")

    # --- audio_paths -> cond_audio with local paths
    cond_audio = {}
    for k, v in (inp.get("audio_paths") or {}).items():
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            cond_audio[k] = _fetch(v, f"audio_{k}")
        else:
            cond_audio[k] = v

    args = {
        "prompt": inp.get("prompt", ""),
        "image_path": image_path,
        "cond_audio": cond_audio,                # what generate_multitalk.py expects
        "audio_type": inp.get("audio_type", "speech"),
        "sample_text_guide_scale": float(inp.get("sample_text_guide_scale", 1.0)),
        "sample_audio_guide_scale": float(inp.get("sample_audio_guide_scale", 2.0)),
        "sample_steps": int(inp.get("sample_steps", 8)),
        "mode": inp.get("mode", "streaming"),
    }

    # Call MultiTalk's script (reads JSON from stdin, prints JSON to stdout)
    proc = subprocess.run(
        ["python3", "/MultiTalk/generate_multitalk.py"],
        input=json.dumps(args).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if proc.returncode != 0:
        return {
            "error": "generate_multitalk.py 스크립트 실행 실패",
            "stdout": proc.stdout.decode(errors="ignore"),
            "stderr": proc.stderr.decode(errors="ignore"),
        }

    # Worker returns JSON with video_base64
    try:
        return json.loads(proc.stdout.decode())
    except Exception:
        return {"video_base64": None, "raw_stdout": proc.stdout.decode(errors="ignore")}

runpod.serverless.start({"handler": handler})
