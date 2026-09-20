import { useCallback, useEffect, useRef, useState } from "react";
import { streamMentorChat } from "../api/client";
import type { ChatTurn, Mentor } from "../api/types";
import { Button } from "../components/ui";
import { Avatar3D } from "./Avatar3D";
import { useVoice } from "./useVoice";

const LABEL: Record<string, string> = {
  idle: "Tap to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking",
};

/** Voice conversation with a mentor.
 *
 *  Shares the transcript with the text chat, so switching modes mid-conversation
 *  keeps the thread. The reply is spoken sentence by sentence as it streams,
 *  which is the whole reason it feels like a conversation rather than a lookup. */
const DEFAULT_VOICE = { prefer: [] as string[], pitch: 1, rate: 1 };

export function VoiceMode({
  mentor,
  turns,
  onTurns,
}: {
  mentor: Mentor;
  turns: ChatTurn[];
  onTurns: (next: ChatTurn[]) => void;
}) {
  // An API older than this client sends no voice or avatar block. Fall back
  // rather than crashing the page - the two are deployed separately.
  const voiceConfig = mentor.voice ?? DEFAULT_VOICE;
  const avatarConfig = mentor.avatar ?? { kind: "stylised" as const, accent: "#4f46e5" };
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState("");
  const [searching, setSearching] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  // The loop reads the latest transcript without being re-created each turn.
  const turnsRef = useRef(turns);
  turnsRef.current = turns;

  const voice = useRef<ReturnType<typeof useVoice> | null>(null);

  const ask = useCallback(
    async (question: string) => {
      const history: ChatTurn[] = [...turnsRef.current, { role: "user", content: question }];
      onTurns(history);
      setError(null);
      setLive("");
      setSearching(null);

      const controller = new AbortController();
      abort.current = controller;
      let reply = "";

      voice.current?.beginStream();
      try {
        await streamMentorChat(mentor.slug, history, {
          signal: controller.signal,
          onDelta: (chunk) => {
            reply += chunk;
            setLive(reply);
            setSearching(null);
            voice.current?.pushText(chunk);
          },
          onSearching: (query) => setSearching(query ?? ""),
        });
        onTurns([...history, { role: "assistant", content: reply }]);
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          setError((err as Error)?.message ?? "The conversation dropped.");
          onTurns(turnsRef.current);
        }
      } finally {
        voice.current?.endStream();
        setLive("");
        setSearching(null);
        abort.current = null;
      }
    },
    [mentor.slug, onTurns],
  );

  const v = useVoice({
    voice: { prefer: voiceConfig.prefer, pitch: voiceConfig.pitch, rate: voiceConfig.rate },
    onTranscript: (text) => void ask(text),
  });
  voice.current = v;

  useEffect(
    () => () => {
      abort.current?.abort();
    },
    [],
  );

  const busy = v.state === "thinking" || v.state === "speaking";
  const lastReply = [...turns].reverse().find((t) => t.role === "assistant")?.content ?? "";
  const shown = live || lastReply;

  if (!v.supported.listening && !v.supported.speaking) {
    return (
      <div className="rounded-2xl bg-amber-50 p-6 text-sm text-amber-800 ring-1 ring-amber-100">
        This browser has no speech support. Chrome or Edge will work — or use the text
        conversation, which needs nothing special.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl bg-slate-950 ring-1 ring-slate-800">
      <div className="relative">
        <button
          type="button"
          onClick={() => {
            if (!busy) return;
            abort.current?.abort();
            v.cancelAll();
          }}
          className={"block w-full " + (busy ? "cursor-pointer" : "cursor-default")}
          aria-label={busy ? "Stop" : undefined}
          tabIndex={busy ? 0 : -1}
        >
          <Avatar3D
            mouth={v.mouth}
            state={v.state}
            accent={avatarConfig.accent}
            className="h-72 w-full sm:h-96"
          />
        </button>
        <div className="pointer-events-none absolute inset-x-0 top-4 text-center">
          <p className="text-sm font-medium text-white/90">{mentor.name}</p>
          <p className="text-xs text-white/45">
            {avatarConfig.kind === "stylised" ? "Abstract form — not a likeness" : "Likeness"}
            {mentor.voice?.clone_of ? " · cloned voice" : " · synthesised voice, not his"}
          </p>
        </div>
      </div>

      {/* what is being said, either direction */}
      <div className="min-h-[5.5rem] border-t border-slate-800 px-5 py-4">
        {searching !== null ? (
          <p className="text-sm leading-6 text-white/55 italic">
            {searching ? `Looking it up — ${searching}` : "Looking it up…"}
          </p>
        ) : v.partial ? (
          <p className="text-sm leading-6 text-white/55 italic">{v.partial}</p>
        ) : shown ? (
          <p className="max-h-32 overflow-y-auto whitespace-pre-line text-sm leading-6 text-white/85">
            {shown}
          </p>
        ) : (
          <p className="text-sm leading-6 text-white/35">{mentor.opening_line}</p>
        )}
        {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
        {v.error && <p className="mt-2 text-xs text-rose-300">{v.error}</p>}
      </div>

      <div className="flex items-center gap-3 border-t border-slate-800 px-5 py-4">
        {/* While he is talking the primary control IS stop - one large target,
            rather than a small ghost button off to the side. */}
        <button
          type="button"
          onClick={() => {
            if (busy) {
              abort.current?.abort();
              v.cancelAll();
            } else if (v.state === "listening") {
              v.stopListening();
            } else {
              v.startListening();
            }
          }}
          disabled={!v.supported.listening && !busy}
          className={
            "press flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition " +
            (busy
              ? "bg-white text-slate-900 hover:bg-white/90"
              : v.state === "listening"
                ? "bg-rose-500 text-white ring-4 ring-rose-500/25"
                : "bg-white text-slate-900 hover:bg-white/90 disabled:opacity-40")
          }
          aria-label={busy ? "Stop" : v.state === "listening" ? "Stop listening" : "Start talking"}
        >
          {busy ? (
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          )}
        </button>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-white/90">
            {busy ? "Stop" : LABEL[v.state]}
          </p>
          <p className="truncate text-xs text-white/40">
            {busy
              ? "Or press Escape. Talking over him also stops it."
              : v.supported.listening
                ? "Talking over him interrupts, the way it would with a person."
                : "Speech recognition needs Chrome or Edge."}
          </p>
        </div>

        {/* Voice quality varies enormously by device, so let them choose. */}
        {v.voices.length > 1 && (
          <select
            value={v.voiceName ?? ""}
            onChange={(event) => v.selectVoice(event.target.value)}
            className="max-w-[9.5rem] rounded-lg border-0 bg-white/10 px-2 py-1.5 text-xs text-white/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
            aria-label="Voice"
          >
            {v.voices.map((voice) => (
              <option key={voice.name} value={voice.name} className="text-ink">
                {voice.name}
              </option>
            ))}
          </select>
        )}

        <Button
          variant="ghost"
          size="sm"
          className="text-white/60 hover:bg-white/10 hover:text-white"
          onClick={() => v.setMuted(!v.muted)}
        >
          {v.muted ? "Unmute" : "Mute"}
        </Button>
      </div>
    </div>
  );
}
