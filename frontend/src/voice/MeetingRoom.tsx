import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { streamMentorChat } from "../api/client";
import type { ChatTurn, Mentor } from "../api/types";
import { useVoice } from "./useVoice";

const RiggedAvatar = lazy(() =>
  import("./RiggedAvatar").then((m) => ({ default: m.RiggedAvatar })),
);
const CharacterAvatar = lazy(() =>
  import("./CharacterAvatar").then((m) => ({ default: m.CharacterAvatar })),
);
const PortraitAvatar = lazy(() =>
  import("./PortraitAvatar").then((m) => ({ default: m.PortraitAvatar })),
);

function elapsed(from: number): string {
  const s = Math.floor((Date.now() - from) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** A call with a mentor: full screen, their face, press to talk.
 *
 *  A call UI implies a person on the other end, so the framing has to work
 *  harder here than anywhere else in the product - the banner says what this
 *  is and does not scroll away, and the figure is labelled underneath. Being
 *  unmistakable is what makes the format usable at all.
 */
export function MeetingRoom({
  mentor,
  turns,
  onTurns,
  onLeave,
}: {
  mentor: Mentor;
  turns: ChatTurn[];
  onTurns: (next: ChatTurn[]) => void;
  onLeave: () => void;
}) {
  const [live, setLive] = useState("");
  const [searching, setSearching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [since] = useState(() => Date.now());
  const [clock, setClock] = useState("0:00");
  const [view, setView] = useState<"avatar" | "portrait">("avatar");

  const abort = useRef<AbortController | null>(null);
  const turnsRef = useRef(turns);
  turnsRef.current = turns;
  const voice = useRef<ReturnType<typeof useVoice> | null>(null);

  const avatar = mentor.avatar ?? { kind: "stylised" as const, accent: "#4f46e5", model_url: "" };
  const hasPortrait = avatar.kind === "likeness" && !!mentor.avatar_url;

  useEffect(() => {
    const id = window.setInterval(() => setClock(elapsed(since)), 1000);
    return () => window.clearInterval(id);
  }, [since]);

  const v = useVoice({
    mentorSlug: mentor.slug,
    voice: {
      prefer: mentor.voice?.prefer ?? [],
      pitch: mentor.voice?.pitch ?? 1,
      rate: mentor.voice?.rate ?? 1,
    },
    onTranscript: (text) => void ask(text),
  });
  voice.current = v;

  async function ask(question: string) {
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
        setError((err as Error)?.message ?? "The call dropped.");
        onTurns(turnsRef.current);
      }
    } finally {
      voice.current?.endStream();
      setLive("");
      setSearching(null);
      abort.current = null;
    }
  }

  const leave = () => {
    abort.current?.abort();
    v.cancelAll();
    onLeave();
  };

  // Escape leaves the call. useVoice also listens for it to stop speech, which
  // is the right order: the first press stops him talking, the second leaves.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && v.state === "idle") leave();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => () => abort.current?.abort(), []);

  const busy = v.state === "thinking" || v.state === "speaking";
  const lastReply = [...turns].reverse().find((t) => t.role === "assistant")?.content ?? "";
  const caption = v.partial || live || lastReply;
  const avatarClass = "h-full w-full";

  // Portalled to <body> on purpose. The page's <main> animates with a
  // transform, and a transformed ancestor makes `position: fixed` resolve
  // against that ancestor rather than the viewport - so in place, this
  // rendered inside the page with the header showing through and no viewport
  // height for the column to fill.
  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950">
      {/* What this is. Does not scroll away. */}
      <div className="shrink-0 bg-amber-500/10 px-4 py-2 text-center text-xs text-amber-200/90 ring-1 ring-inset ring-amber-400/20">
        This is an AI persona of {mentor.name}, not a call with him. The voice is synthesised and
        is not his.
      </div>

      <div className="flex items-center justify-between px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-white/90">{mentor.name}</p>
          <p className="text-xs tabular-nums text-white/40">
            {v.state === "listening"
              ? "Listening…"
              : v.state === "thinking"
                ? searching !== null
                  ? "Looking it up…"
                  : "Thinking…"
                : v.state === "speaking"
                  ? "Speaking"
                  : clock}
          </p>
        </div>
        {hasPortrait && (
          <div className="flex rounded-full bg-white/10 p-0.5">
            {(["avatar", "portrait"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                className={
                  "press rounded-full px-2.5 py-1 text-[11px] font-medium capitalize " +
                  (view === option ? "bg-white/90 text-slate-900" : "text-white/60 hover:text-white")
                }
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Them */}
      <div className="relative min-h-0 flex-1">
        <Suspense fallback={<div className="grid h-full place-items-center text-sm text-white/40">Connecting…</div>}>
          {hasPortrait && view === "portrait" ? (
            <PortraitAvatar src={mentor.avatar_url} mouth={v.mouth} state={v.state} accent={avatar.accent} className={avatarClass} />
          ) : avatar.kind === "stylised" ? (
            <CharacterAvatar mouth={v.mouth} state={v.state} accent={avatar.accent} className={avatarClass} />
          ) : avatar.model_url ? (
            <RiggedAvatar src={avatar.model_url} mouth={v.mouth} state={v.state} accent={avatar.accent} className={avatarClass} />
          ) : (
            <CharacterAvatar mouth={v.mouth} state={v.state} accent={avatar.accent} className={avatarClass} />
          )}
        </Suspense>

        {/* Captions, the way a call shows them */}
        {(caption || error) && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 p-4 sm:p-6">
            <div className="mx-auto max-w-2xl rounded-2xl bg-black/55 px-4 py-3 backdrop-blur">
              {error ? (
                <p className="text-sm leading-6 text-rose-300">{error}</p>
              ) : (
                <p
                  className={
                    "max-h-28 overflow-y-auto text-sm leading-6 " +
                    (v.partial ? "italic text-white/55" : "text-white/90")
                  }
                >
                  {caption}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="shrink-0 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
        <div className="mx-auto flex max-w-2xl items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => v.setMuted(!v.muted)}
            className="press grid h-12 w-12 place-items-center rounded-full bg-white/10 text-white/80 hover:bg-white/20"
            aria-label={v.muted ? "Unmute" : "Mute"}
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
              {v.muted ? <><path d="M11 5 6 9H3v6h3l5 4V5Z" /><path d="m16 9 5 6M21 9l-5 6" /></> : <><path d="M11 5 6 9H3v6h3l5 4V5Z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /></>}
            </svg>
          </button>

          <button
            type="button"
            onClick={() => {
              if (busy) {
                abort.current?.abort();
                v.cancelAll();
              } else if (v.state === "listening") {
                v.stopListening();
              } else {
                void v.unlockAudio();
                v.startListening();
              }
            }}
            disabled={!v.supported.listening && !busy}
            className={
              "press grid h-16 w-16 place-items-center rounded-full transition " +
              (busy
                ? "bg-white text-slate-900 hover:bg-white/90"
                : v.state === "listening"
                  ? "bg-rose-500 text-white ring-4 ring-rose-500/25"
                  : "bg-white text-slate-900 hover:bg-white/90 disabled:opacity-40")
            }
            aria-label={busy ? "Stop" : v.state === "listening" ? "Stop listening" : "Talk"}
          >
            {busy ? (
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
                <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
              </svg>
            )}
          </button>

          <button
            type="button"
            onClick={leave}
            className="press grid h-12 w-12 place-items-center rounded-full bg-rose-500 text-white hover:bg-rose-600"
            aria-label="Leave"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
              <path d="M3 10c5-4 13-4 18 0l-2.5 3-4-1.5V9a12 12 0 0 0-5 0v2.5L5.5 13 3 10Z" />
            </svg>
          </button>
        </div>
        <p className="mt-3 text-center text-[11px] text-white/35">
          {v.supported.listening
            ? "Tap to talk · talking over him interrupts · Escape to leave"
            : "Speech recognition needs Chrome or Edge"}
        </p>
      </div>
    </div>,
    document.body,
  );
}
