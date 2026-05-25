// Browser-side voice client: capture mic as 16k LINEAR16 PCM, stream over
// the WS to the backend, play back the TTS audio that comes back.

const TARGET_RATE = 16000;

export type VoiceCallbacks = {
  onTranscript?: (text: string) => void;
  onAssistantTextDelta?: (chunk: string) => void;
  onAssistantText?: (text: string) => void;
  onDraftState?: (stack: unknown) => void;
  onSubmitted?: (feedback_id: string) => void;
  onReady?: (conversation_id: string) => void;
  onError?: (msg: string) => void;
  // Fired when the backend's retry-on-error path is about to back off
  // before re-attempting the LLM call (real APIError or simulated
  // outage — same code path). The page uses it to show the outage
  // indicator until the next delta arrives.
  onApiRetry?: () => void;
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
  private currentPlaybackSource: AudioBufferSourceNode | null = null;
  // True between stopPlayback() and the next transcript frame, so that
  // audio bytes already in flight from the backend (which doesn't know
  // we interrupted) get dropped instead of played.
  private suppressIncomingAudio = false;
  private conversationId: string | null = null;
  // Tracked per-session so the locale travels with both `begin` (start
  // of a new utterance) and `set_locale` (selector flipped while idle).
  private locale: string;
  // Optional ref pointing at the debug "simulate mic failure" toggle.
  // When `.current` is true, the next `begin` frame asks the backend to
  // short-circuit transcribe() into a TranscriptError so we exercise
  // the spoken-apology path without an actual STT outage.
  private forceSttFailRef: { readonly current: boolean } | null = null;
  // Same shape, for the "simulate Anthropic outage" toggle. Read at
  // `begin` so each utterance starts with the right state; `setOutage`
  // also pushes set_outage frames so a mid-turn toggle flip reaches
  // the backend immediately.
  private simulateOutageRef: { readonly current: boolean } | null = null;

  constructor(
    private readonly wsUrl: string,
    private readonly cb: VoiceCallbacks,
    locale: string = "en-US",
  ) {
    this.locale = locale;
  }

  setForceSttFailRef(ref: { readonly current: boolean }): void {
    this.forceSttFailRef = ref;
  }

  setSimulateOutageRef(ref: { readonly current: boolean }): void {
    this.simulateOutageRef = ref;
  }

  /** Push the current outage-toggle state to the backend. The caller
   *  invokes this each time the debug toggle flips so mid-turn changes
   *  reach the orchestrator's wait loop. */
  setOutage(value: boolean): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "set_outage", value }));
    }
  }

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
            // New turn begins — accept the backend's next audio batch
            // again, even if the previous turn's audio was interrupted.
            this.suppressIncomingAudio = false;
            this.cb.onTranscript?.(msg.text);
            break;
          case "api_retry":
            this.cb.onApiRetry?.();
            break;
          case "assistant_text_delta":
            this.cb.onAssistantTextDelta?.(msg.text);
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
        if (this.suppressIncomingAudio) return;
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
    const force_stt_fail = this.forceSttFailRef?.current === true;
    const simulate_anthropic_outage = this.simulateOutageRef?.current === true;
    this.ws.send(
      JSON.stringify({
        type: "begin",
        locale: this.locale,
        force_stt_fail,
        simulate_anthropic_outage,
      }),
    );

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

  /** Cancel any in-flight TTS playback and discard pending audio bytes
   *  until the next turn's transcript arrives. Called when the user
   *  presses the mic mid-playback — keeps the agent from hearing itself. */
  stopPlayback(): void {
    this.suppressIncomingAudio = true;
    this.playbackQueue.length = 0;
    if (this.currentPlaybackSource) {
      try {
        // .stop() triggers onended, which resolves the awaiter in the
        // drain loop; loop sees empty queue and exits cleanly.
        this.currentPlaybackSource.stop();
      } catch (_) {
        /* already stopped */
      }
    }
  }

  setSpeed(speed: number): void {
    // No-op if not yet open — the caller (GiveFeedback) re-sends on
    // connect, so dropping pre-open changes is fine.
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "set_speed", speed }));
    }
  }

  setLocale(locale: string): void {
    this.locale = locale;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "set_locale", locale }));
    }
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
      this.currentPlaybackSource = src;
      await new Promise<void>((resolve) => {
        src.onended = () => resolve();
        src.start();
      });
      this.currentPlaybackSource = null;
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
