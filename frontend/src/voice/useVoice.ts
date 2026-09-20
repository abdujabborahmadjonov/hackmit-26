import { useCallback, useEffect, useRef, useState } from "react";
import {
  listen,
  pickVoice,
  usableVoices,
  speechSupported,
  takeSpeakable,
  voicesReady,
  type Listener,
  type VoicePreference,
} from "./speech";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

/** The conversation loop: listen, hand the transcript up, speak what comes back.
 *
 *  Stopping is the hard part. `speechSynthesis.cancel()` does not reliably
 *  empty a deep queue in Chrome, and every utterance already in flight still
 *  fires `onend` afterwards - so a naive implementation puts the state machine
 *  back into "speaking" a moment after the user stopped it. Everything here is
 *  therefore stamped with a generation: cancelling bumps it, and any handler
 *  carrying an old stamp is ignored. Queueing one utterance at a time rather
 *  than all of them keeps the amount cancel() has to clear down to one.
 *
 *  `mouth` is a 0-1 signal the avatar reads. speechSynthesis exposes no audio
 *  node - the audio never enters an AudioContext - so it is driven from the
 *  utterance's own `boundary` events, which fire per word in Chrome.
 */
export function useVoice(options: {
  voice: VoicePreference;
  onTranscript: (text: string) => void;
}) {
  const { onTranscript } = options;
  const [state, setState] = useState<VoiceState>("idle");
  const [partial, setPartial] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceName, setVoiceName] = useState<string | null>(null);

  const listener = useRef<Listener | null>(null);
  const chosen = useRef<SpeechSynthesisVoice | null>(null);
  const buffer = useRef("");
  const streamDone = useRef(true);

  // Everything in flight carries this stamp. Cancelling bumps it, which
  // invalidates every queued utterance and every pending callback at once.
  const generation = useRef(0);
  // Sentences waiting their turn. We hand speechSynthesis one at a time.
  const pending = useRef<string[]>([]);
  const speakingNow = useRef(false);

  const mouth = useRef(0);
  const decay = useRef<number | null>(null);

  const { pitch, rate } = options.voice;
  const preferKey = options.voice.prefer.join("|");

  useEffect(() => {
    let alive = true;
    void voicesReady().then((available) => {
      if (!alive) return;
      setVoices(usableVoices(available));
      const picked = pickVoice(available, preferKey ? preferKey.split("|") : []);
      chosen.current = picked;
      setVoiceName(picked?.name ?? null);
    });
    return () => {
      alive = false;
    };
  }, [preferKey]);

  /** Let the caller choose a voice - quality varies wildly by device. */
  const selectVoice = useCallback(
    (name: string) => {
      const hit = voices.find((v) => v.name === name);
      if (!hit) return;
      chosen.current = hit;
      setVoiceName(name);
    },
    [voices],
  );

  const runDecay = useCallback(() => {
    if (decay.current !== null) return;
    const tick = () => {
      mouth.current *= 0.82;
      if (mouth.current < 0.01) {
        mouth.current = 0;
        decay.current = null;
        return;
      }
      decay.current = requestAnimationFrame(tick);
    };
    decay.current = requestAnimationFrame(tick);
  }, []);

  /** Hard stop. Safe to call from anywhere, at any point in the loop. */
  const stopSpeaking = useCallback(() => {
    generation.current += 1;
    pending.current = [];
    speakingNow.current = false;
    buffer.current = "";
    mouth.current = 0;
    if (speechSupported.speaking) {
      // Chrome can leave a paused queue behind; resume() first so cancel()
      // has something to actually flush.
      try {
        speechSynthesis.resume();
      } catch {
        /* not all engines implement it */
      }
      speechSynthesis.cancel();
      // One more pass on the next tick: an utterance that started in the same
      // frame as the cancel sometimes survives the first call.
      window.setTimeout(() => speechSynthesis.cancel(), 60);
    }
  }, []);

  const drain = useCallback(() => {
    if (!speechSupported.speaking || muted) return;
    if (speakingNow.current) return;
    const next = pending.current.shift();
    if (next === undefined) {
      if (streamDone.current) {
        mouth.current = 0;
        setState("idle");
      }
      return;
    }

    const stamp = generation.current;
    const utterance = new SpeechSynthesisUtterance(next);
    if (chosen.current) utterance.voice = chosen.current;
    utterance.pitch = pitch;
    utterance.rate = rate;

    const finish = () => {
      if (stamp !== generation.current) return; // cancelled: stay stopped
      speakingNow.current = false;
      drain();
    };

    utterance.onstart = () => {
      if (stamp !== generation.current) return;
      setState("speaking");
    };
    utterance.onboundary = () => {
      if (stamp !== generation.current) return;
      mouth.current = Math.min(1, 0.55 + Math.random() * 0.45);
      runDecay();
    };
    utterance.onend = finish;
    utterance.onerror = finish;

    speakingNow.current = true;
    speechSynthesis.speak(utterance);
  }, [muted, pitch, rate, runDecay]);

  const enqueue = useCallback(
    (text: string) => {
      if (!text.trim() || muted) return;
      pending.current.push(text.trim());
      drain();
    },
    [drain, muted],
  );

  /** Feed streamed text in as it arrives; complete sentences get spoken. */
  const pushText = useCallback(
    (delta: string) => {
      buffer.current += delta;
      const { chunks, rest } = takeSpeakable(buffer.current);
      buffer.current = rest;
      chunks.forEach(enqueue);
    },
    [enqueue],
  );

  const beginStream = useCallback(() => {
    streamDone.current = false;
    buffer.current = "";
    setState("thinking");
  }, []);

  const endStream = useCallback(() => {
    streamDone.current = true;
    const tail = buffer.current.trim();
    buffer.current = "";
    if (tail) enqueue(tail);
    else if (!speakingNow.current && pending.current.length === 0) setState("idle");
  }, [enqueue]);

  const stopListening = useCallback(() => {
    listener.current?.stop();
    listener.current = null;
  }, []);

  const startListening = useCallback(() => {
    setError(null);
    if (!speechSupported.listening) {
      setError("This browser has no speech recognition. Chrome or Edge will work.");
      return;
    }
    // Barge-in: talking over the reply stops it, as it would with a person.
    stopSpeaking();
    setPartial("");
    setState("listening");

    listener.current = listen({
      onPartial: setPartial,
      onFinal: (text) => {
        setPartial("");
        setState("thinking");
        onTranscript(text);
      },
      onError: (reason) => {
        setError(reason);
        setState("idle");
      },
      onEnd: () => {
        listener.current = null;
        setState((current) => (current === "listening" ? "idle" : current));
      },
    });
    if (!listener.current) {
      setError("Could not start the microphone.");
      setState("idle");
    }
  }, [onTranscript, stopSpeaking]);

  const cancelAll = useCallback(() => {
    listener.current?.abort();
    listener.current = null;
    stopSpeaking();
    streamDone.current = true;
    setPartial("");
    setState("idle");
  }, [stopSpeaking]);

  // Escape stops everything, wherever focus happens to be.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelAll();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cancelAll]);

  useEffect(
    () => () => {
      listener.current?.abort();
      generation.current += 1;
      if (speechSupported.speaking) speechSynthesis.cancel();
      if (decay.current !== null) cancelAnimationFrame(decay.current);
    },
    [],
  );

  return {
    state,
    partial,
    error,
    muted,
    setMuted: (next: boolean) => {
      setMuted(next);
      if (next) stopSpeaking();
    },
    voices,
    voiceName,
    selectVoice,
    mouth,
    supported: { listening: speechSupported.listening, speaking: speechSupported.speaking },
    startListening,
    stopListening,
    beginStream,
    pushText,
    endStream,
    cancelAll,
  };
}
