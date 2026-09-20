import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  ClassProfile,
  ConceptChip,
  FollowUpOption,
  ProblemType,
  Technique,
  TechniqueSearchParseResponse,
} from "../api/types";
import { humanize } from "../api/vocab";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Loading,
  PageHeader,
  Stars,
  cx,
} from "../components/ui";

const TEXTAREA =
  "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line " +
  "placeholder:text-slate-400 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500";

function ratingLine(tech: Technique): string | null {
  const summary = tech.rating_summary;
  if (!summary || summary.count <= 0) {
    if (tech.rating_count > 0) {
      return `${tech.average_rating.toFixed(1)} from ${tech.rating_count} student${tech.rating_count === 1 ? "" : "s"}`;
    }
    return null;
  }
  const similar =
    summary.similar_class_count > 0
      ? ` in similar classes`
      : "";
  return `${summary.average.toFixed(1)} from ${summary.count} student${summary.count === 1 ? "" : "s"}${similar}`;
}

function TechniqueResultCard({
  tech,
  onAsk,
  asking,
}: {
  tech: Technique;
  onAsk: () => void;
  asking: boolean;
}) {
  const line = ratingLine(tech);
  return (
    <Card className="flex h-full flex-col p-5" interactive>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={`/techniques/${tech.id}`}
            className="font-semibold text-ink hover:text-indigo-700"
          >
            {tech.title}
          </Link>
          <p className="mt-1 line-clamp-3 text-sm leading-5 text-muted">{tech.summary}</p>
        </div>
        {tech.score != null && (
          <span className="shrink-0 rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">
            {Math.round(tech.score * 100)}% fit
          </span>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {tech.problem_types.map((ptype) => (
          <Badge key={ptype} tone="amber">
            {humanize(ptype)}
          </Badge>
        ))}
        {tech.concepts.slice(0, 3).map((c) => (
          <Badge key={c.id} tone="indigo">
            {c.label}
          </Badge>
        ))}
      </div>
      {line && (
        <p className="mt-3 flex items-center gap-2 text-xs text-muted">
          <Stars value={tech.rating_summary?.average ?? tech.average_rating} />
          <span>{line}</span>
        </p>
      )}
      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        <Link to={`/techniques/${tech.id}`}>
          <Button size="sm" variant="secondary">
            View technique
          </Button>
        </Link>
        <Button size="sm" loading={asking} onClick={onAsk}>
          Ask this teacher
        </Button>
      </div>
    </Card>
  );
}

export default function ClassSearch() {
  const { classId = "" } = useParams();
  const navigate = useNavigate();
  const [klass, setKlass] = useState<ClassProfile | null>(null);
  const [conceptText, setConceptText] = useState("");
  const [problemText, setProblemText] = useState("");
  const [parsed, setParsed] = useState<TechniqueSearchParseResponse | null>(null);
  const [conceptChips, setConceptChips] = useState<ConceptChip[]>([]);
  const [problemChips, setProblemChips] = useState<string[]>([]);
  const [problemTypes, setProblemTypes] = useState<ProblemType[]>([]);
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [round, setRound] = useState(0);
  const [results, setResults] = useState<Technique[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"parse" | "refine" | "run" | string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.classProfile(classId);
        if (!cancelled) setKlass(data);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classId]);

  const applyParse = useCallback((response: TechniqueSearchParseResponse) => {
    setParsed(response);
    setConceptChips(response.concept_chips);
    setProblemChips(response.problem_chips);
    setProblemTypes(response.problem_types);
    setRound(response.round);
    setSelectedOptions([]);
  }, []);

  async function parse(event: FormEvent) {
    event.preventDefault();
    if (!conceptText.trim() || !problemText.trim()) return;
    setBusy("parse");
    setError(null);
    setResults([]);
    try {
      const response = await api.parseTechniqueSearch({
        class_profile_id: classId,
        concept_text: conceptText.trim(),
        problem_text: problemText.trim(),
        round: 0,
      });
      applyParse(response);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function refine() {
    setBusy("refine");
    setError(null);
    try {
      const nextRound = Math.min(round + 1, 2);
      const response = await api.refineTechniqueSearch({
        class_profile_id: classId,
        concept_chips: conceptChips,
        problem_chips: problemChips,
        problem_types: problemTypes,
        selected_option_ids: selectedOptions,
        round: nextRound,
      });
      applyParse(response);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function runSearch() {
    setBusy("run");
    setError(null);
    try {
      const response = await api.runTechniqueSearch({
        class_profile_id: classId,
        concept_ids: conceptChips.map((c) => c.id).filter((id): id is string => Boolean(id)),
        concept_labels: conceptChips.map((c) => c.label),
        problem_types: problemTypes,
        problem_text: problemChips.join("; ") || problemText.trim() || null,
        limit: 12,
      });
      setResults(response.items);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function askTeacher(tech: Technique) {
    setBusy(`ask-${tech.id}`);
    setError(null);
    try {
      await api.startConversation(
        tech.owner_id,
        `Hi — I saw your technique "${tech.title}" and would love to hear how it worked in your class.`,
      );
      navigate("/messages");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  function toggleOption(option: FollowUpOption) {
    setSelectedOptions((current) =>
      current.includes(option.id)
        ? current.filter((id) => id !== option.id)
        : [...current, option.id],
    );
  }

  function removeConcept(index: number) {
    setConceptChips((current) => current.filter((_, i) => i !== index));
  }

  function removeProblemChip(index: number) {
    setProblemChips((current) => current.filter((_, i) => i !== index));
  }

  function removeProblemType(ptype: ProblemType) {
    setProblemTypes((current) => current.filter((item) => item !== ptype));
  }

  if (loading) return <Loading label="Loading class" />;
  if (!klass) {
    return (
      <div>
        <ErrorNote error={error ?? new Error("Class not found")} />
        <Link to="/classes" className="mt-4 inline-block text-sm font-semibold text-indigo-600">
          ← Back to classes
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow={klass.title}
        title="Technique search"
        description="Describe the concept and the classroom problem. We'll parse it into chips, ask a follow-up if needed, then find techniques that fit this class."
        actions={
          <Link to={`/classes/${classId}/planning`}>
            <Button size="sm" variant="secondary">
              Planning mode
            </Button>
          </Link>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      <Card className="mt-6 p-5">
        <form onSubmit={parse} className="space-y-4">
          <Field label="Concept" hint="What topic are students working on?">
            <textarea
              className={TEXTAREA}
              rows={2}
              value={conceptText}
              onChange={(e) => setConceptText(e.target.value)}
              placeholder="e.g. Chain rule for composite functions"
              required
              maxLength={500}
            />
          </Field>
          <Field
            label="Classroom problem"
            hint={
              parsed?.vague_vs_specific ||
              'Vague: "students struggle with this." Specific: "they treat derivatives as fractions and cancel dy/dx symbols."'
            }
          >
            <textarea
              className={TEXTAREA}
              rows={3}
              value={problemText}
              onChange={(e) => setProblemText(e.target.value)}
              placeholder="What are you seeing in class?"
              required
              maxLength={2000}
            />
          </Field>
          <Button type="submit" loading={busy === "parse"}>
            Parse & refine
          </Button>
        </form>
      </Card>

      {parsed && (
        <Card className="mt-5 space-y-4 p-5">
          <div>
            <p className="text-sm font-semibold text-ink">Concept chips</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {conceptChips.length === 0 && (
                <span className="text-xs text-muted">None yet — pick a follow-up below.</span>
              )}
              {conceptChips.map((chip, index) => (
                <button
                  key={`${chip.label}-${index}`}
                  type="button"
                  onClick={() => removeConcept(index)}
                  className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
                  title="Remove"
                >
                  {chip.label}
                  <span aria-hidden>×</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-sm font-semibold text-ink">Problem chips</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {problemChips.length === 0 && problemTypes.length === 0 && (
                <span className="text-xs text-muted">None yet.</span>
              )}
              {problemChips.map((chip, index) => (
                <button
                  key={`${chip}-${index}`}
                  type="button"
                  onClick={() => removeProblemChip(index)}
                  className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-200"
                >
                  {chip}
                  <span aria-hidden>×</span>
                </button>
              ))}
              {problemTypes.map((ptype) => (
                <button
                  key={ptype}
                  type="button"
                  onClick={() => removeProblemType(ptype)}
                  className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-100"
                >
                  {humanize(ptype)}
                  <span aria-hidden>×</span>
                </button>
              ))}
            </div>
          </div>

          {parsed.needs_follow_up && parsed.follow_up_options.length > 0 && round < 2 && (
            <div className="rounded-xl bg-slate-50 p-4">
              <p className="text-sm font-semibold text-ink">
                {parsed.follow_up_prompt || "A quick follow-up:"}
              </p>
              <ul className="mt-3 space-y-2">
                {parsed.follow_up_options.map((option) => {
                  const selected = selectedOptions.includes(option.id);
                  return (
                    <li key={option.id}>
                      <button
                        type="button"
                        onClick={() => toggleOption(option)}
                        className={cx(
                          "w-full rounded-xl px-3 py-2.5 text-left text-sm ring-1 transition",
                          selected
                            ? "bg-indigo-50 text-indigo-800 ring-indigo-200"
                            : "bg-white text-ink ring-line hover:ring-slate-300",
                        )}
                      >
                        <span className="font-medium">{option.label}</span>
                        {option.example && (
                          <span className="mt-0.5 block text-xs text-muted">{option.example}</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <Button
                className="mt-3"
                size="sm"
                loading={busy === "refine"}
                disabled={selectedOptions.length === 0}
                onClick={() => void refine()}
              >
                Apply follow-up
              </Button>
            </div>
          )}

          <Button loading={busy === "run"} onClick={() => void runSearch()}>
            Run search
          </Button>
        </Card>
      )}

      {results.length > 0 && (
        <div className="mt-8">
          <p className="mb-4 text-lg font-semibold tracking-tight text-ink">
            {results.length} technique{results.length === 1 ? "" : "s"}
          </p>
          <ul className="grid gap-4 sm:grid-cols-2">
            {results.map((tech) => (
              <li key={tech.id}>
                <TechniqueResultCard
                  tech={tech}
                  asking={busy === `ask-${tech.id}`}
                  onAsk={() => void askTeacher(tech)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {busy === "run" && results.length === 0 && (
        <Loading label="Searching techniques" />
      )}

      <p className="mt-8">
        <Link to="/classes" className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
          ← Back to classes
        </Link>
      </p>
    </div>
  );
}
