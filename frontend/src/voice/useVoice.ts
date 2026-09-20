import { useCallback, useEffect, useRef, useState } from "react";
import { HostedSpeaker, hostedVoiceStatus } from "./hostedSpeech";
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
  mentorSlug: string;
  onTranscript: (text: string) => void;
}) {
  const { onTranscript } = options;
  const [state, setState] = useState<VoiceState>("idle");
  const [partial, setPartial] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceName, setVoiceName] = useState<string | null>(null);
  // Hosted speech sounds far better; the browser is the fallback, not the plan.
  const [hosted, setHosted] = useState<{ enabled: boolean; model: string | null }>({
    enabled: false,
    model: null,
  });

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
  const speaker = useRef<HostedSpeaker | null>(null);
  const meter = useRef<number | null>(null);
  // One sentence synthesised ahead of the one being spoken.
  const prefetched = useRef<{
    stamp: number;
    promise: Promise<AudioBuffer | null>;
    text: string;
  } | null>(null);

  const { mentorSlug } = options;
  useEffect(() => {
    let alive = true;
    void hostedVoiceStatus().then((status) => {
      if (alive) setHosted({ enabled: status.enabled, model: status.model });
    });
    speaker.current = new HostedSpeaker(mentorSlug);
    return () => {
      alive = false;
      void speaker.current?.dispose();
      speaker.current = null;
    };
  }, [mentorSlug]);

  /** Read the real waveform while hosted audio plays. */
  const runMeter = useCallback(() => {
    if (meter.current !== null) return;
    const tick = () => {
      const level = speaker.current?.level() ?? 0;
      // Rise fast, fall slow: a mouth, not an oscilloscope.
      mouth.current = level > mouth.current ? level : mouth.current * 0.86;
      if (mouth.current < 0.01 && level === 0) {
        mouth.current = 0;
        meter.current = null;
        return;
      }
      meter.current = requestAnimationFrame(tick);
    };
    meter.current = requestAnimationFrame(tick);
  }, []);

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
    speaker.current?.stop();
    prefetched.current = null;
    if (meter.current !== null) {
      cancelAnimationFrame(meter.current);
      meter.current = null;
    }
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

  /** Start synthesising the next sentence, if one is waiting and nothing is
   *  already in flight. Hosted speech takes ~1.5s per sentence, which is most
   *  of a sentence's playing time - so it has to overlap with playback or half
   *  the conversation is silence. */
  const startPrefetch = useCallback(() => {
    if (!hosted.enabled || !speaker.current) return;
    if (prefetched.current) return;
    const next = pending.current.shift();
    if (next === undefined) return;
    prefetched.current = {
      stamp: generation.current,
      // A failed sentence resolves to null and is skipped, rather than
      // rejecting and taking the rest of the reply with it.
      promise: speaker.current.prepare(next).catch(() => null),
      text: next,
    };
  }, [hosted.enabled]);

  const drain = useCallback(() => {
    if (muted || speakingNow.current) return;

    // --- hosted speech: real audio, real lip sync ---------------------------
    if (hosted.enabled && speaker.current) {
      startPrefetch();
      const job = prefetched.current;
      if (!job) {
        if (streamDone.current) {
          mouth.current = 0;
          setState("idle");
        }
        return;
      }
      prefetched.current = null;
      speakingNow.current = true;
      setState("speaking");

      void (async () => {
        const audio = await job.promise;
        if (job.stamp !== generation.current) return; // cancelled while waiting
        try {
          if (audio === null) {
            // Either this sentence failed, or the deployment lost its key. Put
            // it back once under the browser voice rather than dropping it.
            speakingNow.current = false;
            setHosted({ enabled: false, model: null });
            pending.current.unshift(job.text);
            drain();
            return;
          }
          // Get the next one cooking before this one starts playing.
          startPrefetch();
          runMeter();
          await speaker.current!.play(audio);
        } finally {
          if (job.stamp === generation.current) {
            speakingNow.current = false;
            drain();
          }
        }
      })();
      return;
    }

    // --- browser fallback ---------------------------------------------------
    if (!speechSupported.speaking) return;
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
  }, [hosted.enabled, muted, pitch, rate, runDecay, runMeter, startPrefetch]);

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
      if (meter.current !== null) cancelAnimationFrame(meter.current);
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
    hosted,
    /** Browsers block audio until a gesture - call from the click handler. */
    unlockAudio: () => speaker.current?.unlock(),
    mouth,
    supported: {
      listening: speechSupported.listening,
      speaking: speechSupported.speaking || hosted.enabled,
    },
    startListening,
    stopListening,
    beginStream,
    pushText,
    endStream,
    cancelAll,
  };
}
