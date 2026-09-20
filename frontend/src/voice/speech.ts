/** Browser speech: recognition in, synthesis out.
 *
 *  Both Web Speech APIs, so there is no extra key and no extra provider. The
 *  types are hand-written because TypeScript's DOM lib still does not ship
 *  SpeechRecognition - it is prefixed in Chrome and absent in Firefox.
 */

export interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): { transcript: string; confidence: number };
  [index: number]: { transcript: string; confidence: number };
}

interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number;
  readonly results: {
    readonly length: number;
    item(index: number): SpeechRecognitionResultLike;
    [index: number]: SpeechRecognitionResultLike;
  };
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: Event & { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

type RecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const speechSupported = {
  get listening(): boolean {
    return recognitionCtor() !== null;
  },
  get speaking(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  },
};

// --------------------------------------------------------------------------- //
// Listening
// --------------------------------------------------------------------------- //
export interface Listener {
  stop(): void;
  abort(): void;
}

/** Start recognition. `onFinal` fires once with the settled transcript. */
export function listen(options: {
  onPartial?: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (reason: string) => void;
  onEnd?: () => void;
}): Listener | null {
  const Ctor = recognitionCtor();
  if (!Ctor) return null;

  const recognition = new Ctor();
  recognition.lang = navigator.language || "en-US";
  // Non-continuous: the browser decides when a thought has finished, which is
  // a better turn boundary than any timer we would write.
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  let settled = "";

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const text = result[0].transcript;
      if (result.isFinal) settled += text;
      else interim += text;
    }
    options.onPartial?.((settled + interim).trim());
  };

  recognition.onerror = (event) => {
    // "aborted" is what we get when we stop it ourselves; not worth reporting.
    if (event.error !== "aborted" && event.error !== "no-speech") {
      options.onError(
        event.error === "not-allowed"
          ? "Microphone access was blocked. Allow it in your browser's site settings."
          : `Speech recognition failed (${event.error}).`,
      );
    }
  };

  recognition.onend = () => {
    const text = settled.trim();
    if (text) options.onFinal(text);
    options.onEnd?.();
  };

  try {
    recognition.start();
  } catch {
    return null;
  }

  return {
    stop: () => recognition.stop(),
    abort: () => recognition.abort(),
  };
}

// --------------------------------------------------------------------------- //
// Speaking
// --------------------------------------------------------------------------- //
export interface VoicePreference {
  prefer: string[];
  pitch: number;
  rate: number;
}

/** Voices load asynchronously in Chrome, and the first call returns []. */
export function voicesReady(): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    if (!speechSupported.speaking) return resolve([]);
    const existing = speechSynthesis.getVoices();
    if (existing.length) return resolve(existing);
    const timer = window.setTimeout(() => resolve(speechSynthesis.getVoices()), 1500);
    speechSynthesis.addEventListener(
      "voiceschanged",
      () => {
        window.clearTimeout(timer);
        resolve(speechSynthesis.getVoices());
      },
      { once: true },
    );
  });
}

/** macOS ships a pile of novelty voices that are unusable for speech.
 *  They are real SpeechSynthesisVoice entries and will be picked by any
 *  naive "first English voice" fallback. */
const NOVELTY = new Set([
  "albert", "bad news", "bahh", "bells", "boing", "bubbles", "cellos",
  "good news", "jester", "organ", "superstar", "trinoids", "whisper",
  "wobble", "zarvox", "junior", "ralph", "fred", "kathy", "princess",
  "deranged", "hysterical", "bruce", "agnes", "victoria",
]);

/** Higher is better. Quality varies enormously between engines, and the old
 *  local macOS voices are the ones people mean when they say it sounds bad. */
export function voiceScore(voice: SpeechSynthesisVoice): number {
  const name = voice.name.toLowerCase();
  if (NOVELTY.has(name)) return -100;
  if (!voice.lang.toLowerCase().startsWith("en")) return -50;

  let score = 0;
  // Neural / cloud engines, in rough order of how good they sound.
  if (name.includes("natural")) score += 60;
  if (name.includes("google")) score += 50;
  if (name.includes("premium") || name.includes("enhanced")) score += 40;
  if (name.includes("siri")) score += 35;
  // Decent modern local voices.
  if (/\b(samantha|daniel|karen|moira|tessa|serena|alex|allison|ava|tom|nicky)\b/.test(name))
    score += 20;
  // A local voice with no other signal is usually one of the old ones.
  if (voice.localService && score === 0) score -= 10;
  if (voice.default) score += 2;
  return score;
}

export function usableVoices(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  return voices
    .filter((v) => voiceScore(v) > -50)
    .sort((a, b) => voiceScore(b) - voiceScore(a) || a.name.localeCompare(b.name));
}

export function pickVoice(
  voices: SpeechSynthesisVoice[],
  prefer: string[],
): SpeechSynthesisVoice | null {
  for (const wanted of prefer) {
    const hit = voices.find(
      (v) => v.name.toLowerCase().includes(wanted.toLowerCase()) && voiceScore(v) > -50,
    );
    if (hit) return hit;
  }
  return usableVoices(voices)[0] ?? voices[0] ?? null;
}

/** Split streamed text into speakable chunks.
 *
 *  This is what makes the reply feel live rather than batched: the first
 *  sentence is spoken while the rest is still being generated. Returns the
 *  complete chunks found and whatever tail is not yet speakable.
 */
export function takeSpeakable(buffer: string): { chunks: string[]; rest: string } {
  const chunks: string[] = [];
  let rest = buffer;

  for (;;) {
    // A sentence end, or a hard line break, whichever comes first.
    const match = /([.!?…]["')\]]?\s)|(\n\n)/.exec(rest);
    if (!match || match.index === undefined) break;
    const cut = match.index + match[0].length;
    const chunk = rest.slice(0, cut).trim();
    if (chunk) chunks.push(chunk);
    rest = rest.slice(cut);
  }

  // A long clause with no sentence end yet would otherwise stall the voice.
  if (rest.length > 240) {
    const comma = rest.lastIndexOf(", ", 240);
    if (comma > 80) {
      chunks.push(rest.slice(0, comma + 1).trim());
      rest = rest.slice(comma + 1);
    }
  }
  return { chunks, rest };
}
