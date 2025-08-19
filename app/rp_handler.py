# /app/rp_handler.py
import os, json, base64, subprocess, traceback
from pathlib import Path
import runpod

EL_KEY = os.getenv("ELEVENLABS_API_KEY", "")

def b64_of(fp): return base64.b64encode(Path(fp).read_bytes()).decode("utf-8")

def ensure_local_media(val, kind):
    # val can be url or base64
    out = f"/tmp/{'img' if kind=='image' else 'aud'}.{ 'png' if kind=='image' else 'wav'}"
    if isinstance(val, str) and val.startswith("http"):
        subprocess.run(["curl","-L","-o",out,val], check=True)
    else:
        # assume base64
        Path(out).write_bytes(base64.b64decode(val.split(",")[-1]))
    return out

def ffmpeg_norm_wav(in_path, out_path, max_sec=None, atempo=None, strip=True):
    flt = []
    if strip:
        flt.append("silenceremove=start_periods=1:start_duration=0.15:start_threshold=-40dB:stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB")
    if atempo:
        flt.append(f"atempo={atempo}")
    af = ",".join(flt) if flt else "anull"
    cmd = ["ffmpeg","-y","-i",in_path,"-af",af,"-ar","16000","-ac","1"]
    if max_sec: cmd += ["-t",str(max_sec)]
    cmd += [out_path]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def elevenlabs_tts_to_wav(text, out_wav):
    # simple sync TTS; for streaming, do it on the frontend
    import requests
    voice_id = os.getenv("ELEVENLABS_VOICE_ID","Rachel")  # pick your default
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": EL_KEY, "accept":"audio/mpeg","Content-Type":"application/json"}
    payload = {"text": text, "model_id":"eleven_multilingual_v2","voice_settings":{"stability":0.5,"similarity_boost":0.7}}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    mp3 = "/tmp/tts.mp3"; wav = out_wav
    Path(mp3).write_bytes(r.content)
    subprocess.run(["ffmpeg","-y","-i",mp3,"-ar","16000","-ac","1",wav], check=True)

def run_wav2lip(image, wav, out_mp4):
    # Minimal Wav2Lip CLI using inference.py
    cmd = ["python","/Wav2Lip/inference.py",
           "--checkpoint_path","/Wav2Lip/Wav2Lip.pth",
           "--face", image,
           "--audio", wav,
           "--outfile", out_mp4,
           "--fps","12"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return Path(out_mp4).exists(), p.stdout.decode()[-1200:], p.stderr.decode()[-1200:]

def run_multitalk(image, wav, out_mp4, size, steps, frames, audio_type, prompt):
    tmp_json = "/tmp/mt_input.json"
    Path(tmp_json).write_text(json.dumps({
        "prompt": prompt or "",
        "cond_image": image,
        "cond_audio": {"person1": wav},
        "audio_type": audio_type
    }))
    cmd = ["python","/MultiTalk/generate_multitalk.py",
           "--input_json", tmp_json,
           "--size", size,
           "--sample_steps", str(steps),
           "--frame_num", str(frames),
           "--output", out_mp4]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return Path(out_mp4).exists(), p.stdout.decode()[-1200:], p.stderr.decode()[-1200:]

def handler(event):
    try:
        inp = event.get("input",{}) or {}
        engine = (inp.get("engine") or "auto").lower()
        image = inp.get("image"); audio = inp.get("audio"); text = inp.get("text")
        size = inp.get("size","multitalk-480")
        steps = int(inp.get("sample_steps", 4))
        frames = int(inp.get("frame_num", 36))
        audio_type = inp.get("audio_type","para")
        prompt = inp.get("prompt","")

        # Media in /tmp
        img_path = ensure_local_media(image, "image") if image else "/app/assets/placeholder.png"
        wav_full = "/tmp/in.wav"

        if text and not audio:
            if not EL_KEY: return {"error":"NO_ELEVENLABS_API_KEY"}
            elevenlabs_tts_to_wav(text, wav_full)
        else:
            wav_full = ensure_local_media(audio, "audio")

        # Normalize + preview
        wav_preview = "/tmp/preview.wav"
        ffmpeg_norm_wav(wav_full, wav_full)          # normalize full
        ffmpeg_norm_wav(wav_full, wav_preview, max_sec=float(inp.get("preview_max_sec",3.0)),
                        atempo=float(inp.get("preview_speed",1.35)), strip=True)

        if engine == "idle":
            idle = "/app/assets/idle_480_12fps.mp4"
            if Path(idle).exists():
                return {"video_base64": b64_of(idle)}
            else:
                # fallback: quick Wav2Lip on preview
                outp = "/tmp/idle.mp4"
                ok,so,se = run_wav2lip(img_path, wav_preview, outp)
                return {"video_base64": b64_of(outp)} if ok else {"error":"idle_failed","stderr_tail":se}

        if engine == "fast":
            outp = "/tmp/fast.mp4"
            ok,so,se = run_wav2lip(img_path, wav_preview, outp)
            if ok: return {"video_base64": b64_of(outp)}
            # fallback to tiny MultiTalk
            ok,so,se = run_multitalk(img_path, wav_preview, outp, size, 4, 36, audio_type, prompt)
            return {"video_base64": b64_of(outp)} if ok else {"error":"fast_failed","stderr_tail":se}

        if engine == "mid":
            outp = "/tmp/mid.mp4"
            ok,so,se = run_multitalk(img_path, wav_preview, outp, size, 4, 36, audio_type, prompt)
            return {"video_base64": b64_of(outp)} if ok else {"error":"mid_failed","stderr_tail":se}

        if engine == "hq":
            outp = "/tmp/hq.mp4"
            steps_hq = int(inp.get("sample_steps",8))
            frames_hq = int(inp.get("frame_num",81))
            ok,so,se = run_multitalk(img_path, wav_full, outp, size, steps_hq, frames_hq, audio_type, prompt)
            return {"video_base64": b64_of(outp)} if ok else {"error":"hq_failed","stdout_tail":so,"stderr_tail":se}

        # AUTO: return idle now + start fast; also return a ready HQ payload
        idle = "/app/assets/idle_480_12fps.mp4"
        resp = {"idle_video_base64": b64_of(idle) if Path(idle).exists() else None}

        fast_out = "/tmp/fast.mp4"
        ok,so,se = run_wav2lip(img_path, wav_preview, fast_out)
        if not ok:
            ok,so,se = run_multitalk(img_path, wav_preview, fast_out, size, 4, 36, audio_type, prompt)
        if ok:
            resp["preview_video_base64"] = b64_of(fast_out)
        else:
            resp["preview_error"] = {"stderr_tail": se}

        resp["hq_payload"] = {
            "input": {
                "engine":"hq",
                "image": image,
                "audio": audio or None,
                "text": text or None,
                "size": size,
                "sample_steps": 8,
                "frame_num": 81,
                "audio_type": audio_type,
                "prompt": prompt
            }
        }
        resp["eta_hint_sec"] = 180
        return resp

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
