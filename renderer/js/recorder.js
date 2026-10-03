/**
 * recorder.js - records the microphone and encodes a mono 16-bit PCM WAV in the browser
 * (plain WAV is what Praat reads reliably). Turns OFF echo cancellation, noise suppression
 * and auto-gain, which would otherwise distort jitter/shimmer.
 */
class VoiceRecorder {
  constructor() {
    this.audioContext = null;
    this.stream = null;
    this.sourceNode = null;
    this.processorNode = null;
    this.chunks = [];
    this.sampleRate = 44100;
    this.recording = false;
  }

  async start() {
    this.chunks = [];
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    if (this.audioContext.state === "suspended") await this.audioContext.resume();
    this.sampleRate = this.audioContext.sampleRate;

    this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);
    // ScriptProcessorNode is deprecated but simple and reliable in Electron.
    this.processorNode = this.audioContext.createScriptProcessor(4096, 1, 1);
    this.processorNode.onaudioprocess = (event) => {
      if (!this.recording) return;
      this.chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));  // copy: browser reuses the buffer
    };
    this.sourceNode.connect(this.processorNode);
    this.processorNode.connect(this.audioContext.destination);  // required for the callback to fire
    this.recording = true;
  }

  /** Releases the microphone without producing a WAV (used on errors). */
  release() {
    this.recording = false;
    try { if (this.processorNode) this.processorNode.disconnect(); } catch (e) {}
    try { if (this.sourceNode) this.sourceNode.disconnect(); } catch (e) {}
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.audioContext && this.audioContext.state !== "closed") this.audioContext.close();
  }

  async stop() {
    this.recording = false;
    this.release();
    return this._encodeWav(this._merge(this.chunks), this.sampleRate);
  }

  _merge(chunks) {
    const total = chunks.reduce((n, c) => n + c.length, 0);
    const out = new Float32Array(total);
    let offset = 0;
    for (const c of chunks) { out.set(c, offset); offset += c.length; }
    return out;
  }

  _encodeWav(samples, sampleRate) {
    const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
    const str = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
    str(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
    str(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    str(36, "data"); view.setUint32(40, samples.length * 2, true);
    let o = 44;
    for (let i = 0; i < samples.length; i++, o += 2) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([view], { type: "audio/wav" });
  }
}