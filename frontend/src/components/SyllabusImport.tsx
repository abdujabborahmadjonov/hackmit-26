import { useRef, useState, type DragEvent } from "react";
import { api } from "../api/client";
import type { ProfileDraft } from "../api/types";
import { humanize } from "../api/vocab";
import { Badge, Button, ErrorNote, Spinner, cx } from "./ui";

/** Drop a syllabus, get a filled-in profile to review. The fastest path past
 *  the twelve-field form, which is the dullest part of onboarding. */
export function SyllabusImport({ onExtract }: { onExtract: (draft: ProfileDraft) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [dragging, setDragging] = useState(false);
  const [applied, setApplied] = useState<ProfileDraft | null>(null);

  async function send(input: File | string) {
    setLoading(true);
    setError(null);
    try {
      const draft = await api.profileFromDocument(input);
      setApplied(draft);
      onExtract(draft);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void send(file);
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cx(
          "rounded-xl border-2 border-dashed p-6 text-center transition",
          dragging ? "border-indigo-400 bg-indigo-50/60" : "border-line bg-white",
        )}
      >
        {loading ? (
          <div className="flex items-center justify-center gap-3 py-2 text-sm text-muted">
            <Spinner className="h-5 w-5" />
            Reading your document…
          </div>
        ) : (
          <>
            <p className="text-sm font-medium text-ink">
              Drop a syllabus and skip the form
            </p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-muted">
              A syllabus, lesson plan or course outline — PDF, TXT or Markdown. We read how you
              teach and fill the fields below; nothing is saved until you submit.
            </p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-3"
              onClick={() => inputRef.current?.click()}
            >
              Choose a file
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt,.md,.markdown"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void send(file);
              }}
            />
          </>
        )}
      </div>

      <div className="mt-2">
        <ErrorNote error={error} />
      </div>

      {applied && (
        <div className="rise mt-3 rounded-lg bg-emerald-50 p-3 ring-1 ring-emerald-100">
          <p className="text-sm font-medium text-emerald-800">
            Filled in from {applied.source_name ?? "your document"} — review and edit below.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {applied.subjects.slice(0, 5).map((s) => (
              <Badge key={s} tone="emerald">
                {humanize(s)}
              </Badge>
            ))}
            {applied.teaching_methods.slice(0, 3).map((m) => (
              <Badge key={m} tone="indigo">
                {humanize(m)}
              </Badge>
            ))}
            <span className="ml-auto text-xs text-emerald-700">
              confidence: {applied.confidence}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
