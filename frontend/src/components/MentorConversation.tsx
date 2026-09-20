import { useEffect, useRef, useState } from "react";
import { streamMentorChat } from "../api/client";
import type { MentorReplyEnd, ResearchedPage } from "../api/client";
import type { ChatTurn, Mentor, MentorSource } from "../api/types";
import { Avatar, Button, ErrorNote, Spinner } from "./ui";

/** A turn plus whatever the reply cited. Citations are verified server-side,
 *  so what arrives here already resolves to a real source. */
interface Turn extends ChatTurn {
  citations?: MentorSource[];
  unverified?: string[];
  researched?: ResearchedPage[];
}

/** The text conversation with a mentor.
 *
 *  The API is stateless, so the transcript is owned by the page and passed in -
 *  which is what lets text and voice share one thread rather than two.
 *  `streaming` holds the reply as it arrives and only becomes a turn once the
 *  stream finishes, keeping a dropped reply out of the history sent next time. */
export function MentorConversation({
  mentor,
  turns,
  onTurns,
}: {
  mentor: Mentor;
  turns: Turn[];
  onTurns: (next: Turn[]) => void;
}) {
  const [streaming, setStreaming] = useState<string | null>(null);
  const [searching, setSearching] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<unknown>(null);

  const abort = useRef<AbortController | null>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const busy = streaming !== null;

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" });
  }, [turns, streaming]);

  const ready = mentor.available && mentor.has_material;
  const lastName = mentor.name.split(" ").slice(-1)[0];
  const guide = mentor.mode === "guide";

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;

    const history: Turn[] = [...turns, { role: "user", content: question }];
    onTurns(history);
    setDraft("");
    setError(null);
    setStreaming("");
    setSearching(null);

    const controller = new AbortController();
    abort.current = controller;
    let reply = "";
    // TypeScript does not track assignments made inside the onEnd callback.
    const finished: { end: MentorReplyEnd | null } = { end: null };

    try {
      await streamMentorChat(mentor.slug, history.map(({ role, content }) => ({ role, content })), {
        signal: controller.signal,
        onDelta: (chunk) => {
          reply += chunk;
          setStreaming(reply);
          setSearching(null);
        },
        onSearching: (query) => setSearching(query ?? ""),
        onEnd: (payload) => {
          finished.end = payload;
        },
      });
      onTurns([
        ...history,
        {
          role: "assistant",
          content: reply,
          citations: finished.end?.citations,
          unverified: finished.end?.unverified,
          researched: finished.end?.researched,
        },
      ]);
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      setError(err);
      // Keep whatever arrived; otherwise drop the question so the next attempt
      // is not answering it twice.
      if (reply) onTurns([...history, { role: "assistant", content: reply }]);
      else onTurns(turns);
    } finally {
      setStreaming(null);
      setSearching(null);
      abort.current = null;
      input.current?.focus();
    }
  }

  return (
    <div className="overflow-hidden rounded-2xl ring-1 ring-line">
      <div
        ref={transcript}
        className="flex max-h-[26rem] min-h-[15rem] flex-col gap-4 overflow-y-auto bg-white p-5"
      >
        <Bubble from="mentor" name={mentor.name} avatar={mentor.avatar_url}>
          {mentor.opening_line}
        </Bubble>

        {turns.map((turn, index) => (
          <Bubble
            key={index}
            from={turn.role === "user" ? "you" : "mentor"}
            name={mentor.name}
            avatar={mentor.avatar_url}
            citations={turn.citations}
            unverified={turn.unverified}
            researched={turn.researched}
          >
            {turn.content}
          </Bubble>
        ))}

        {busy && (
          <Bubble from="mentor" name={mentor.name} avatar={mentor.avatar_url}>
            {streaming ? (
              <>
                {streaming}
                <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-indigo-500 align-text-bottom" />
              </>
            ) : (
              <span className="inline-flex items-center gap-2 text-muted">
                <Spinner className="h-4 w-4" />
                {searching === null
                  ? "reading their material"
                  : searching
                    ? `searching the web — ${searching}`
                    : "searching the web…"}
              </span>
            )}
          </Bubble>
        )}

        {turns.length === 0 && !busy && mentor.suggested_questions.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {mentor.suggested_questions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => void send(question)}
                disabled={!ready}
                className="press rounded-full bg-white px-3 py-1.5 text-left text-xs text-muted ring-1 ring-line hover:bg-slate-50 hover:text-ink disabled:opacity-50"
              >
                {question}
              </button>
            ))}
          </div>
        )}
      </div>

      <form
        className="border-t border-line bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
      >
        {!mentor.available && (
          <Notice>
            This needs a model key on this deployment, so the conversation is read-only here.
          </Notice>
        )}
        {mentor.available && !mentor.has_material && (
          <Notice>
            No sources are loaded yet. Rather than answer from memory about a real person, this
            stays quiet until its material is added.
          </Notice>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={input}
            rows={2}
            value={draft}
            disabled={!ready || busy}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends, Shift+Enter is a newline - chat convention.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(draft);
              }
            }}
            placeholder={guide ? `Ask how ${lastName} teaches…` : `Ask ${lastName} something…`}
            className="min-h-[3rem] flex-1 resize-none rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line placeholder:text-muted/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:opacity-60"
          />
          {busy ? (
            <Button type="button" variant="secondary" onClick={() => abort.current?.abort()}>
              Stop
            </Button>
          ) : (
            <Button type="submit" disabled={!draft.trim() || !ready}>
              Send
            </Button>
          )}
        </div>
        <div className="mt-2">
          <ErrorNote error={error} />
        </div>
      </form>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-100">
      {children}
    </p>
  );
}

function Bubble({
  from,
  name,
  avatar,
  citations,
  unverified,
  researched,
  children,
}: {
  from: "you" | "mentor";
  name: string;
  avatar?: string;
  citations?: MentorSource[];
  unverified?: string[];
  researched?: ResearchedPage[];
  children: React.ReactNode;
}) {
  const mine = from === "you";
  return (
    <div className={mine ? "flex justify-end" : "flex gap-3"}>
      {!mine && <Avatar name={name} src={avatar} size={32} />}
      <div className="max-w-[85%]">
        <div
          className={
            mine
              ? "rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm leading-6 text-white"
              : "whitespace-pre-line rounded-2xl rounded-tl-sm bg-slate-100 px-4 py-2.5 text-sm leading-6 text-ink"
          }
        >
          {children}
        </div>

        {!!citations?.length && (
          <ul className="mt-2 space-y-1 pl-1">
            {citations.map((source) => (
              <li key={source.id} className="text-xs leading-5 text-muted">
                <span className="mr-1.5 font-mono text-[11px] text-indigo-700">[{source.id}]</span>
                {source.url ? (
                  <a
                    className="underline decoration-line underline-offset-2 hover:text-ink"
                    href={source.url}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {source.label}
                  </a>
                ) : (
                  source.label
                )}
              </li>
            ))}
          </ul>
        )}

        {/* Looked up mid-answer. Labelled as the persona's research rather than
            the educator's own material - the distinction is the point. */}
        {!!researched?.length && (
          <details className="mt-2 pl-1">
            <summary className="cursor-pointer text-xs text-muted hover:text-ink">
              Looked up {researched.length} source{researched.length === 1 ? "" : "s"} — not their
              own material
            </summary>
            <ul className="mt-1 space-y-1">
              {researched.map((page) => (
                <li key={page.url} className="text-xs leading-5 text-muted">
                  <a
                    className="underline decoration-line underline-offset-2 hover:text-ink"
                    href={page.url}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {page.title || page.url}
                  </a>
                </li>
              ))}
            </ul>
          </details>
        )}

        {/* The server could not match these keys to a source, so they are not
            presented as references. */}
        {!!unverified?.length && (
          <p className="mt-2 pl-1 text-xs leading-5 text-amber-700">
            Unverified reference{unverified.length === 1 ? "" : "s"}:{" "}
            {unverified.map((key) => `[${key}]`).join(" ")} — no matching source.
          </p>
        )}
      </div>
    </div>
  );
}
