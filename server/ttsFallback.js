// /server/ttsFallback.js
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import gTTS from "gtts";
import ffmpegPath from "ffmpeg-static";
import ffmpeg from "fluent-ffmpeg";

ffmpeg.setFfmpegPath(ffmpegPath);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

export async function ttsFallbackToWav16k(text, outWavPath) {
  const tmpMp3 = path.join(__dirname, "tmp_gtts.mp3");
  await new Promise((resolve, reject) => {
    new gTTS(text, "en").save(tmpMp3, err => (err ? reject(err) : resolve()));
  });
  await new Promise((resolve, reject) => {
    ffmpeg(tmpMp3)
      .audioChannels(1)
      .audioFrequency(16000)
      .audioCodec("pcm_s16le")
      .format("wav")
      .save(outWavPath)
      .on("end", resolve)
      .on("error", reject);
  });
  fs.unlink(tmpMp3, () => {});
  return outWavPath;
}
