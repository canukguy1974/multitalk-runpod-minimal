# /workspace/rp_handler.py
import os, json, base64, subprocess, traceback
from urllib.parse import urlparse
import requests
import runpod

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
    try:
        inp = event.get("input", {}) or {}

        # download to /tmp
        img = inp.get("image_path")
        if isinstance(img, str) and img.startswith(("http://","https://")):
            img = _fetch(img, "image")

        cond_audio = {}
        for k, v in (inp.get("audio_paths") or {}).items():
            if isinstance(v, str) and v.startswith(("http://","https://")):
                cond_audio[k] = _fetch(v, f"audio_{k}")
            else:
                cond_audio[k] = v

        # build input_json for MultiTalk
        input_json = {
            "prompt": inp.get("prompt",""),
            "cond_image": img,
            "cond_audio": cond_audio,
            "audio_type": inp.get("audio_type","speech"),
            "mode": inp.get("mode","streaming")
        }
        ij = os.path.join(TMP, "input.json")
        with open(ij, "w", encoding="utf-8") as f:
            json.dump(input_json, f)

        save = os.path.join(TMP, "out")
        cmd = [
            "python3", "/MultiTalk/generate_multitalk.py",
            "--input_json", ij,
            "--mode", str(inp.get("mode","streaming")),
            "--sample_steps", str(int(inp.get("sample_steps",8))),
            "--sample_text_guide_scale", str(float(inp.get("sample_text_guide_scale",1.0))),
            "--sample_audio_guide_scale", str(float(inp.get("sample_audio_guide_scale",2.0))),
            "--size", str(inp.get("size","multitalk-480")),
            "--save_file", save
        ]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        mp4 = save + ".mp4"

        if proc.returncode != 0:
            return {
                "error": "generate_multitalk.py failed",
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
                "paths": {
                    "cond_image": {"path": img, "exists": os.path.exists(img) if img else False},
                    "cond_audio.person1": {
                        "path": cond_audio.get("person1"),
                        "exists": os.path.exists(cond_audio.get("person1",""))
                    },
                    "out_mp4": {"path": mp4, "exists": os.path.exists(mp4)}
                }
            }

        if not os.path.exists(mp4):
            return {
                "error": "no mp4 output",
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:]
            }

        with open(mp4, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return {"video_base64": b64}

    except Exception:
        return {"error": "handler exception", "traceback": traceback.format_exc()}

runpod.serverless.start({"handler": handler})
