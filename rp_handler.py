# /workspace/rp_handler.py
import os, json, base64, subprocess, traceback, time
from urllib.parse import urlparse
import requests

# Optional S3 upload of the output
S3_ENABLED = False
try:
    import boto3  # installed via Dockerfile
    S3_ENABLED = True
except Exception:
    S3_ENABLED = False

import runpod

SIG = "url2tmp-unified-v5"
TMP = "/tmp"

# env toggles
LOG_TAIL = int(os.getenv("LOG_TAIL_CHARS", "4000"))
DEFAULT_SIZE = os.getenv("MTALK_SIZE", "multitalk-480")
DEFAULT_STEPS = int(os.getenv("MTALK_STEPS", "8"))
DEFAULT_TEXT_GUIDE = float(os.getenv("MTALK_TEXT_GUIDE", "1.0"))
DEFAULT_AUDIO_GUIDE = float(os.getenv("MTALK_AUDIO_GUIDE", "2.0"))

def _ensure_tmp():
    os.makedirs(TMP, exist_ok=True)

def _tail(s: str, n: int = LOG_TAIL) -> str:
    if not s:
        return ""
    return s[-n:]

def _stat(p):
    try:
        s = os.stat(p)
        return {"exists": True, "size": s.st_size}
    except Exception as e:
        return {"exists": False, "err": str(e)}

def _fetch(url, name_hint, retries=3, timeout=120):
    _ensure_tmp()
    ext = os.path.splitext(urlparse(url).path)[1] or ""
    path = os.path.join(TMP, f"{name_hint}{ext}")
    last_err = None
    for i in range(retries):
        try:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1024 * 64):
                        if chunk:
                            f.write(chunk)
            return path
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"download failed for {url}: {last_err}")

def _write_b64(data_b64, name_hint, default_ext):
    _ensure_tmp()
    ext = default_ext if default_ext.startswith(".") else f".{default_ext}"
    path = os.path.join(TMP, f"{name_hint}{ext}")
    with open(path, "wb") as f:
        f.write(base64.b64decode(data_b64))
    return path

def _normalize_inputs(inp):
    """
    Accepts any of:
      - image_path (url/local), cond_image (url/local), image_base64
      - audio_paths {key: url/local}, cond_audio {key: url/local}, audio_base64 (string) or audio_base64s {key: b64}
    Returns local paths.
    """
    # Image
    img = inp.get("image_path") or inp.get("cond_image")
    if isinstance(img, str) and img.startswith(("http://", "https://")):
        img = _fetch(img, "image")
    elif not img and inp.get("image_base64"):
        img = _write_b64(inp["image_base64"], "image", ".png")
    # else: img could already be a local filesystem path

    # Audio dict
    cond_audio = {}
    # precedence: audio_paths > cond_audio
    ap = inp.get("audio_paths") or inp.get("cond_audio") or {}
    if isinstance(ap, dict):
        for k, v in ap.items():
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                cond_audio[k] = _fetch(v, f"audio_{k}")
            else:
                cond_audio[k] = v  # assume local path
    # single base64 field (or dict of base64s)
    if not cond_audio:
        if "audio_base64s" in inp and isinstance(inp["audio_base64s"], dict):
            for k, b64 in inp["audio_base64s"].items():
                cond_audio[k] = _write_b64(b64, f"audio_{k}", ".wav")
        elif "audio_base64" in inp:
            cond_audio["person1"] = _write_b64(inp["audio_base64"], "audio_person1", ".wav")

    return img, cond_audio

def _build_input_json(inp, img_local, cond_audio_local):
    return {
        "prompt": inp.get("prompt", ""),
        "cond_image": img_local,
        "cond_audio": cond_audio_local,
        "audio_type": inp.get("audio_type", "speech"),
        "mode": inp.get("mode", "streaming")
    }

def _call_multitalk_cli(inp, ij_path):
    save = os.path.join(TMP, "out")
    cmd = [
        "python3", "/MultiTalk/generate_multitalk.py",
        "--input_json", ij_path,
        "--mode", str(inp.get("mode", "streaming")),
        "--sample_steps", str(int(inp.get("sample_steps", DEFAULT_STEPS))),
        "--sample_text_guide_scale", str(float(inp.get("sample_text_guide_scale", DEFAULT_TEXT_GUIDE))),
        "--sample_audio_guide_scale", str(float(inp.get("sample_audio_guide_scale", DEFAULT_AUDIO_GUIDE))),
        "--size", str(inp.get("size", DEFAULT_SIZE)),
        "--save_file", save
    ]
    # optional overrides
    if inp.get("ckpt_dir"):
        cmd += ["--ckpt_dir", str(inp["ckpt_dir"])]
    if inp.get("wav2vec_dir"):
        cmd += ["--wav2vec_dir", str(inp["wav2vec_dir"])]
    if inp.get("num_persistent_param_in_dit") is not None:
        cmd += ["--num_persistent_param_in_dit", str(int(inp["num_persistent_param_in_dit"]))]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc, save + ".mp4", cmd

def _call_multitalk_stdin(inp, img_local, cond_audio_local):
    """Fallback path if --input_json is not supported in your checkout."""
    args = {
        "prompt": inp.get("prompt", ""),
        "image_path": img_local,
        "cond_audio": cond_audio_local,
        "audio_type": inp.get("audio_type", "speech"),
        "sample_text_guide_scale": float(inp.get("sample_text_guide_scale", DEFAULT_TEXT_GUIDE)),
        "sample_audio_guide_scale": float(inp.get("sample_audio_guide_scale", DEFAULT_AUDIO_GUIDE)),
        "sample_steps": int(inp.get("sample_steps", DEFAULT_STEPS)),
        "mode": inp.get("mode", "streaming"),
        "size": inp.get("size", DEFAULT_SIZE),
    }
    proc = subprocess.run(
        ["python3", "/MultiTalk/generate_multitalk.py"],
        input=json.dumps(args).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return proc

def _maybe_upload_s3(local_path):
    if not S3_ENABLED:
        return None
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        return None
    key_prefix = os.getenv("S3_PREFIX", "multitalk")
    key = f"{key_prefix}/out_{int(time.time())}.mp4"
    try:
        s3 = boto3.client("s3",
            region_name=os.getenv("AWS_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        s3.upload_file(local_path, bucket, key, ExtraArgs={"ContentType": "video/mp4", "ACL": "private"})
        # presign read URL (10 min)
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=int(os.getenv("S3_URL_TTL", "600"))
        )
        return url
    except Exception:
        return None

def handler(event):
    print(f"HANDLER_SIGNATURE: {SIG}", flush=True)
    try:
        inp = event.get("input", {}) or {}

        # Normalize inputs (URL/base64/local)
        img, cond_audio = _normalize_inputs(inp)

        # Basic validation
        if not img:
            return {"error": "missing image (image_path/cond_image/image_base64)"}
        if not cond_audio:
            return {"error": "missing audio (audio_paths/cond_audio/audio_base64)"}

        # Build input.json and call MultiTalk (CLI first)
        _ensure_tmp()
        ij = os.path.join(TMP, "input.json")
        with open(ij, "w", encoding="utf-8") as f:
            json.dump(_build_input_json(inp, img, cond_audio), f)

        proc, mp4_path, cmd = _call_multitalk_cli(inp, ij)

        # CLI failed? try STDIN mode once.
        if proc.returncode != 0 and "unrecognized arguments" in (proc.stderr or ""):
            proc = _call_multitalk_stdin(inp, img, cond_audio)
            mp4_path = os.path.join(TMP, "out.mp4")  # some forks save here

        if proc.returncode != 0:
            return {
                "error": "generate_multitalk.py failed",
                "stdout_tail": _tail(proc.stdout),
                "stderr_tail": _tail(proc.stderr),
                "paths": {
                    "cond_image": {"path": img, **_stat(img)},
                    **{f"cond_audio.{k}": {"path": v, **_stat(v)} for k, v in cond_audio.items()},
                    "out_mp4": {"path": mp4_path, **_stat(mp4_path)}
                },
                "cmd": cmd if isinstance(cmd, list) else None
            }

        if not os.path.exists(mp4_path):
            # Sometimes the script prints JSON with video_base64 on stdout; try parse
            try:
                payload = json.loads(proc.stdout)
                if "video_base64" in payload:
                    return payload
            except Exception:
                pass
            return {
                "error": "no mp4 output found",
                "stdout_tail": _tail(proc.stdout),
                "stderr_tail": _tail(proc.stderr),
                "paths": {
                    "cond_image": {"path": img, **_stat(img)},
                    **{f"cond_audio.{k}": {"path": v, **_stat(v)} for k, v in cond_audio.items()},
                    "out_mp4": {"path": mp4_path, **_stat(mp4_path)}
                }
            }

        # Success → return base64, plus optional S3 URL
        with open(mp4_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        out = {"video_base64": b64, "video_size_bytes": os.path.getsize(mp4_path)}
        s3_url = _maybe_upload_s3(mp4_path)
        if s3_url:
            out["video_s3_url"] = s3_url
        return out

    except Exception:
        return {"error": "handler exception", "traceback": traceback.format_exc()}

runpod.serverless.start({"handler": handler})
