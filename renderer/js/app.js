/**
 * renderer/js/app.js - home -> (login on demand) -> register -> welcome -> steps 1-8 -> results
 * All data goes to the local Flask backend. User-supplied text is only ever inserted with textContent.
 */
const API = window.neurosign.apiBaseUrl;
const $ = (id) => document.getElementById(id);

let AUTH_TOKEN = null;
let AUTH_USERNAME = null;

let PENDING_ACTION = null;

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

const EXERCISES = [
  {
    id: "seated-march",
    title: "Seated marching",
    summary: "Gently lift one foot at a time while sitting in a sturdy chair.",
    instructions: "Sit toward the front of a stable chair with both feet resting on the floor. Sit tall, then slowly lift one foot a few inches, lower it, and repeat with the other foot. Keep alternating at an easy pace.",
    cue: "Keep your back supported if needed; make the lift smaller or stop if it feels uncomfortable.",
    image: "img/exercises/seated-march.png",
  },
  {
    id: "heel-raises",
    title: "Supported heel raises",
    summary: "Hold a stable support and gently rise onto your toes.",
    instructions: "Stand facing a sturdy counter or the back of a heavy chair, with both hands resting on it. Keeping your body upright, slowly lift your heels, pause briefly if comfortable, then lower them with control.",
    cue: "Keep both feet pointing forward and stay close to your support. Skip this if standing does not feel steady.",
    image: "img/exercises/heel-raises.png",
  },
  {
    id: "knee-extension",
    title: "Seated knee extension",
    summary: "Slowly straighten one knee while seated, then switch legs.",
    instructions: "Sit in a stable chair with your feet flat on the floor. Slowly straighten one knee until your leg is comfortable, pause briefly, then lower your foot back down. Repeat on the other side.",
    cue: "Use a small, pain-free range and keep the movement slow. Do not lock your knee.",
    image: "img/exercises/knee-extension.png",
  },
  {
    id: "supported-side-steps",
    title: "Supported side steps",
    summary: "With a counter within reach, take a few small sideways steps.",
    instructions: "Stand beside a clear, sturdy counter and keep one or both hands in contact with it. Take one small step sideways, bring the other foot in, and repeat for a few steps. Turn carefully, then return the other way if comfortable.",
    cue: "Keep your steps small and avoid crossing your feet. Have someone nearby if balance is a concern.",
    image: "img/exercises/supported-side-steps.png",
  },
  {
    id: "shoulder-rolls",
    title: "Gentle shoulder rolls",
    summary: "Slowly roll your shoulders in a comfortable, relaxed motion.",
    instructions: "Sit or stand comfortably with your arms relaxed by your sides. Slowly lift your shoulders toward your ears, roll them gently backward, and let them settle. Repeat a few times, then reverse direction if it feels comfortable.",
    cue: "Keep your neck relaxed and use a small range; stop if you feel pain or pinching.",
    image: "img/exercises/shoulder-rolls.png",
  },
  {
    id: "relaxed-voice",
    title: "Relaxed voice practice",
    summary: "Read a short sentence aloud in a natural, comfortable voice.",
    instructions: "Sit comfortably and take an easy breath. Read a short sentence or talk about something familiar at your usual pace and comfortable volume. Pause to breathe as needed.",
    cue: "This is gentle practice, not a voice test. Do not force your volume or continue if your throat feels strained.",
    image: "img/exercises/relaxed-voice.png",
  },
];

// ---------------- helpers ----------------

function authHeader() {
  return AUTH_TOKEN ? { Authorization: "Bearer " + AUTH_TOKEN } : {};
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), ...authHeader() };
  let response;
  try {
    response = await fetch(API + path, { ...options, headers });
  } catch (e) {
    throw new Error("Cannot reach the NeuroSign backend. Please restart the app.");
  }
  if (response.status === 401) {
    window.NS_onLogout && window.NS_onLogout("Your session has expired. Please sign in again.");
    throw new Error("Your session has expired. Please sign in again.");
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

async function openReportBlob(sessionId) {
  const res = await fetch(`${API}/api/assessments/${sessionId}/report.pdf`, { headers: authHeader() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "Could not open the report.");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url);
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

// ---------------- navigation ----------------

function goHome() {
  PENDING_ACTION = null;
  showScreen("home");
}
window.NS_goHome = goHome;

function requireAuth(action, proceed) {
  if (AUTH_TOKEN) {
    proceed();
  } else {
    PENDING_ACTION = action;
    showScreen("login");
  }
}

$("home-know-more-btn").addEventListener("click", () => showScreen("knowmore"));
$("home-test-btn").addEventListener("click", () => requireAuth("test", () => { showScreen("register"); loadPast(); }));
$("home-neuro-btn").addEventListener("click", () => requireAuth("neuro", () => showScreen("neuro")));
$("home-nav-btn").addEventListener("click", goHome);
$("knowmore-back-btn").addEventListener("click", goHome);
$("neuro-back-btn").addEventListener("click", goHome);

// ---------------- auth session handlers (called by auth.js) ----------------

window.NS_onLogin = function (token, username) {
  AUTH_TOKEN = token;
  AUTH_USERNAME = username;
  $("account-username").textContent = username;
  $("account-box").classList.remove("hidden");

  const action = PENDING_ACTION;
  PENDING_ACTION = null;
  if (action === "test") { showScreen("register"); loadPast(); }
  else if (action === "neuro") { showScreen("neuro"); }
  else { showScreen("home"); }
};

window.NS_onLogout = function (message) {
  AUTH_TOKEN = null;
  AUTH_USERNAME = null;
  localStorage.removeItem("neurosign_token");
  localStorage.removeItem("neurosign_username");
  $("account-box").classList.add("hidden");
  state.profile = null; state.sessionId = null; state.summary = null; state.done = {};
  showScreen("home");
  if (window.NS_showLoginMessage) window.NS_showLoginMessage(message || "");
};

$("logout-btn").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* ignore - logging out locally regardless */ }
  window.NS_onLogout();
});

// ---------------- screen: register ----------------
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
      a.href = "#";
      a.addEventListener("click", (e) => {
        e.preventDefault();
        openReportBlob(r.session_id).catch((err) => console.error(err));
      });
      c4.appendChild(a);
      tr.append(c1, c2, c3, c4);
      body.appendChild(tr);
    });
    $("past-card").classList.toggle("hidden", rows.length === 0);
  } catch (e) { /* backend not ready, or logged out: ignore, list is optional */ }
}

// ---------------- screen: welcome ----------------
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

// ---------------- screen: steps ----------------
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
      body: JSON.stringify({
        step,
        task_type: currentTask(),
        canvas_size: { width: tracer.canvas.width, height: tracer.canvas.height },
        samples,
      }),
    });
    state.done[step] = true;
    const f = r.features;
    const rows = [
      ["Duration (s)", fmt(f.duration_s, 1)],
      ["Samples captured", String(f.n_samples)],
      ["Tremor share (4-6 Hz)", fmt(f.tremor_share * 100, 0) + " %"],
      ["Peak frequency (Hz)", fmt(f.peak_freq_hz, 1)],
      ["Velocity variability (CV)", fmt(f.velocity_cv, 2)],
      ["Distance from guide (95th percentile)", f.guide_deviation == null ? "N/A" : fmt(f.guide_deviation, 1) + " px"],
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
    state.done[8] = false;
    $("movement-result").classList.add("hidden");
    updateNext();
    armTracer();
  });
});

// ---------------- screen: results ----------------
function renderExercises() {
  const grid = $("exercise-grid");
  grid.replaceChildren();

  for (const exercise of EXERCISES) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "exercise-card";
    card.dataset.exercise = exercise.id;
    card.setAttribute("aria-haspopup", "dialog");

    const illustration = document.createElement("span");
    illustration.className = "exercise-illustration";
    const image = document.createElement("img");
    image.src = exercise.image;
    image.alt = `${exercise.title} illustration`;
    image.loading = "lazy";
    illustration.appendChild(image);
    const title = document.createElement("span");
    title.className = "exercise-card-title";
    title.textContent = exercise.title;
    const summary = document.createElement("span");
    summary.className = "exercise-card-summary";
    summary.textContent = exercise.summary;
    const more = document.createElement("span");
    more.className = "exercise-card-more";
    more.textContent = "View steps";
    card.append(illustration, title, summary, more);
    grid.appendChild(card);
  }
}

function openExercise(exercise) {
  $("exercise-dialog-title").textContent = exercise.title;
  $("exercise-dialog-instructions").textContent = exercise.instructions;
  $("exercise-dialog-cue").textContent = exercise.cue;
  const illustration = $("exercise-dialog-illustration");
  illustration.replaceChildren();
  const image = document.createElement("img");
  image.src = exercise.image;
  image.alt = `${exercise.title} illustration`;
  illustration.appendChild(image);
  $("exercise-dialog").showModal();
}

$("exercise-grid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-exercise]");
  const exercise = card && EXERCISES.find((item) => item.id === card.dataset.exercise);
  if (exercise) openExercise(exercise);
});
$("exercise-dialog-close").addEventListener("click", () => $("exercise-dialog").close());
$("exercise-dialog").addEventListener("click", (event) => {
  if (event.target === $("exercise-dialog")) $("exercise-dialog").close();
});

function renderResults(summary) {
  renderExercises();
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
    const guide = document.createElement("td");
    const guideDeviation = s.kind === "movement" ? s.data.guide_deviation : null;
    guide.textContent = guideDeviation == null ? "-" : `${fmt(guideDeviation, 1)} px`;
    const ch = document.createElement("td");
    ch.textContent = s.role === "Detection" ? fmt(s.change_index, 1) : "-";
    tr.append(sc, guide, ch);
    body.appendChild(tr);
  });
  setStatus($("results-status"), "");
}

$("open-pdf-btn").addEventListener("click", () => {
  openReportBlob(state.sessionId).catch((e) => setStatus($("results-status"), e.message, "error"));
});

$("save-pdf-btn").addEventListener("click", async () => {
  const status = $("results-status");
  try {
    const res = await fetch(`${API}/api/assessments/${state.sessionId}/report.pdf`, { headers: authHeader() });
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