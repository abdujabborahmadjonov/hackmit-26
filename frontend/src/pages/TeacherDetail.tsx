import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  Profile,
  Rating,
  RatingSummary,
  Recommendation,
  Resource,
  StudentToken,
} from "../api/types";
import { humanize } from "../api/vocab";
import { WhyThisMatch } from "../components/MatchCard";
import {
  Avatar,
  Badge,
  Button,
  Card,
  ErrorNote,
  Input,
  Loading,
  ScoreRing,
  SectionHeading,
  Stars,
} from "../components/ui";
import { useAuth } from "../auth/AuthContext";

const ASPECTS = [
  { key: "knowledge_of_material" as const, label: "Knowledge of material" },
  { key: "presentation" as const, label: "Presentation" },
  { key: "friendliness" as const, label: "Friendliness" },
  { key: "other" as const, label: "Other" },
];

const DURATION_PRESETS = [
  { label: "30 minutes", minutes: 30 },
  { label: "1 hour", minutes: 60 },
  { label: "2 hours", minutes: 120 },
  { label: "1 day", minutes: 60 * 24 },
  { label: "7 days", minutes: 60 * 24 * 7 },
];

function AspectStars({
  value,
  onChange,
}: {
  value: number;
  onChange?: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={!onChange}
          onClick={() => onChange?.(star)}
          className={`text-lg ${onChange ? "press" : "cursor-default"} ${
            star <= value ? "text-amber-500" : "text-slate-300 hover:text-amber-300"
          }`}
          aria-label={`${star} stars`}
        >
          ★
        </button>
      ))}
    </div>
  );
}

function formatExpiry(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function TeacherDetail() {
  const { userId = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [match, setMatch] = useState<Recommendation | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [ratings, setRatings] = useState<Rating[]>([]);
  const [summary, setSummary] = useState<RatingSummary | null>(null);
  const [tokens, setTokens] = useState<StudentToken[]>([]);
  const [freshToken, setFreshToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const [myRating, setMyRating] = useState(0);
  const [comment, setComment] = useState("");
  const [studentToken, setStudentToken] = useState("");
  const [aspects, setAspects] = useState({
    knowledge_of_material: 0,
    presentation: 0,
    friendliness: 0,
    other: 0,
  });
  const [studentComment, setStudentComment] = useState("");

  const [tokenDuration, setTokenDuration] = useState(120);
  const [tokenLabel, setTokenLabel] = useState("");
  const [tokenMaxUses, setTokenMaxUses] = useState("");

  const isSelf = user?.id === userId;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [profileData, resourceData, ratingData, summaryData] = await Promise.all([
        api.profile(userId),
        api.resources({ owner_id: userId, limit: 6 }),
        api.ratings(userId),
        api.ratingSummary(userId),
      ]);
      setProfile(profileData);
      setResources(resourceData.items.map((item) => item.resource));
      setRatings(ratingData.items);
      setSummary(summaryData);
      if (user?.id === userId) {
        const tokenData = await api.studentTokens();
        setTokens(tokenData.items);
      }
      try {
        setMatch(await api.explain(userId));
      } catch {
        setMatch(null);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [userId, user?.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function connect() {
    setBusy("connect");
    try {
      await api.connect(userId);
      setConnected(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function message() {
    setBusy("message");
    try {
      await api.startConversation(userId);
      navigate("/messages");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function submitPeerRating() {
    if (!myRating) return;
    setBusy("rate");
    try {
      await api.rate(userId, myRating, comment);
      setComment("");
      setMyRating(0);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function submitStudentRating() {
    if (!studentToken.trim()) return;
    if (ASPECTS.some(({ key }) => !aspects[key])) return;
    setBusy("student-rate");
    try {
      await api.rateAsStudent(userId, {
        verification_token: studentToken.trim(),
        ...aspects,
        comment: studentComment,
      });
      setStudentToken("");
      setStudentComment("");
      setAspects({
        knowledge_of_material: 0,
        presentation: 0,
        friendliness: 0,
        other: 0,
      });
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function createToken() {
    setBusy("create-token");
    try {
      const created = await api.createStudentToken({
        duration_minutes: tokenDuration,
        label: tokenLabel.trim() || undefined,
        max_uses: tokenMaxUses ? Number(tokenMaxUses) : null,
      });
      setFreshToken(created.token ?? null);
      setTokenLabel("");
      setTokenMaxUses("");
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function revokeToken(tokenId: string) {
    setBusy(`revoke-${tokenId}`);
    try {
      await api.revokeStudentToken(tokenId);
      if (freshToken) setFreshToken(null);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <Loading label="Loading profile" />;
  if (!profile) return <ErrorNote error={error ?? new Error("Profile not found")} />;

  const name = profile.user ? `${profile.user.first_name} ${profile.user.last_name}` : "Educator";
  const aspectAverages = summary?.aspect_averages;
  const studentAspectsReady = ASPECTS.every(({ key }) => aspects[key] > 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="press inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-ink"
        >
          <span aria-hidden>←</span> Back to discovery
        </button>
        {isSelf && (
          <Button variant="secondary" size="sm" onClick={() => navigate("/profile")}>
            Edit profile
          </Button>
        )}
      </div>

      <Card className="overflow-hidden">
        <div className="h-24 bg-gradient-to-r from-indigo-100 via-blue-50 to-emerald-50" />
        <div className="-mt-8 p-6 sm:p-8">
          <div className="flex flex-wrap items-start gap-4">
            <div className="rounded-full bg-white p-1.5 shadow-sm">
              <Avatar name={name} size={72} />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="mt-8 text-2xl font-semibold tracking-tight text-ink sm:mt-9">{name}</h1>
              <p className="mt-0.5 text-sm text-muted">
                {[profile.institution, profile.location_name].filter(Boolean).join(" · ")}
                {profile.years_experience ? ` · ${profile.years_experience} years teaching` : ""}
              </p>
              {profile.rating_count > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Stars value={profile.average_rating} count={profile.rating_count} />
                  {summary && summary.verified_student_count > 0 && (
                    <Badge tone="emerald">
                      {summary.verified_student_count} verified student
                      {summary.verified_student_count === 1 ? "" : "s"}
                    </Badge>
                  )}
                </div>
              )}
            </div>
            {match && !isSelf && <ScoreRing score={match.match_score} size={64} />}
          </div>

          {profile.bio && <p className="mt-6 max-w-3xl text-sm leading-6 text-ink">{profile.bio}</p>}
          {profile.teaching_style && (
            <blockquote className="mt-4 max-w-3xl rounded-xl bg-indigo-50/70 p-4 text-sm leading-6 text-indigo-950 ring-1 ring-indigo-100">
              <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-indigo-600">
                Teaching philosophy
              </span>
              {profile.teaching_style}
            </blockquote>
          )}

          <div className="mt-4 flex flex-wrap gap-1.5">
            {profile.education_levels.map((level) => (
              <Badge key={level} tone="amber">
                {humanize(level)}
              </Badge>
            ))}
            {profile.subjects.map((subject) => (
              <Badge key={subject} tone="emerald">
                {humanize(subject)}
              </Badge>
            ))}
            {profile.teaching_methods.map((method) => (
              <Badge key={method} tone="indigo">
                {humanize(method)}
              </Badge>
            ))}
            {profile.class_size && <Badge>Class of {profile.class_size}</Badge>}
            {profile.languages.map((language) => (
              <Badge key={language}>{language}</Badge>
            ))}
          </div>

          {!isSelf && (
            <div className="mt-5 flex flex-wrap gap-2">
              <Button onClick={connect} loading={busy === "connect"} disabled={connected}>
                {connected ? "Request sent" : "Connect"}
              </Button>
              <Button variant="secondary" onClick={message} loading={busy === "message"}>
                Message
              </Button>
            </div>
          )}
          <ErrorNote error={error} />
        </div>
      </Card>

      {match && !isSelf && (
        <Card className="p-6 sm:p-7">
          <SectionHeading
            title="Why you two match"
            description="The strongest signals connecting your classrooms."
          />
          <ul className="grid gap-2 sm:grid-cols-2">
            {match.reasons.map((reason) => (
              <li
                key={reason}
                className="flex gap-2 rounded-xl bg-emerald-50/60 p-3 text-sm text-ink ring-1 ring-emerald-100"
              >
                <span aria-hidden className="mt-0.5 text-emerald-600">
                  ✓
                </span>
                {reason}
              </li>
            ))}
          </ul>
          <WhyThisMatch recommendation={match} />
        </Card>
      )}

      <Card className="p-6 sm:p-7">
        <SectionHeading
          title={`Resources from ${profile.user?.first_name ?? "this educator"}`}
          description="Materials and ideas this educator has shared with the community."
        />
        {resources.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No resources shared yet.</p>
        ) : (
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {resources.map((resource) => (
              <li key={resource.id} className="rounded-xl bg-slate-50 p-4 ring-1 ring-line">
                <p className="text-sm font-medium text-ink">{resource.title}</p>
                <p className="mt-0.5 text-sm text-muted">{resource.description}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  {resource.resource_type && (
                    <Badge tone="indigo">{humanize(resource.resource_type)}</Badge>
                  )}
                  {resource.subject && <Badge tone="emerald">{humanize(resource.subject)}</Badge>}
                  {resource.education_level && (
                    <Badge tone="amber">{humanize(resource.education_level)}</Badge>
                  )}
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
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {isSelf && (
        <Card className="p-6 sm:p-7">
          <SectionHeading
            title="Student rating tokens"
            description="Generate a classroom code. Students enter it to leave a verified rating while the token is valid."
          />
          <div className="mt-4 space-y-4 rounded-xl bg-slate-50 p-4 ring-1 ring-line">
            <div>
              <p className="mb-2 text-sm font-medium text-ink">Token length</p>
              <div className="flex flex-wrap gap-2">
                {DURATION_PRESETS.map((preset) => (
                  <button
                    key={preset.minutes}
                    type="button"
                    onClick={() => setTokenDuration(preset.minutes)}
                    className={`press rounded-lg px-3 py-1.5 text-sm ring-1 ${
                      tokenDuration === preset.minutes
                        ? "bg-indigo-600 text-white ring-indigo-600"
                        : "bg-white text-ink ring-line hover:ring-slate-300"
                    }`}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-ink">Label (optional)</span>
                <Input
                  value={tokenLabel}
                  onChange={(e) => setTokenLabel(e.target.value)}
                  placeholder="Period 3 Biology — Friday"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-ink">Max uses (optional)</span>
                <Input
                  type="number"
                  min={1}
                  value={tokenMaxUses}
                  onChange={(e) => setTokenMaxUses(e.target.value)}
                  placeholder="Unlimited"
                />
              </label>
            </div>
            <Button onClick={createToken} loading={busy === "create-token"}>
              Generate token
            </Button>
            {freshToken && (
              <div className="rounded-xl bg-emerald-50 p-4 ring-1 ring-emerald-100">
                <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                  Share this code now
                </p>
                <p className="mt-1 font-mono text-2xl font-semibold tracking-widest text-emerald-950">
                  {freshToken}
                </p>
                <p className="mt-1 text-sm text-emerald-800">
                  It will not be shown again. Copy it before leaving this page.
                </p>
              </div>
            )}
          </div>
          {tokens.length === 0 ? (
            <p className="mt-4 text-sm text-muted">No tokens yet.</p>
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {tokens.map((token) => (
                <li key={token.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <p className="text-sm font-medium text-ink">
                      {token.label || "Classroom token"}
                    </p>
                    <p className="text-xs text-muted">
                      Expires {formatExpiry(token.expires_at)} · {token.use_count}
                      {token.max_uses != null ? ` / ${token.max_uses}` : ""} uses
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {token.is_active ? (
                      <Badge tone="emerald">Active</Badge>
                    ) : token.is_revoked ? (
                      <Badge>Revoked</Badge>
                    ) : (
                      <Badge tone="amber">Expired</Badge>
                    )}
                    {token.is_active && (
                      <Button
                        size="sm"
                        variant="danger"
                        loading={busy === `revoke-${token.id}`}
                        onClick={() => revokeToken(token.id)}
                      >
                        Revoke
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {aspectAverages &&
        (aspectAverages.knowledge_of_material != null ||
          aspectAverages.presentation != null ||
          aspectAverages.friendliness != null ||
          aspectAverages.other != null) && (
          <Card className="p-6 sm:p-7">
            <SectionHeading
              title="Verified student averages"
              description="Aspect scores from students who redeemed a classroom token."
            />
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {ASPECTS.map(({ key, label }) => {
                const value = aspectAverages[key];
                if (value == null) return null;
                return (
                  <li
                    key={key}
                    className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3 ring-1 ring-line"
                  >
                    <span className="text-sm text-ink">{label}</span>
                    <Stars value={value} />
                  </li>
                );
              })}
            </ul>
          </Card>
        )}

      <Card className="p-6 sm:p-7">
        <SectionHeading
          title="Reviews"
          description="Verified student ratings use a classroom token. Colleagues can leave a peer review without one."
        />

        {!isSelf && (
          <div className="mt-4 space-y-4">
            <div className="rounded-xl bg-emerald-50/70 p-4 ring-1 ring-emerald-100">
              <p className="text-sm font-semibold text-emerald-950">Verified student rating</p>
              <p className="mt-1 text-sm text-emerald-900/80">
                Enter the code from your educator, then rate each aspect.
              </p>
              <label className="mt-3 block text-sm">
                <span className="mb-1 block font-medium text-ink">Verification token</span>
                <Input
                  value={studentToken}
                  onChange={(e) => setStudentToken(e.target.value.toUpperCase())}
                  placeholder="K7MP-9Q2R"
                  className="font-mono tracking-wider"
                  autoCapitalize="characters"
                />
              </label>
              <ul className="mt-3 space-y-2">
                {ASPECTS.map(({ key, label }) => (
                  <li key={key} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm text-ink">{label}</span>
                    <AspectStars
                      value={aspects[key]}
                      onChange={(value) => setAspects((prev) => ({ ...prev, [key]: value }))}
                    />
                  </li>
                ))}
              </ul>
              <textarea
                className="mt-3 w-full rounded-lg bg-white px-3 py-2 text-sm ring-1 ring-line focus:outline-none focus:ring-2 focus:ring-indigo-500"
                rows={2}
                value={studentComment}
                onChange={(e) => setStudentComment(e.target.value)}
                placeholder="Optional comment about the class experience."
              />
              <Button
                size="sm"
                className="mt-2"
                onClick={submitStudentRating}
                loading={busy === "student-rate"}
                disabled={!studentToken.trim() || !studentAspectsReady}
              >
                Submit verified rating
              </Button>
            </div>

            <div className="rounded-lg bg-slate-50 p-4 ring-1 ring-line">
              <p className="text-sm font-medium text-ink">Colleague review</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-sm text-muted">Your rating:</span>
                {[1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setMyRating(value)}
                    className={`press text-xl ${value <= myRating ? "text-amber-500" : "text-slate-300 hover:text-amber-300"}`}
                    aria-label={`${value} stars`}
                  >
                    ★
                  </button>
                ))}
              </div>
              <textarea
                className="mt-3 w-full rounded-lg bg-white px-3 py-2 text-sm ring-1 ring-line focus:outline-none focus:ring-2 focus:ring-indigo-500"
                rows={2}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="We co-planned a unit together — great with scaffolding."
              />
              <Button
                size="sm"
                className="mt-2"
                onClick={submitPeerRating}
                loading={busy === "rate"}
                disabled={!myRating}
              >
                Post peer review
              </Button>
            </div>
          </div>
        )}

        {ratings.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No reviews yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {ratings.map((rating) => (
              <li key={rating.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Stars value={rating.rating} />
                  {rating.reviewer && (
                    <span className="text-sm text-muted">
                      {rating.reviewer.first_name} {rating.reviewer.last_name}
                    </span>
                  )}
                  {rating.is_verified_student ? (
                    <Badge tone="emerald">Verified student</Badge>
                  ) : (
                    <Badge>Colleague</Badge>
                  )}
                </div>
                {rating.is_verified_student &&
                  rating.knowledge_of_material != null &&
                  rating.presentation != null &&
                  rating.friendliness != null &&
                  rating.other != null && (
                    <ul className="mt-2 grid gap-1 text-xs text-muted sm:grid-cols-2">
                      <li>Knowledge: {rating.knowledge_of_material}/5</li>
                      <li>Presentation: {rating.presentation}/5</li>
                      <li>Friendliness: {rating.friendliness}/5</li>
                      <li>Other: {rating.other}/5</li>
                    </ul>
                  )}
                {rating.comment && <p className="mt-1 text-sm text-ink">{rating.comment}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
