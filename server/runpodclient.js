// /server/runpodClient.js
export async function callRunPod({ imageUrl, wavUrl, prompt }) {
  const ENDPOINT_ID = process.env.RUNPOD_ENDPOINT_ID;
  const API_KEY = process.env.RUNPOD_API_KEY;

  if (!ENDPOINT_ID) throw new Error("RUNPOD_ENDPOINT_ID is missing");
  if (!API_KEY) throw new Error("RUNPOD_API_KEY is missing");

  const body = {
    input: {
      prompt: prompt || "Customer-service agent speaking clearly and helpfully.",
      image_path: imageUrl,                      // <- URL, worker downloads it
      audio_paths: { person1: wavUrl },         // <- URL, worker downloads it
      audio_type: "speech",
      sample_text_guide_scale: 1.0,
      sample_audio_guide_scale: 2.0,
      sample_steps: 8,
      mode: "streaming",
      size: "multitalk-480"
    }
  };

  // submit
  const runResRaw = await fetch(`https://api.runpod.ai/v2/${ENDPOINT_ID}/run`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  const runText = await runResRaw.text();
  if (!runResRaw.ok) throw new Error(`RunPod /run HTTP ${runResRaw.status}: ${runText.slice(0, 800)}`);
  let runRes; try { runRes = JSON.parse(runText); } catch { throw new Error(`RunPod /run non-JSON: ${runText.slice(0, 800)}`); }
  const id = runRes.id; if (!id) throw new Error(`RunPod /run missing job id: ${runText}`);
  console.log("RunPod job id:", id);

  // poll
  for (;;) {
    await new Promise(r => setTimeout(r, 2500));
    const statusRaw = await fetch(`https://api.runpod.ai/v2/${ENDPOINT_ID}/status/${id}`, {
      headers: { Authorization: `Bearer ${API_KEY}` }
    });
    const statusText = await statusRaw.text();
    if (!statusRaw.ok) throw new Error(`RunPod /status HTTP ${statusRaw.status}: ${statusText.slice(0, 1200)}`);
    let status; try { status = JSON.parse(statusText); } catch { throw new Error(`RunPod /status non-JSON: ${statusText.slice(0, 1200)}`); }

    if (status.status === "COMPLETED") {
      return status.output?.video_base64;
    }
    if (status.status === "FAILED") {
      const o = status.output || {};
      const details = [
        o.error && `error: ${o.error}`,
        o.stdout && `\n--- stdout ---\n${o.stdout.slice(-2000)}`,
        o.stderr && `\n--- stderr ---\n${o.stderr.slice(-2000)}`
      ].filter(Boolean).join("");
      throw new Error(details || "RunPod job failed (no details)");
    }
  }
}
