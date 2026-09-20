import { Suspense, lazy, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ChatTurn, Mentor } from "../api/types";
import { humanize } from "../api/vocab";
import { MentorConversation } from "../components/MentorConversation";
import {
  Avatar,
  Button,
  Badge,
  Card,
  ErrorNote,
  Loading,
  SectionHeading,
  Spinner,
} from "../components/ui";

const VoiceMode = lazy(() =>
  import("../voice/VoiceMode").then((m) => ({ default: m.VoiceMode })),
);
const MeetingRoom = lazy(() =>
  import("../voice/MeetingRoom").then((m) => ({ default: m.MeetingRoom })),
);

/** An educator's profile, with the conversation on it.
 *
 *  Same shape as a member's profile deliberately: who they are, what they
 *  teach, what they are worth talking to about - and then the conversation, as
 *  one section of the page rather than the whole of it. A mentor is a person
 *  you visit, not a chat widget.
 *
 *  What a member profile does not have, and this does, is provenance: where
 *  everything on the page came from, and what the person agreed to.
 */
export default function MentorProfile() {
  const { slug } = useParams();
  const navigate = useNavigate();

  const [mentors, setMentors] = useState<Mentor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [inMeeting, setInMeeting] = useState(false);

  const mentor = slug ? mentors.find((m) => m.slug === slug) : mentors[0];

  useEffect(() => {
    api.mentors().then(setMentors).catch(setError).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setTurns([]);
    setMode("text");
    setInMeeting(false);
  }, [slug]);

  if (loading) return <Loading label="Opening the profile" />;
  if (!mentor) {
    return (
      <Card className="p-10 text-center">
        <p className="text-sm text-muted">
          {slug ? "There is no mentor at that address." : "No mentors are configured here."}
        </p>
        <ErrorNote error={error} />
        <Link className="mt-4 inline-block text-sm font-medium text-indigo-700" to="/mentor">
          See who is available
        </Link>
      </Card>
    );
  }

  const guide = mentor.mode === "guide";
  const ready = mentor.available && mentor.has_material;
  const canSpeak = Boolean(mentor.voice?.enabled && mentor.avatar?.enabled && ready);

  if (inMeeting) {
    return (
      <Suspense
        fallback={
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950">
            <span className="inline-flex items-center gap-2 text-sm text-white/50">
              <Spinner className="h-4 w-4" />
              Connecting…
            </span>
          </div>
        }
      >
        <MeetingRoom
          mentor={mentor}
          turns={turns}
          onTurns={setTurns}
          onLeave={() => setInMeeting(false)}
        />
      </Suspense>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="press inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-ink"
        >
          <span aria-hidden>←</span> Back
        </button>
        {mentors.length > 1 && (
          <div className="flex flex-wrap gap-1.5">
            {mentors
              .filter((m) => m.slug !== mentor.slug)
              .map((other) => (
                <Link
                  key={other.slug}
                  to={`/mentor/${other.slug}`}
                  className="press flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-muted ring-1 ring-line hover:text-ink"
                >
                  <Avatar name={other.avatar_seed || other.name} src={other.avatar_url} size={18} />
                  {other.name}
                </Link>
              ))}
          </div>
        )}
      </div>

      {/* --- identity ---------------------------------------------------- */}
      <Card className="overflow-hidden">
        <div className="h-24 bg-gradient-to-r from-indigo-100 via-blue-50 to-emerald-50" />
        <div className="-mt-8 p-6 sm:p-8">
          <div className="flex flex-wrap items-start gap-4">
            <div className="rounded-full bg-white p-1.5 shadow-sm">
              <Avatar name={mentor.avatar_seed || mentor.name} src={mentor.avatar_url} size={72} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mt-8 flex flex-wrap items-center gap-2 sm:mt-9">
                <h1 className="text-2xl font-semibold tracking-tight text-ink">{mentor.name}</h1>
                <Badge tone="indigo">{guide ? "AI guide" : "AI persona"}</Badge>
              </div>
              <p className="mt-0.5 text-sm text-muted">
                {[mentor.title, mentor.institution, mentor.location_name]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {mentor.known_for && (
                <p className="mt-2 text-sm text-ink/80">Known for {mentor.known_for}</p>
              )}
            </div>
          </div>

          {mentor.tagline && (
            <blockquote className="mt-6 max-w-3xl rounded-xl bg-indigo-50/70 p-4 text-sm leading-6 text-indigo-950 ring-1 ring-indigo-100">
              <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-indigo-600">
                In short
              </span>
              {mentor.tagline}
            </blockquote>
          )}

          {canSpeak && (
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button onClick={() => setInMeeting(true)}>
                <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="6" width="13" height="12" rx="2.5" />
                  <path d="m15 11 6-3.5v9L15 13" />
                </svg>
                Meet {mentor.name.split(" ").slice(-1)[0]}
              </Button>
              <p className="text-xs text-muted">
                Face to face, out loud — an AI persona, not him.
              </p>
            </div>
          )}

          {mentor.subjects.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-1.5">
              {mentor.subjects.map((subject) => (
                <Badge key={subject} tone="neutral">
                  {humanize(subject)}
                </Badge>
              ))}
              {mentor.years_experience && (
                <Badge tone="amber">{mentor.years_experience} years teaching</Badge>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* --- the conversation, as a section of the profile ---------------- */}
      <Card className="p-6 sm:p-7">
        <SectionHeading
          title={guide ? `Ask about ${mentor.name.split(" ").slice(-1)[0]}'s teaching` : "Talk to them"}
          description={
            guide
              ? "Answered from cited sources, or not at all."
              : "Type, or switch to voice and talk."
          }
          trailing={
            canSpeak ? (
              <div className="inline-flex shrink-0 rounded-full bg-slate-100 p-1">
                {(["text", "voice"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setMode(option)}
                    className={
                      "press rounded-full px-3 py-1 text-sm font-medium capitalize " +
                      (mode === option ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink")
                    }
                  >
                    {option}
                  </button>
                ))}
              </div>
            ) : undefined
          }
        />

        {mode === "voice" && canSpeak ? (
          <Suspense
            fallback={
              <div className="grid h-72 place-items-center rounded-2xl bg-slate-950 ring-1 ring-slate-800 sm:h-96">
                <span className="inline-flex items-center gap-2 text-sm text-white/50">
                  <Spinner className="h-4 w-4" />
                  Waking them up…
                </span>
              </div>
            }
          >
            <VoiceMode mentor={mentor} turns={turns} onTurns={setTurns} />
          </Suspense>
        ) : (
          <MentorConversation mentor={mentor} turns={turns} onTurns={setTurns} />
        )}
      </Card>

      {/* --- what they are worth talking about --------------------------- */}
      {mentor.collaborates_on.length > 0 && (
        <Card className="p-6 sm:p-7">
          <SectionHeading
            title="Worth asking about"
            description="What they have most to say on."
          />
          <ul className="grid gap-2 sm:grid-cols-2">
            {mentor.collaborates_on.map((topic) => (
              <li
                key={topic}
                className="flex gap-2 rounded-xl bg-emerald-50/60 p-3 text-sm text-ink ring-1 ring-emerald-100"
              >
                <span aria-hidden className="text-emerald-600">
                  ✓
                </span>
                {topic}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* --- provenance: the part a member profile does not have ---------- */}
      <Card className="p-6 sm:p-7">
        <SectionHeading
          title="Where this comes from"
          description="Everything this persona can say, and what it is allowed to say it from."
        />

        {mentor.sources.length > 0 ? (
          <ul className="space-y-2">
            {mentor.sources.map((source) => (
              <li key={source.id} className="flex gap-3 text-sm leading-6">
                <span className="mt-0.5 shrink-0 font-mono text-[11px] text-indigo-700">
                  [{source.id}]
                </span>
                <span className="text-ink/85">
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
                  {source.kind !== "other" && (
                    <span className="ml-2 text-xs text-muted">{source.kind}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-xl bg-amber-50 p-3 text-sm leading-6 text-amber-800 ring-1 ring-amber-100">
            No sources have been loaded yet, so this persona will decline every question about{" "}
            {mentor.name.split(" ").slice(-1)[0]} rather than answer from memory.
          </p>
        )}

        {mentor.disclaimer && (
          <p className="mt-5 border-t border-line pt-4 text-xs leading-5 text-muted">
            <strong className="font-semibold text-ink/70">
              {guide ? "Not affiliated." : "AI persona."}
            </strong>{" "}
            {mentor.disclaimer}
          </p>
        )}
      </Card>
    </div>
  );
}
