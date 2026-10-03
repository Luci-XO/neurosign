/**
 * tracer.js - guide shape + single-stroke capture.
 * arm({onStart, onEnd}): recording starts when the user presses the pointer on the canvas and
 * ends when they release it; onEnd(samples) receives [[t_ms, x, y], ...].
 * Uses getCoalescedEvents() (every hardware sample, not one per frame) and pointer capture
 * (a stroke that leaves the canvas is not lost).
 */
class MovementTracer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.taskType = "spiral";
    this.armed = false;
    this.drawing = false;
    this.samples = [];
    this.startTime = 0;
    this.lastPoint = null;
    this.hooks = {};

    canvas.addEventListener("pointerdown", (e) => this._down(e));
    canvas.addEventListener("pointermove", (e) => this._move(e));
    canvas.addEventListener("pointerup", (e) => this._up(e));
    canvas.addEventListener("pointercancel", (e) => this._up(e));
    this.setTask("spiral");
  }

  setTask(taskType) { this.taskType = taskType; this.clear(); }

  /** Clear the canvas and wait for the next stroke. */
  arm(hooks) {
    this.hooks = hooks || {};
    this.clear();
    this.armed = true;
    this.canvas.classList.add("armed");
  }

  disarm() { this.armed = false; this.drawing = false; this.canvas.classList.remove("armed"); }

  clear() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.samples = [];
    this.lastPoint = null;
    this.drawing = false;
    this._drawGuide();
  }

  _down(e) {
    if (!this.armed || this.drawing) return;
    e.preventDefault();
    try { this.canvas.setPointerCapture(e.pointerId); } catch (err) {}
    this.drawing = true;
    this.samples = [];
    this.startTime = e.timeStamp;
    const p = this._pos(e);
    this.samples.push([0, p.x, p.y]);
    this.lastPoint = p;
    if (this.hooks.onStart) this.hooks.onStart();
  }

  _move(e) {
    if (!this.drawing) return;
    const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const ev of events.length ? events : [e]) {
      const t = ev.timeStamp - this.startTime;
      if (t <= 0) continue;
      const p = this._pos(ev);
      this.samples.push([t, p.x, p.y]);
      this.ctx.strokeStyle = "#2d6cdf";
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.moveTo(this.lastPoint.x, this.lastPoint.y);
      this.ctx.lineTo(p.x, p.y);
      this.ctx.stroke();
      this.lastPoint = p;
    }
  }

  _up(e) {
    if (!this.drawing) return;
    try { this.canvas.releasePointerCapture(e.pointerId); } catch (err) {}
    this.drawing = false;
    this.armed = false;
    this.canvas.classList.remove("armed");
    if (this.hooks.onEnd) this.hooks.onEnd(this.samples);
  }

  _pos(e) {
    const r = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * (this.canvas.width / r.width),
      y: (e.clientY - r.top) * (this.canvas.height / r.height),
    };
  }

  _drawGuide() {
    const { width, height } = this.canvas;
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = "#c7cfdb";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    if (this.taskType === "spiral") {
      const cx = width / 2, cy = height / 2, maxR = Math.min(width, height) / 2 - 20, turns = 4;
      ctx.beginPath();
      for (let a = 0; a <= turns * 2 * Math.PI; a += 0.05) {
        const r = (a / (turns * 2 * Math.PI)) * maxR;
        const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
        if (a === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#2d6cdf";
      ctx.beginPath(); ctx.arc(cx, cy, 5, 0, 2 * Math.PI); ctx.fill();   // start dot at the centre
    } else if (this.taskType === "wave") {
      const margin = 40, amp = height / 4, midY = height / 2;
      ctx.beginPath();
      for (let x = margin; x <= width - margin; x += 2) {
        const y = midY + amp * Math.sin(((x - margin) / (width - 2 * margin)) * 4 * Math.PI);
        if (x === margin) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#2d6cdf";
      ctx.beginPath(); ctx.arc(margin, midY, 5, 0, 2 * Math.PI); ctx.fill();   // start dot at the left end
    } else {
      ctx.setLineDash([]);
      ctx.fillStyle = "#9aa4b2";
      ctx.font = "14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Draw any simple shape in one stroke", width / 2, height / 2);
    }
    ctx.restore();
  }
}