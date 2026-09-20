import { useCallback, useEffect, useRef, useState } from "react";
import {
  listen,
  pickVoice,
  speechSupported,
  takeSpeakable,
  voicesReady,
  type Listener,
  type VoicePreference,
} from "./speech";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

/** The conversation loop: listen, hand the transcript up, speak what comes back.
 *
 *  `mouth` is a 0-1 signal the avatar reads. speechSynthesis gives no audio
 *  node to analyse - the audio never enters an AudioContext - so it is driven
 *  from the utterance's own `boundary` events, which fire per word in Chrome,
 *  shaped into an envelope. That tracks real speech rhythm rather than faking
 *  a waveform, and degrades to a steady pulse where boundary events are absent.
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

  const listener = useRef<Listener | null>(null);
  const chosen = useRef<SpeechSynthesisVoice | null>(null);
  const buffer = useRef("");
  const queued = useRef(0);
  const streamDone = useRef(true);

  // The mouth signal lives in a ref so the render loop can read it every frame
  // without re-rendering React sixty times a second.
  const mouth = useRef(0);
  const decay = useRef<number | null>(null);

  const prefer = options.voice.prefer;
  const preferKey = prefer.join("|");
  useEffect(() => {
    let alive = true;
    void voicesReady().then((voices) => {
      if (alive) chosen.current = pickVoice(voices, preferKey ? preferKey.split("|") : []);
    });
    return () => {
      alive = false;
    };
  }, [preferKey]);

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

  const stopSpeaking = useCallback(() => {
    if (speechSupported.speaking) speechSynthesis.cancel();
    queued.current = 0;
    buffer.current = "";
    mouth.current = 0;
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!speechSupported.speaking || muted || !text.trim()) return;
      const utterance = new SpeechSynthesisUtterance(text);
      if (chosen.current) utterance.voice = chosen.current;
      utterance.pitch = options.voice.pitch;
      utterance.rate = options.voice.rate;

      utterance.onstart = () => setState("speaking");
      // Fires per word in Chrome: a real rhythm rather than a fake waveform.
      utterance.onboundary = () => {
        mouth.current = Math.min(1, 0.55 + Math.random() * 0.45);
        runDecay();
      };
      utterance.onend = utterance.onerror = () => {
        queued.current = Math.max(0, queued.current - 1);
        if (queued.current === 0 && streamDone.current) {
          mouth.current = 0;
          setState("idle");
        }
      };

      queued.current += 1;
      speechSynthesis.speak(utterance);
    },
    [muted, options.voice.pitch, options.voice.rate, runDecay],
  );

  /** Feed streamed text in as it arrives; complete sentences get spoken. */
  const pushText = useCallback(
    (delta: string) => {
      buffer.current += delta;
      const { chunks, rest } = takeSpeakable(buffer.current);
      buffer.current = rest;
      chunks.forEach(speak);
    },
    [speak],
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
    if (tail) speak(tail);
    else if (queued.current === 0) setState("idle");
  }, [speak]);

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

  useEffect(
    () => () => {
      listener.current?.abort();
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
