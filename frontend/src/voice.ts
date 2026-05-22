// Browser-side voice client: capture mic as 16k LINEAR16 PCM, stream over
// the WS to the backend, play back the TTS audio that comes back.

const TARGET_RATE = 16000;

export type VoiceCallbacks = {
  onTranscript?: (text: string) => void;
  onAssistantText?: (text: string) => void;
  onDraftState?: (stack: unknown) => void;
  onSubmitted?: (feedback_id: string) => void;
  onReady?: (conversation_id: string) => void;
  onError?: (msg: string) => void;
};

export class VoiceSession {
  private ws: WebSocket | null = null;
  private audioCtx: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private playbackCtx: AudioContext | null = null;
  private playbackQueue: ArrayBuffer[] = [];
  private isPlaying = false;
  private conversationId: string | null = null;

  constructor(
    private readonly wsUrl: string,
    private readonly cb: VoiceCallbacks,
  ) {}

  async connect(): Promise<void> {
    this.ws = new WebSocket(this.wsUrl);
    this.ws.binaryType = "arraybuffer";
    await new Promise<void>((resolve, reject) => {
      this.ws!.onopen = () => resolve();
      this.ws!.onerror = () => reject(new Error("voice ws error"));
    });
    this.ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case "ready":
            this.conversationId = msg.conversation_id;
            this.cb.onReady?.(msg.conversation_id);
            break;
          case "transcript":
            this.cb.onTranscript?.(msg.text);
            break;
          case "assistant_text":
            this.cb.onAssistantText?.(msg.text);
            break;
          case "draft_state":
            this.cb.onDraftState?.(msg.stack);
            break;
          case "submitted":
            this.cb.onSubmitted?.(msg.feedback_id);
            break;
          case "audio_end":
            // No-op; playback drains on its own.
            break;
          case "error":
            this.cb.onError?.(msg.message);
            break;
        }
      } else {
        this.playbackQueue.push(ev.data as ArrayBuffer);
        void this.drainPlayback();
      }
    };
  }

  get conversation(): string | null {
    return this.conversationId;
  }

  async startRecording(): Promise<void> {
    if (!this.ws) throw new Error("not connected");
    this.ws.send(JSON.stringify({ type: "begin" }));

    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.audioCtx = new AudioContext();
    this.source = this.audioCtx.createMediaStreamSource(this.mediaStream);
    // 4096-sample buffer is plenty for push-to-talk.
    this.processor = this.audioCtx.createScriptProcessor(4096, 1, 1);
    const inputRate = this.audioCtx.sampleRate;
    this.processor.onaudioprocess = (e) => {
      const f32 = e.inputBuffer.getChannelData(0);
      const downsampled = downsample(f32, inputRate, TARGET_RATE);
      const pcm = floatToInt16LE(downsampled);
      this.ws?.send(pcm);
    };
    this.source.connect(this.processor);
    this.processor.connect(this.audioCtx.destination);
  }

  stopRecording(): void {
    this.processor?.disconnect();
    this.source?.disconnect();
    this.mediaStream?.getTracks().forEach((t) => t.stop());
    void this.audioCtx?.close();
    this.processor = null;
    this.source = null;
    this.mediaStream = null;
    this.audioCtx = null;
    this.ws?.send(JSON.stringify({ type: "end" }));
  }

  disconnect(): void {
    try {
      this.ws?.close();
    } catch (_) {
      /* ignore */
    }
    this.ws = null;
  }

  private async drainPlayback(): Promise<void> {
    if (this.isPlaying) return;
    this.isPlaying = true;
    this.playbackCtx ??= new AudioContext({ sampleRate: TARGET_RATE });
    while (this.playbackQueue.length > 0) {
      const buf = this.playbackQueue.shift()!;
      const float32 = int16LEToFloat(new Int16Array(buf));
      const audioBuf = this.playbackCtx.createBuffer(1, float32.length, TARGET_RATE);
      audioBuf.getChannelData(0).set(float32);
      const src = this.playbackCtx.createBufferSource();
      src.buffer = audioBuf;
      src.connect(this.playbackCtx.destination);
      await new Promise<void>((resolve) => {
        src.onended = () => resolve();
        src.start();
      });
    }
    this.isPlaying = false;
  }
}

function downsample(buffer: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const outLen = Math.floor(buffer.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(buffer.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += buffer[j];
    out[i] = sum / (end - start);
  }
  return out;
}

function floatToInt16LE(buffer: Float32Array): ArrayBuffer {
  const out = new ArrayBuffer(buffer.length * 2);
  const view = new DataView(out);
  for (let i = 0; i < buffer.length; i++) {
    const s = Math.max(-1, Math.min(1, buffer[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return out;
}

function int16LEToFloat(buffer: Int16Array): Float32Array {
  const out = new Float32Array(buffer.length);
  for (let i = 0; i < buffer.length; i++) {
    out[i] = buffer[i] / (buffer[i] < 0 ? 0x8000 : 0x7fff);
  }
  return out;
}
