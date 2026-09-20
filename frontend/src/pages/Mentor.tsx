import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, streamMentorChat } from "../api/client";
import type { MentorReplyEnd } from "../api/client";
import type { ChatTurn, Mentor as MentorPersona, MentorSource } from "../api/types";
import type { ResearchedPage } from "../api/client";
// Three.js is ~500kB and most visitors never open voice mode, so it is only
// fetched when someone actually switches to it.
const VoiceMode = lazy(() =>
  import("../voice/VoiceMode").then((m) => ({ default: m.VoiceMode })),
);
import {
  Avatar,
  Badge,
  Button,
  Card,
  ErrorNote,
  Loading,
  PageHeader,
  Spinner,
} from "../components/ui";

/** A turn plus whatever the reply cited. Citations are verified server-side,
 *  so what arrives here is already known to resolve to a real source. */
interface Turn extends ChatTurn {
  citations?: MentorSource[];
  unverified?: string[];
  researched?: ResearchedPage[];
}

/** A live conversation with a mentor.
 *
 *  Two shapes share this screen. A `first_person` persona speaks as the
 *  educator; a `guide` speaks about a real educator's published teaching and
 *  cites it, which is the only honest way to do this without their consent.
 *
 *  The API is stateless, so the transcript lives here and travels with every
 *  turn. `streaming` holds the reply as it arrives - it becomes a real turn
 *  only once the stream finishes, which keeps a dropped reply out of the
 *  history we send next time. */
export default function Mentor() {
  const { slug } = useParams();
  const navigate = useNavigate();

  const [mentors, setMentors] = useState<MentorPersona[]>([]);
  const [loading, setLoading] = useState(true);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);
  const [searching, setSearching] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [mode, setMode] = useState<"text" | "voice">("text");

  const abort = useRef<AbortController | null>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const busy = streaming !== null;

  // Pinned first, so no slug means the one the product is leading with.
  const mentor = slug ? mentors.find((m) => m.slug === slug) : mentors[0];

  useEffect(() => {
    api.mentors().then(setMentors).catch(setError).finally(() => setLoading(false));
    return () => abort.current?.abort();
  }, []);

  // Switching mentor starts a new conversation rather than handing one
  // person's transcript to another.
  useEffect(() => {
    abort.current?.abort();
    setTurns([]);
    setStreaming(null);
    setSearching(null);
    setError(null);
    setMode("text");
  }, [slug]);

  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" });
  }, [turns, streaming]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || !mentor || busy) return;

    const history: Turn[] = [...turns, { role: "user", content: question }];
    setTurns(history);
    setDraft("");
    setError(null);
    setStreaming("");
    setSearching(null);

    const controller = new AbortController();
    abort.current = controller;
    let reply = "";
    // A box, not a bare `let`: TypeScript does not track assignments made
    // inside the onEnd callback and narrows a plain variable to null.
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
      setTurns([
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
      // Keep whatever did arrive, but drop the question from the history if
      // nothing came back, so the next attempt is not answering it twice.
      if (reply) setTurns([...history, { role: "assistant", content: reply }]);
      else setTurns(turns);
    } finally {
      setStreaming(null);
      setSearching(null);
      abort.current = null;
      input.current?.focus();
    }
  }

  if (loading) return <Loading label="Finding your mentor" />;
  if (!mentor) {
    return (
      <>
        <PageHeader
          title="Ask a mentor"
          description={
            slug ? "That mentor does not exist." : "No mentors are configured on this deployment."
          }
        />
        <ErrorNote error={error} />
        {slug && mentors.length > 0 && (
          <Link className="text-sm font-medium text-indigo-700" to="/mentor">
            See who is available
          </Link>
        )}
      </>
    );
  }

  const guide = mentor.mode === "guide";
  const started = turns.length > 0 || busy;
  // A guide with no sources yet can introduce itself and nothing more.
  const ready = mentor.available && mentor.has_material;
  const lastName = mentor.name.split(" ").slice(-1)[0];

  return (
    <>
      <PageHeader
        eyebrow="EduMatch AI"
        title="Ask a mentor"
        description={
          guide
            ? `A guide to ${mentor.name}'s published teaching, answered with its sources.`
            : "A conversation with an experienced educator, live."
        }
      />

      {mentors.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {mentors.map((option) => (
            <button
              key={option.slug}
              type="button"
              onClick={() => navigate(`/mentor/${option.slug}`)}
              className={
                option.slug === mentor.slug
                  ? "press flex items-center gap-2 rounded-full bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white"
                  : "press flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-sm font-medium text-muted ring-1 ring-line hover:text-ink"
              }
            >
              <Avatar name={option.avatar_seed || option.name} src={option.avatar_url} size={20} />
              {option.name}
            </button>
          ))}
        </div>
      )}

      {mentor.voice?.enabled && mentor.avatar?.enabled && ready && (
        <div className="mb-4 inline-flex rounded-full bg-slate-100 p-1">
          {(["text", "voice"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMode(option)}
              className={
                "press rounded-full px-4 py-1.5 text-sm font-medium capitalize " +
                (mode === option ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink")
              }
            >
              {option}
            </button>
          ))}
        </div>
      )}

      {mode === "voice" ? (
        <Suspense
          fallback={
            <div className="grid h-72 place-items-center rounded-2xl bg-slate-950 ring-1 ring-slate-800 sm:h-96">
              <span className="inline-flex items-center gap-2 text-sm text-white/50">
                <Spinner className="h-4 w-4" />
                Waking him up…
              </span>
            </div>
          }
        >
          <VoiceMode
            mentor={mentor}
            turns={turns.map(({ role, content }) => ({ role, content }))}
            onTurns={(next) => setTurns(next)}
          />
        </Suspense>
      ) : (
      <Card className="overflow-hidden">
        {/* --- who you are talking to --- */}
        <div className="flex flex-wrap items-start gap-4 border-b border-line bg-slate-50/60 p-5">
          <Avatar name={mentor.avatar_seed || mentor.name} src={mentor.avatar_url} size={52} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold tracking-tight text-ink">
                {guide ? `Guide to ${mentor.name}` : mentor.name}
              </h2>
              <Badge tone="neutral">{guide ? "AI guide · not him" : "AI persona"}</Badge>
              {mentor.years_experience && (
                <Badge tone="neutral">{mentor.years_experience} years teaching</Badge>
              )}
            </div>
            <p className="mt-0.5 text-sm text-muted">
              {mentor.title} · {mentor.institution}
              {mentor.known_for && ` · ${mentor.known_for}`}
            </p>
            {mentor.tagline && <p className="mt-2 text-sm italic text-ink/80">{mentor.tagline}</p>}
            {guide && mentor.sources.length > 0 && (
              <p className="mt-2 text-xs text-muted">
                Drawing on {mentor.sources.length} source
                {mentor.sources.length === 1 ? "" : "s"}. Every claim is cited.
              </p>
            )}
          </div>
        </div>

        {/* --- transcript --- */}
        <div
          ref={transcript}
          className="flex max-h-[26rem] min-h-[18rem] flex-col gap-4 overflow-y-auto p-5"
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
                    ? "reading his material"
                    : searching
                      ? `searching the web — ${searching}`
                      : "searching the web…"}
                </span>
              )}
            </Bubble>
          )}

          {!started && mentor.suggested_questions.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {mentor.suggested_questions.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => send(question)}
                  disabled={!ready}
                  className="press rounded-full bg-white px-3 py-1.5 text-left text-xs text-muted ring-1 ring-line hover:bg-slate-50 hover:text-ink disabled:opacity-50"
                >
                  {question}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* --- composer --- */}
        <form
          className="border-t border-line p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void send(draft);
          }}
        >
          {!mentor.available && (
            <Notice>
              Mentor chat needs a model key on this deployment, so the conversation is read-only
              here.
            </Notice>
          )}
          {mentor.available && !mentor.has_material && (
            <Notice>
              This guide has no sources loaded yet. Rather than answer from memory about a real
              person, it stays quiet until its material is added.
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
              placeholder={
                guide
                  ? `Ask how ${lastName} teaches…`
                  : `Ask ${lastName} about your classroom…`
              }
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
      </Card>
      )}

      {mentor.disclaimer && (
        <p className="mt-3 px-1 text-xs leading-5 text-muted">
          <strong className="font-semibold text-ink/70">
            {guide ? "Not affiliated." : "AI persona."}
          </strong>{" "}
          {mentor.disclaimer}
        </p>
      )}
    </>
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
      <div className={mine ? "max-w-[85%]" : "max-w-[85%]"}>
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

        {/* Looked up mid-answer. Labelled as the persona's research rather
            than the educator's own material - the distinction is the point. */}
        {!!researched?.length && (
          <details className="mt-2 pl-1">
            <summary className="cursor-pointer text-xs text-muted hover:text-ink">
              Looked up {researched.length} source{researched.length === 1 ? "" : "s"} — not his
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
