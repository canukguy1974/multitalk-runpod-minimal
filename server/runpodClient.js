// /server/runpodClient.js
export async function callRunPod({ imageUrl, wavUrl, prompt }) {
  const body = {
    input: {
      prompt: prompt || "Customer-service agent speaking clearly and helpfully.",
      image_path: imageUrl,
      audio_paths: { person1: wavUrl },
      audio_type: "speech",
      sample_text_guide_scale: 1.0,
      sample_audio_guide_scale: 2.0,
      sample_steps: 8,
      mode: "streaming",
      size: "multitalk-480"
    }
  };

  const runRes = await fetch(`https://api.runpod.ai/v2/${process.env.RUNPOD_ENDPOINT_ID}/run`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.RUNPOD_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  }).then(r => r.json());

  const id = runRes.id;
  if (!id) throw new Error(`RunPod run error: ${JSON.stringify(runRes)}`);

  // poll
  for (;;) {
    await new Promise(r => setTimeout(r, 2500));
    const status = await fetch(`https://api.runpod.ai/v2/${process.env.RUNPOD_ENDPOINT_ID}/status/${id}`, {
      headers: { Authorization: `Bearer ${process.env.RUNPOD_API_KEY}` }
    }).then(r => r.json());
    if (status.status === "COMPLETED") return status.output.video_base64;
    if (status.status === "FAILED") throw new Error(status.error || "RunPod job failed");
  }
}
