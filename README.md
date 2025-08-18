# MultiTalk RunPod Minimal

A tiny RunPod Serverless worker that:
- clones [MeiGen-AI/MultiTalk](https://github.com/MeiGen-AI/MultiTalk)
- downloads your `image_path` + `audio_paths.person1` URLs to `/tmp`
- calls `generate_multitalk.py`
- returns `video_base64`

## Deploy

1. Push this repo to GitHub.
2. RunPod Console → **Serverless** → **Create Endpoint**:
   - Source: **GitHub**, pick this repo + branch
   - Dockerfile path: `/Dockerfile`
   - (Keep default start command; handler calls `runpod.serverless.start`.)
3. Click **Build** and wait for status **Active**.

## Call it

```bash
IMG="https://YOUR-NGROK.ngrok-free.app/uploads/spokesperson.png"
AUD="https://YOUR-NGROK.ngrok-free.app/uploads/speech.wav"

curl -s -X POST "https://api.runpod.ai/v2/<ENDPOINT_ID>/run" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>" \
  -H "Content-Type: application/json" \
  -d "{
        \"input\": {
          \"prompt\": \"A woman is talking in a confident, helpful way.\",
          \"image_path\": \"${IMG}\",
          \"audio_paths\": { \"person1\": \"${AUD}\" },
          \"audio_type\": \"speech\",
          \"sample_text_guide_scale\": 1.0,
          \"sample_audio_guide_scale\": 2.0,
          \"sample_steps\": 8,
          \"mode\": \"streaming\"
        }
      }"
