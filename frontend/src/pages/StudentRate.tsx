import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Technique } from "../api/types";
import { humanize } from "../api/vocab";
import { Badge, Button, Card, ErrorNote, Field, Loading, cx } from "../components/ui";

const TEXTAREA =
  "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line " +
  "placeholder:text-slate-400 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500";

export default function StudentRate() {
  const { token = "" } = useParams();
  const [tech, setTech] = useState<Technique | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.previewRate(token);
        if (!cancelled) setTech(data);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (rating < 1) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.submitRate(token, {
        rating,
        comment: comment.trim() || null,
      });
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-line/80 bg-paper/90 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-lg items-center gap-2.5 px-4">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-600 text-sm text-white shadow-sm">
            E
          </span>
          <span className="font-semibold tracking-tight text-ink">EduMatch</span>
          <span className="text-sm text-muted">· Student feedback</span>
        </div>
      </header>

      <main className="mx-auto max-w-lg px-4 py-10">
        {loading ? (
          <Loading label="Loading" />
        ) : done ? (
          <Card className="p-8 text-center">
            <p className="text-lg font-semibold text-ink">Thanks — feedback sent</p>
            <p className="mt-2 text-sm text-muted">
              Your rating is anonymous. You can close this page.
            </p>
          </Card>
        ) : !tech ? (
          <Card className="p-8 text-center">
            <p className="font-semibold text-ink">Link unavailable</p>
            <p className="mt-2 text-sm text-muted">
              This rating link may have expired or already been used up.
            </p>
            <div className="mt-4">
              <ErrorNote error={error} />
            </div>
          </Card>
        ) : (
          <>
            <div className="mb-6">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-indigo-600">
                Rate this technique
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">{tech.title}</h1>
              <p className="mt-2 text-sm leading-6 text-muted">{tech.summary}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {tech.problem_types.map((ptype) => (
                  <Badge key={ptype} tone="amber">
                    {humanize(ptype)}
                  </Badge>
                ))}
              </div>
            </div>

            <Card className="p-5">
              <form onSubmit={submit} className="space-y-4">
                <ErrorNote error={error} />
                <div>
                  <p className="mb-2 text-sm font-semibold text-ink">How helpful was this?</p>
                  <div className="flex gap-1">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setRating(n)}
                        className={cx(
                          "press text-3xl leading-none",
                          n <= rating ? "text-amber-500" : "text-slate-300 hover:text-amber-300",
                        )}
                        aria-label={`${n} star${n === 1 ? "" : "s"}`}
                      >
                        ★
                      </button>
                    ))}
                  </div>
                </div>
                <Field label="Comment (optional)">
                  <textarea
                    className={TEXTAREA}
                    rows={3}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="What worked? What was confusing?"
                    maxLength={1000}
                  />
                </Field>
                <Button type="submit" loading={submitting} disabled={rating < 1} className="w-full">
                  Submit rating
                </Button>
                <p className="text-center text-xs text-muted">
                  No account needed. Ratings are anonymous.
                </p>
              </form>
            </Card>
          </>
        )}

        <p className="mt-8 text-center text-xs text-muted">
          <Link to="/" className="font-medium text-indigo-600 hover:text-indigo-700">
            EduMatch
          </Link>{" "}
          for educators
        </p>
      </main>
    </div>
  );
}
