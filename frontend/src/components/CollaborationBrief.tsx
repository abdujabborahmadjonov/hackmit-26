import { useState } from "react";
import { api } from "../api/client";
import { Button, ErrorNote, Spinner } from "./ui";

/** "Why this match" answers the ranking. This answers what to do about it. */
export function CollaborationBrief({ teacherId, teacherName }: { teacherId: string; teacherName: string }) {
  const [brief, setBrief] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.collaborationBrief(teacherId);
      setBrief(result.brief);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  if (brief) {
    return (
      <div className="rise mt-4 rounded-lg bg-indigo-50/60 p-4 ring-1 ring-indigo-100">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">
          What you two could do together
        </p>
        <p className="mt-2 whitespace-pre-line text-sm leading-6 text-ink">{brief}</p>
        <p className="mt-3 text-xs text-muted">
          Written from both profiles and {teacherName.split(" ")[0]}'s shared materials — not from
          anything outside them.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <Button size="sm" variant="secondary" onClick={generate} disabled={loading}>
        {loading ? (
          <>
            <Spinner className="h-4 w-4" />
            Drafting a plan…
          </>
        ) : (
          "Draft a collaboration plan"
        )}
      </Button>
      <div className="mt-2">
        <ErrorNote error={error} />
      </div>
    </div>
  );
}
