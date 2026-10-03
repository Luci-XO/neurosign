/**
 * renderer/js/app.js - the guided 8-step flow:
 *   register -> welcome -> steps 1-8 -> results (+ PDF)
 * All data goes to the local Flask backend. User-supplied text is only ever inserted with textContent.
 */
const API = window.neurosign.apiBaseUrl;
const $ = (id) => document.getElementById(id);

const STEPS = {
  1: { kind: "voice", title: "Voice baseline 1 of 3",
       text: "Press Start, then say a long, steady \"aaah\" for 3-4 seconds at your normal pitch, about a hand's length from the microphone. Press Stop when you are done. This sets your personal voice baseline." },
  2: { kind: "voice", title: "Voice baseline 2 of 3",
       text: "Same again: Start, a steady \"aaah\" for 3-4 seconds, then Stop." },
  3: { kind: "voice", title: "Voice baseline 3 of 3",
       text: "One more baseline recording: Start, a steady \"aaah\" for 3-4 seconds, then Stop." },
  4: { kind: "voice", title: "Voice detection test",
       text: "This is the detection recording. Say a steady \"aaah\" for 3-4 seconds exactly as before. It will be compared with your three baselines." },
  5: { kind: "movement", title: "Spiral baseline", task: "spiral",
       text: "Press and hold the mouse button on the blue dot in the centre, then follow the dotted spiral outwards in ONE smooth, steady stroke (about 5-10 seconds). Release at the end. Recording starts when you press and stops when you release." },
  6: { kind: "movement", title: "Wave baseline", task: "wave",
       text: "Press and hold on the blue dot at the left end and follow the dotted wave to the right in ONE smooth, steady stroke (about 4-8 seconds). Release at the end." },
  7: { kind: "movement", title: "Free shape baseline", task: "free",
       text: "Draw any simple shape you can repeat later (a star, a house, a loop) in ONE steady stroke lasting at least 3 seconds. Remember it - you may repeat it in step 8." },
  8: { kind: "movement", title: "Movement detection test", task: null,
       text: "Choose one of your earlier shapes below and trace it again, as steadily as you can, in one stroke. It will be compared with your baseline for that shape. (The spiral works best.)" },
};

const state = { profile: null, device: "mouse", sessionId: null, step: 1, done: {}, task8: "spiral", summary: null };

// ---------------- helpers ----------------
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(API + path, options);
  } catch (e) {
    throw new Error("Cannot reach the NeuroSign backend. Please restart the app.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function showScreen(name) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $("screen-" + name).classList.add("active");
  window.scrollTo(0, 0);
}

function setStatus(el, message, kind = "") {
  el.textContent = message;
  el.className = "status-line " + kind;
}

const fmt = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "N/A");
const scoreColor = (v) => (v == null ? "#a9b7cc" : v < 35 ? "#1e8449" : v < 50 ? "#d68910" : "#c0392b");

function fillTable(tableEl, rows) {
  tableEl.innerHTML = "";
  for (const [label, value] of rows) {
    const tr = document.createElement("tr");
    const a = document.createElement("td");
    const b = document.createElement("td");
    a.textContent = label;
    b.textContent = value;
    tr.append(a, b);
    tableEl.appendChild(tr);
  }
}

function showScore(prefix, score) {
  const circle = $(prefix + "-score-circle");
  $(prefix + "-score-value").textContent = score == null ? "--" : Math.round(score);
  circle.style.background = scoreColor(score);
}

// ---------------- screen 1: register ----------------
$("reg-continue").addEventListener("click", () => {
  const name = $("reg-name").value.trim();
  const age = parseInt($("reg-age").value, 10);
  const gender = $("reg-gender").value;
  const err = $("reg-error");
  if (!name) return setStatus(err, "Please enter your name.", "error");
  if (!Number.isInteger(age) || age < 18 || age > 120) return setStatus(err, "Please enter a valid age (18 to 120).", "error");
  if (!gender) return setStatus(err, "Please choose a gender option.", "error");
  setStatus(err, "");
  state.profile = { name, age, gender };
  $("welcome-name").textContent = name;
  setStatus($("welcome-error"), "");
  showScreen("welcome");
});

async function loadPast() {
  try {
    const rows = await api("/api/assessments");
    const body = $("past-body");
    body.innerHTML = "";
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      const c1 = document.createElement("td");
      c1.textContent = `${r.name} (${r.age})`;
      const c2 = document.createElement("td");
      c2.textContent = new Date(r.created_at.replace(" ", "T") + "Z").toLocaleString();
      const c3 = document.createElement("td");
      c3.textContent = r.verdict_title;
      const c4 = document.createElement("td");
      const a = document.createElement("a");
      a.textContent = "PDF";
      a.addEventListener("click", () => window.open(`${API}/api/assessments/${r.session_id}/report.pdf`));
      c4.appendChild(a);
      tr.append(c1, c2, c3, c4);
      body.appendChild(tr);
    });
    $("past-card").classList.toggle("hidden", rows.length === 0);
  } catch (e) { /* backend not ready: ignore, list is optional */ }
}

// ---------------- screen 2: welcome ----------------
$("welcome-back").addEventListener("click", () => showScreen("register"));

$("welcome-begin").addEventListener("click", async () => {
  const btn = $("welcome-begin");
  btn.disabled = true;
  try {
    state.device = document.querySelector('input[name="device"]:checked').value;
    const r = await api("/api/assessments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...state.profile, device: state.device }),
    });
    state.sessionId = r.session_id;
    state.step = 1;
    state.done = {};
    state.task8 = "spiral";
    document.querySelector('input[name="shape"][value="spiral"]').checked = true;
    showScreen("steps");
    renderStep();
  } catch (e) {
    setStatus($("welcome-error"), e.message, "error");
  } finally {
    btn.disabled = false;
  }
});

// ---------------- screen 3: steps ----------------
const recorder = new VoiceRecorder();
const tracer = new MovementTracer($("tracer-canvas"));
let voiceRecording = false, voiceTimerId = null, voiceStart = 0;
let moveTimerId = null;

function buildProgress() {
  const box = $("progress");
  box.innerHTML = "";
  for (let n = 1; n <= 8; n++) {
    const d = document.createElement("div");
    d.className = "pill" + (state.done[n] ? " done" : "") + (n === state.step ? " current" : "");
    d.textContent = n;
    box.appendChild(d);
  }
}

function currentTask() {
  return STEPS[state.step].task || state.task8;
}

function updateNext() {
  const btn = $("next-btn");
  btn.disabled = !state.done[state.step];
  btn.textContent = state.step === 8 ? "Analyze all results & build report" : "Next step";
}

function renderStep() {
  const n = state.step, cfg = STEPS[n];
  buildProgress();
  $("step-title").textContent = `Step ${n} of 8 - ${cfg.title}`;
  $("step-text").textContent = cfg.text;
  const isVoice = cfg.kind === "voice";
  $("voice-panel").classList.toggle("hidden", !isVoice);
  $("movement-panel").classList.toggle("hidden", isVoice);
  $("voice-result").classList.add("hidden");
  $("movement-result").classList.add("hidden");
  setStatus($("voice-status"), "");
  setStatus($("movement-status"), "");
  $("shape-picker").classList.toggle("hidden", n !== 8);
  $("voice-timer").textContent = "0.0s";
  $("movement-timer").textContent = "0.0s";
  $("voice-record-btn").textContent = "Start Recording";
  updateNext();
  if (!isVoice) armTracer();
  else tracer.disarm();
}

$("next-btn").addEventListener("click", async () => {
  if (state.step < 8) {
    state.step += 1;
    renderStep();
    return;
  }
  const btn = $("next-btn");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  try {
    state.summary = await api(`/api/assessments/${state.sessionId}/finalize`, { method: "POST" });
    renderResults(state.summary);
    showScreen("results");
  } catch (e) {
    setStatus($("movement-status"), e.message, "error");
    updateNext();
  }
});

// ---- voice
$("voice-record-btn").addEventListener("click", async () => {
  const btn = $("voice-record-btn"), status = $("voice-status");

  if (!voiceRecording) {
    try {
      await recorder.start();
    } catch (e) {
      recorder.release();
      return setStatus(status, "Microphone access failed. Please allow microphone use and try again.", "error");
    }
    voiceRecording = true;
    voiceStart = performance.now();
    voiceTimerId = setInterval(() => {
      $("voice-timer").textContent = ((performance.now() - voiceStart) / 1000).toFixed(1) + "s";
    }, 100);
    $("voice-result").classList.add("hidden");
    btn.textContent = "Stop & Analyze";
    setStatus(status, "Recording... say a steady 'aaah'.");
    return;
  }

  voiceRecording = false;
  clearInterval(voiceTimerId);
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  setStatus(status, "Analyzing your voice...");
  const step = state.step;
  try {
    const wav = await recorder.stop();
    const form = new FormData();
    form.append("step", step);
    form.append("audio", wav, "recording.wav");
    const r = await api(`/api/assessments/${state.sessionId}/voice`, { method: "POST", body: form });
    state.done[step] = true;
    const f = r.features;
    const rows = [
      ["Mean F0 (Hz)", fmt(f.f0_mean, 1)],
      ["Jitter (local)", fmt(f.jitter_local * 100, 2) + " %"],
      ["Shimmer (local)", fmt(f.shimmer_local * 100, 2) + " %"],
      ["HNR (dB)", fmt(f.hnr, 1)],
    ];
    if (step === 4) rows.push(["Change vs your baseline (0-100)", fmt(r.change_index, 1)]);
    showScore("voice", r.stage_score);
    fillTable($("voice-feature-table"), rows);
    $("voice-result").classList.remove("hidden");
    setStatus(status, "Recording analysed. Continue, or record again to replace it.", "success");
    buildProgress();
    updateNext();
  } catch (e) {
    recorder.release();
    setStatus(status, e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = state.done[step] ? "Record again" : "Start Recording";
    $("voice-timer").textContent = "0.0s";
  }
});

// ---- movement
function armTracer() {
  clearInterval(moveTimerId);
  $("movement-timer").textContent = "0.0s";
  tracer.setTask(currentTask());
  tracer.arm({
    onStart() {
      const t0 = performance.now();
      setStatus($("movement-status"), "Recording... keep tracing, release when finished.");
      moveTimerId = setInterval(() => {
        $("movement-timer").textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s";
      }, 100);
    },
    onEnd(samples) {
      clearInterval(moveTimerId);
      submitMovement(samples);
    },
  });
  if (!state.done[state.step]) setStatus($("movement-status"), "Press and hold on the canvas to begin.");
}

async function submitMovement(samples) {
  const step = state.step, status = $("movement-status");
  setStatus(status, "Analyzing your movement...");
  $("next-btn").disabled = true;
  try {
    const r = await api(`/api/assessments/${state.sessionId}/movement`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step, task_type: currentTask(), samples }),
    });
    state.done[step] = true;
    const f = r.features;
    const rows = [
      ["Duration (s)", fmt(f.duration_s, 1)],
      ["Samples captured", String(f.n_samples)],
      ["Tremor share (4-6 Hz)", fmt(f.tremor_share * 100, 0) + " %"],
      ["Peak frequency (Hz)", fmt(f.peak_freq_hz, 1)],
      ["Velocity variability (CV)", fmt(f.velocity_cv, 2)],
      ["Path deviation (px)", f.path_deviation == null ? "N/A" : fmt(f.path_deviation, 2)],
    ];
    if (step === 8) rows.push([`Change vs step ${r.compared_step} baseline (0-100)`, fmt(r.change_index, 1)]);
    showScore("movement", r.stage_score);
    fillTable($("movement-feature-table"), rows);
    $("movement-result").classList.remove("hidden");
    setStatus(status, "Step analysed. Continue, or press 'Clear / redo' to replace it.", "success");
    buildProgress();
    updateNext();
  } catch (e) {
    updateNext();
    armTracer();
    setStatus(status, e.message + " Please try again: press and hold on the canvas.", "error");
  }
}

$("movement-redo-btn").addEventListener("click", () => {
  if (tracer.drawing) return;
  $("movement-result").classList.add("hidden");
  armTracer();
});

document.querySelectorAll('input[name="shape"]').forEach((radio) => {
  radio.addEventListener("change", (e) => {
    if (tracer.drawing) { document.querySelector(`input[name="shape"][value="${state.task8}"]`).checked = true; return; }
    state.task8 = e.target.value;
    state.done[8] = false;            // a different shape needs its own analysis
    $("movement-result").classList.add("hidden");
    updateNext();
    armTracer();
  });
});

// ---------------- screen 4: results ----------------
function renderResults(summary) {
  const v = summary.verdict;
  $("verdict-card").style.background = v.color;
  $("verdict-title").textContent = v.title;
  $("verdict-message").textContent = v.message;

  const flags = $("flags-body");
  flags.innerHTML = "";
  v.flags.forEach((f) => {
    const tr = document.createElement("tr");
    const a = document.createElement("td"); a.textContent = f.label;
    const b = document.createElement("td"); b.textContent = f.value == null ? "N/A" : f.value;
    const c = document.createElement("td");
    c.textContent = f.flagged ? "FLAGGED" : f.value == null ? "n/a" : "ok";
    if (f.flagged) c.className = "flagged";
    tr.append(a, b, c);
    flags.appendChild(tr);
  });

  const body = $("stages-body");
  body.innerHTML = "";
  summary.stages.forEach((s) => {
    const tr = document.createElement("tr");
    const cells = [String(s.step), s.name, s.role];
    cells.forEach((t) => { const td = document.createElement("td"); td.textContent = t; tr.appendChild(td); });
    const sc = document.createElement("td");
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.style.width = Math.max(2, (s.score || 0) * 0.8) + "px";
    bar.style.background = scoreColor(s.score);
    sc.append(bar, document.createTextNode(fmt(s.score, 1)));
    const ch = document.createElement("td");
    ch.textContent = s.role === "Detection" ? fmt(s.change_index, 1) : "-";
    tr.append(sc, ch);
    body.appendChild(tr);
  });
  setStatus($("results-status"), "");
}

const reportUrl = () => `${API}/api/assessments/${state.sessionId}/report.pdf`;

$("open-pdf-btn").addEventListener("click", () => window.open(reportUrl()));

$("save-pdf-btn").addEventListener("click", async () => {
  const status = $("results-status");
  try {
    const res = await fetch(reportUrl());
    if (!res.ok) throw new Error("Could not create the report.");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `NeuroSign_${state.profile.name.replace(/[^\w-]+/g, "_")}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    setStatus(status, "Report saved.", "success");
  } catch (e) {
    setStatus(status, e.message, "error");
  }
});

$("restart-btn").addEventListener("click", () => {
  state.profile = null; state.sessionId = null; state.summary = null; state.done = {};
  $("reg-name").value = ""; $("reg-age").value = ""; $("reg-gender").value = "";
  tracer.disarm();
  showScreen("register");
  loadPast();
});

// ---------------- startup ----------------
loadPast();