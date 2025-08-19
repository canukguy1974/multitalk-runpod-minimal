// /server/routes/talking-reply.js
import fs from "fs";
import path from "path";
import multer from "multer";
import ffmpegPath from "ffmpeg-static";
import ffmpeg from "fluent-ffmpeg";
import OpenAI from "openai";
import { fileURLToPath } from "url";
import { ttsFallbackToWav16k } from "../ttsFallback.js";
import { callRunPod } from "../runpodClient.js";
import { imageWavToMp4 } from "../makeVideo.js";

ffmpeg.setFfmpegPath(ffmpegPath);

// Resolve /server and /server/uploads robustly (no cwd surprises)
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const serverRoot = path.join(__dirname, "..");
const uploadsDir = path.join(serverRoot, "uploads");

// ✅ THIS creates the `upload` you’re missing
const upload = multer({ dest: uploadsDir });

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

function publicUrl(fileName) {
  return `${process.env.PUBLIC_BASE_URL}/uploads/${encodeURIComponent(fileName)}`;
}

async function ensureWav16kMono(inputPath, outPath) {
  return new Promise((resolve, reject) => {
    ffmpeg(inputPath)
      .audioChannels(1)
      .audioFrequency(16000)
      .audioCodec("pcm_s16le")
      .format("wav")
      .save(outPath)
      .on("end", () => resolve(outPath))
      .on("error", reject);
  });
}

export const talkingReplyMiddleware = upload.fields([
  { name: "image", maxCount: 1 },
  { name: "audio", maxCount: 1 }
]);

export async function talkingReplyHandler(req, res) {
  try {
    const imageFile = req.files?.image?.[0];
    const audioFile = req.files?.audio?.[0];
    const userText = req.body.text?.trim();

    if (!imageFile) {
      return res.status(400).json({ error: "image is required" });
    }

    // 1) Input text: either provided or transcribe uploaded audio
    let transcript = userText || "";

    if (!transcript && audioFile) {
      const tmpWav = path.join(uploadsDir, `in_${Date.now()}.wav`);
      await ensureWav16kMono(audioFile.path, tmpWav);

      const file = fs.createReadStream(tmpWav);
      const tr = await openai.audio.transcriptions.create({
        model: "whisper-1",
        file
      });
      transcript = tr.text?.trim() || "";
    }

    if (!transcript) {
      return res.status(400).json({ error: "Provide text or audio to transcribe." });
    }

    // 2) Get assistant reply (GPT-4o)
    const system =
      "You are a helpful, calm customer-service assistant. Be concise, friendly, and solution-focused.";
    const chat = await openai.chat.completions.create({
      model: "gpt-4o",
      temperature: 0.4,
      messages: [
        { role: "system", content: system },
        { role: "user", content: transcript }
      ]
    });
    const replyText =
      chat.choices?.[0]?.message?.content?.trim() ||
      "Thanks for reaching out! How can I help today?";

    // 3) TTS → mono 16k WAV (ElevenLabs if key, else gTTS)
    const outWav = path.join(uploadsDir, `tts_${Date.now()}.wav`);
    const elevenKey = process.env.ELEVENLABS_API_KEY;

    if (elevenKey) {
      const voiceId = "21m00Tcm4TlvDq8ikWAM"; // Rachel (female)
      const resp = await fetch(
        `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`,
        {
          method: "POST",
          headers: {
            "xi-api-key": elevenKey,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            text: replyText,
            model_id: "eleven_monolingual_v1",
            voice_settings: { stability: 0.5, similarity_boost: 0.75 }
          })
        }
      );
      if (!resp.ok) throw new Error(`ElevenLabs error ${resp.status}`);
      const mp3Buf = Buffer.from(await resp.arrayBuffer());
      const tmpMp3 = path.join(uploadsDir, `tts_${Date.now()}.mp3`);
      fs.writeFileSync(tmpMp3, mp3Buf);
      await ensureWav16kMono(tmpMp3, outWav);
      fs.unlink(tmpMp3, () => {});
    } else {
      await ttsFallbackToWav16k(replyText, outWav);
    }

    // 4) Public URLs for the RunPod worker
    const imgUrl = publicUrl(path.basename(imageFile.path));
    const wavUrl = publicUrl(path.basename(outWav));

    // 5) Call RunPod MultiTalk → video_base64
    const videoB64 = await callRunPod({
      imageUrl: imgUrl,
      wavUrl,
      prompt: "Customer-service agent speaking clearly and helpfully."
    });
    if (!videoB64) {
  const fallback = path.join(uploadsDir, `fallback_${Date.now()}.mp4`);
  await imageWavToMp4(imageFile.path, outWav, fallback);
  return res.json({
    ok: true,
    note: "Fallback static video (no lipsync)",
    transcript,
    replyText,
    audioUrl: wavUrl,
    videoUrl: `${process.env.PUBLIC_BASE_URL}/uploads/${path.basename(fallback)}`
  });
}
    // 6) Save mp4 and respond
    const outMp4 = path.join(uploadsDir, `video_${Date.now()}.mp4`);
    fs.writeFileSync(outMp4, Buffer.from(videoB64, "base64"));

    return res.json({
      ok: true,
      transcript,
      replyText,
      audioUrl: wavUrl,
      videoUrl: publicUrl(path.basename(outMp4))
    });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ error: String(e.message || e) });
  }
}
