/** Hosted speech (Deepgram Aura), played through Web Audio.
 *
 *  The browser's speechSynthesis gives you no handle on the audio, so a mouth
 *  signal has to be guessed from word-boundary events. Here the audio arrives
 *  as bytes, which means an AnalyserNode and a mouth driven by the actual
 *  waveform - and it stops the instant we say so, rather than when the
 *  platform engine gets round to it.
 */

import { API_URL, getToken } from "../api/client";

export interface HostedVoiceStatus {
  enabled: boolean;
  provider: string;
  model: string | null;
}

export async function hostedVoiceStatus(): Promise<HostedVoiceStatus> {
  try {
    const response = await fetch(`${API_URL}/voice/status`);
    if (!response.ok) return { enabled: false, provider: "browser", model: null };
    return (await response.json()) as HostedVoiceStatus;
  } catch {
    return { enabled: false, provider: "browser", model: null };
  }
}

/** One player per conversation: one audio graph, one place to stop. */
export class HostedSpeaker {
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private source: AudioBufferSourceNode | null = null;
  private samples: Uint8Array | null = null;
  /** Bumped on every stop; anything carrying an older stamp is discarded. */
  private generation = 0;

  constructor(private readonly mentorSlug: string) {}

  private ensureContext(): AudioContext {
    if (!this.context) {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.context = new Ctor();
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.6;
      this.analyser.connect(this.context.destination);
      this.samples = new Uint8Array(this.analyser.frequencyBinCount);
    }
    return this.context;
  }

  /** Browsers block audio until a gesture; call this from the click. */
  async unlock(): Promise<void> {
    const context = this.ensureContext();
    if (context.state === "suspended") await context.resume();
  }

  /** Fetch and decode a sentence without playing it, so the next one is ready. */
  async prepare(text: string, signal?: AbortSignal): Promise<AudioBuffer | null> {
    const token = getToken();
    const response = await fetch(`${API_URL}/voice/speak`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text, mentor: this.mentorSlug }),
      signal,
    });
    if (!response.ok) {
      // 503 means the deployment has no key; the caller falls back quietly.
      if (response.status === 503) return null;
      throw new Error(`Speech failed (${response.status})`);
    }
    const bytes = await response.arrayBuffer();
    return await this.ensureContext().decodeAudioData(bytes);
  }

  /** Play a decoded buffer. Resolves when it finishes, or at once if stopped. */
  play(buffer: AudioBuffer): Promise<void> {
    const context = this.ensureContext();
    const stamp = this.generation;
    return new Promise((resolve) => {
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.analyser!);
      source.onended = () => {
        if (stamp !== this.generation) return resolve();
        this.source = null;
        resolve();
      };
      this.source = source;
      source.start();
    });
  }

  /** 0-1, from the real waveform rather than an approximation of it. */
  level(): number {
    if (!this.analyser || !this.samples || !this.source) return 0;
    this.analyser.getByteTimeDomainData(this.samples as Uint8Array<ArrayBuffer>);
    let peak = 0;
    for (let i = 0; i < this.samples.length; i += 1) {
      peak = Math.max(peak, Math.abs(this.samples[i] - 128));
    }
    // 128 is full scale for byte time-domain data; the multiplier opens the
    // mouth on ordinary speech rather than only on shouting.
    return Math.min(1, (peak / 128) * 2.4);
  }

  stop(): void {
    this.generation += 1;
    if (this.source) {
      try {
        this.source.onended = null;
        this.source.stop();
      } catch {
        /* already finished */
      }
      this.source = null;
    }
  }

  get stamp(): number {
    return this.generation;
  }

  async dispose(): Promise<void> {
    this.stop();
    if (this.context) {
      await this.context.close().catch(() => {});
      this.context = null;
      this.analyser = null;
    }
  }
}
