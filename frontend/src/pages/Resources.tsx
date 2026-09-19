import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { RecommendedResource, Resource } from "../api/types";
import {
  ALLOWED_UPLOAD_EXTENSIONS,
  DIFFICULTIES,
  EDUCATION_LEVELS,
  RESOURCE_TYPES,
  SUBJECTS,
  TEACHING_METHODS,
  humanize,
} from "../api/vocab";
import { useAuth } from "../auth/AuthContext";
import { Badge, Button, Card, ErrorNote, Field, Input, Loading, Select, cx } from "../components/ui";

const ACCEPT = ALLOWED_UPLOAD_EXTENSIONS.join(",");
const MAX_UPLOAD_MB = 25;

function formatBytes(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ResourceRow({
  resource,
  score,
  reasons,
  onDelete,
  deleting,
}: {
  resource: Resource;
  score?: number;
  reasons?: string[];
  onDelete?: () => void;
  deleting?: boolean;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-ink">{resource.title}</p>
          {resource.description && (
            <p className="mt-0.5 text-sm text-muted">{resource.description}</p>
          )}
          {resource.file_name && (
            <p className="mt-1 text-xs text-muted">
              {resource.file_name}
              {resource.file_size_bytes ? ` · ${formatBytes(resource.file_size_bytes)}` : ""}
            </p>
          )}
        </div>
        {score !== undefined && (
          <span className="shrink-0 rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">
            {Math.round(score * 100)}% fit
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {resource.resource_type && <Badge tone="indigo">{humanize(resource.resource_type)}</Badge>}
        {resource.subject && <Badge tone="emerald">{humanize(resource.subject)}</Badge>}
        {resource.education_level && <Badge tone="amber">{humanize(resource.education_level)}</Badge>}
        {resource.teaching_method && <Badge>{humanize(resource.teaching_method)}</Badge>}
        {resource.difficulty && <Badge>{humanize(resource.difficulty)}</Badge>}
        {resource.file_url && (
          <a
            href={resource.file_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
          >
            Download
          </a>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            disabled={deleting}
            className="text-xs font-medium text-rose-600 hover:text-rose-700 disabled:opacity-50"
          >
            {deleting ? "Removing…" : "Delete"}
          </button>
        )}
      </div>
      {reasons && reasons.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {reasons.map((reason) => (
            <li key={reason} className="text-xs text-muted">
              · {reason}
            </li>
          ))}
        </ul>
      )}
      <Link
        to={`/teachers/${resource.owner_id}`}
        className="mt-2 inline-block text-xs text-muted hover:text-indigo-700"
      >
        View the educator who made this →
      </Link>
    </Card>
  );
}

type Tab = "foryou" | "browse" | "mine" | "upload";

const EMPTY_UPLOAD = {
  title: "",
  description: "",
  resource_type: "",
  subject: "",
  education_level: "",
  difficulty: "",
  teaching_method: "",
  tags: "",
};

export default function Resources() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("foryou");
  const [recommended, setRecommended] = useState<RecommendedResource[]>([]);
  const [browse, setBrowse] = useState<{ resource: Resource; score: number }[]>([]);
  const [mine, setMine] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [subject, setSubject] = useState("");
  const [level, setLevel] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const [uploadForm, setUploadForm] = useState(EMPTY_UPLOAD);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadRecommended = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRecommended(await api.recommendedResources(8));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBrowse = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.resources({
        query: query || undefined,
        subject: subject || undefined,
        education_level: level || undefined,
        sort: query ? "relevance" : "newest",
        limit: 20,
      });
      setBrowse(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [query, subject, level]);

  const loadMine = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.resources({
        owner_id: user.id,
        sort: "newest",
        limit: 50,
      });
      setMine(data.items.map((item) => item.resource));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (tab === "foryou") void loadRecommended();
    else if (tab === "browse") void loadBrowse();
    else if (tab === "mine") void loadMine();
    else {
      setLoading(false);
      setError(null);
    }
  }, [tab, loadRecommended, loadBrowse, loadMine]);

  function setUploadField<K extends keyof typeof EMPTY_UPLOAD>(key: K, value: string) {
    setUploadForm((current) => ({ ...current, [key]: value }));
    setUploadSuccess(null);
  }

  async function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError(new Error("Choose a file to upload"));
      return;
    }
    const extension = file.name.includes(".")
      ? `.${file.name.split(".").pop()!.toLowerCase()}`
      : "";
    if (!(ALLOWED_UPLOAD_EXTENSIONS as readonly string[]).includes(extension)) {
      setError(
        new Error(
          `Unsupported file type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(", ")}`,
        ),
      );
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(new Error(`File exceeds the ${MAX_UPLOAD_MB} MB limit`));
      return;
    }

    setUploading(true);
    setError(null);
    setUploadSuccess(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", uploadForm.title.trim());
      if (uploadForm.description.trim()) form.append("description", uploadForm.description.trim());
      if (uploadForm.resource_type) form.append("resource_type", uploadForm.resource_type);
      if (uploadForm.subject) form.append("subject", uploadForm.subject);
      if (uploadForm.education_level) form.append("education_level", uploadForm.education_level);
      if (uploadForm.difficulty) form.append("difficulty", uploadForm.difficulty);
      if (uploadForm.teaching_method) form.append("teaching_method", uploadForm.teaching_method);
      if (uploadForm.tags.trim()) form.append("tags", uploadForm.tags.trim());

      const created = await api.uploadResource(form);
      setUploadForm(EMPTY_UPLOAD);
      setFile(null);
      setUploadSuccess(created.title);
      setTab("mine");
    } catch (err) {
      setError(err);
    } finally {
      setUploading(false);
    }
  }

  async function removeResource(id: string) {
    setDeletingId(id);
    setError(null);
    try {
      await api.deleteResource(id);
      setMine((current) => current.filter((r) => r.id !== id));
    } catch (err) {
      setError(err);
    } finally {
      setDeletingId(null);
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "foryou", label: "Picked for you" },
    { key: "browse", label: "Browse all" },
    { key: "mine", label: "My materials" },
    { key: "upload", label: "Upload" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Teaching resources</h1>
      <p className="mt-1 text-sm text-muted">
        Share syllabi, homework, lesson plans and other materials — or browse what educators have
        uploaded.
      </p>

      <div className="mt-5 flex gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cx(
              "shrink-0 flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition",
              tab === key ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "browse" && (
        <Card className="mt-4 grid gap-3 p-4 sm:grid-cols-4">
          <div className="sm:col-span-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by meaning, e.g. teaching recursion with games"
              onKeyDown={(e) => e.key === "Enter" && void loadBrowse()}
            />
          </div>
          <Select value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">Any subject</option>
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </Select>
          <div className="flex gap-2">
            <Select value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">Any level</option>
              {EDUCATION_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {humanize(l)}
                </option>
              ))}
            </Select>
            <Button onClick={() => void loadBrowse()}>Go</Button>
          </div>
        </Card>
      )}

      {tab === "upload" && (
        <Card className="mt-4 p-5">
          <form onSubmit={submitUpload} className="space-y-4">
            <Field
              label="File"
              hint={`PDF, Word, PowerPoint, text or images · max ${MAX_UPLOAD_MB} MB`}
            >
              <Input
                type="file"
                accept={ACCEPT}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setUploadSuccess(null);
                  setError(null);
                }}
                required
              />
              {file && (
                <p className="mt-1 text-xs text-muted">
                  {file.name} · {formatBytes(file.size)}
                </p>
              )}
            </Field>

            <Field label="Title">
              <Input
                value={uploadForm.title}
                onChange={(e) => setUploadField("title", e.target.value)}
                placeholder="e.g. Algebra II syllabus — Fall 2026"
                minLength={3}
                maxLength={250}
                required
              />
            </Field>

            <Field label="Description" hint="Optional — helps others find this via semantic search">
              <textarea
                className="w-full rounded-lg bg-white px-3 py-2 text-sm text-ink ring-1 ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                rows={3}
                value={uploadForm.description}
                onChange={(e) => setUploadField("description", e.target.value)}
                placeholder="What is this material for? What topics does it cover?"
                maxLength={4000}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Type">
                <Select
                  value={uploadForm.resource_type}
                  onChange={(e) => setUploadField("resource_type", e.target.value)}
                >
                  <option value="">Select type</option>
                  {RESOURCE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {humanize(t)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Subject">
                <Select
                  value={uploadForm.subject}
                  onChange={(e) => setUploadField("subject", e.target.value)}
                >
                  <option value="">Select subject</option>
                  {SUBJECTS.map((s) => (
                    <option key={s} value={s}>
                      {humanize(s)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Education level">
                <Select
                  value={uploadForm.education_level}
                  onChange={(e) => setUploadField("education_level", e.target.value)}
                >
                  <option value="">Select level</option>
                  {EDUCATION_LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {humanize(l)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Difficulty">
                <Select
                  value={uploadForm.difficulty}
                  onChange={(e) => setUploadField("difficulty", e.target.value)}
                >
                  <option value="">Select difficulty</option>
                  {DIFFICULTIES.map((d) => (
                    <option key={d} value={d}>
                      {humanize(d)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Teaching method">
                <Select
                  value={uploadForm.teaching_method}
                  onChange={(e) => setUploadField("teaching_method", e.target.value)}
                >
                  <option value="">Select method</option>
                  {TEACHING_METHODS.map((m) => (
                    <option key={m} value={m}>
                      {humanize(m)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Tags" hint="Comma-separated, e.g. algebra, fractions">
                <Input
                  value={uploadForm.tags}
                  onChange={(e) => setUploadField("tags", e.target.value)}
                  placeholder="syllabus, week1, homework"
                />
              </Field>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <Button type="submit" loading={uploading}>
                Upload material
              </Button>
              {uploadSuccess && (
                <p className="text-sm text-emerald-700">Uploaded “{uploadSuccess}”.</p>
              )}
            </div>
          </form>
        </Card>
      )}

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {tab === "upload" ? null : loading ? (
        <Loading />
      ) : tab === "foryou" ? (
        <div className="mt-4 space-y-3">
          {recommended.map((item) => (
            <ResourceRow
              key={item.resource.id}
              resource={item.resource}
              score={item.match_score}
              reasons={item.reasons}
            />
          ))}
          {recommended.length === 0 && (
            <Card className="p-10 text-center text-sm text-muted">
              Nothing yet — add subjects to your profile and these will fill in.
            </Card>
          )}
        </div>
      ) : tab === "mine" ? (
        <div className="mt-4 space-y-3">
          {uploadSuccess && (
            <p className="text-sm text-emerald-700">
              “{uploadSuccess}” is live. You can upload another anytime.
            </p>
          )}
          {mine.map((resource) => (
            <ResourceRow
              key={resource.id}
              resource={resource}
              onDelete={() => void removeResource(resource.id)}
              deleting={deletingId === resource.id}
            />
          ))}
          {mine.length === 0 && (
            <Card className="p-10 text-center text-sm text-muted">
              You haven&apos;t uploaded anything yet.{" "}
              <button
                type="button"
                onClick={() => setTab("upload")}
                className="font-medium text-indigo-600 hover:text-indigo-700"
              >
                Share a syllabus or homework →
              </button>
            </Card>
          )}
        </div>
      ) : (
        <>
          <p className="mt-4 text-xs text-muted">{total.toLocaleString()} resources</p>
          <div className="mt-2 space-y-3">
            {browse.map(({ resource, score }) => (
              <ResourceRow key={resource.id} resource={resource} score={query ? score : undefined} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
