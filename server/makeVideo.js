import ffmpegPath from "ffmpeg-static";
import ffmpeg from "fluent-ffmpeg";
ffmpeg.setFfmpegPath(ffmpegPath);

export function imageWavToMp4(imagePath, wavPath, outPath) {
  return new Promise((resolve, reject) => {
    ffmpeg()
      .input(imagePath).inputOptions(["-loop 1"])
      .input(wavPath)
      .videoCodec("libx264")
      .audioCodec("aac")
      .fps(30)
      .outputOptions(["-tune stillimage","-pix_fmt yuv420p","-b:a 128k","-shortest","-movflags +faststart"])
      .size("?x720")
      .save(outPath)
      .on("end", () => resolve(outPath))
      .on("error", reject);
  });
}
