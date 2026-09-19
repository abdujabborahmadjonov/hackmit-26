import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Profile, Rating, Recommendation, Resource } from "../api/types";
import { humanize } from "../api/vocab";
import { WhyThisMatch } from "../components/MatchCard";
import {
  Avatar,
  Badge,
  Button,
  Card,
  ErrorNote,
  Loading,
  ScoreRing,
  SectionHeading,
  Stars,
} from "../components/ui";
import { useAuth } from "../auth/AuthContext";

export default function TeacherDetail() {
  const { userId = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [match, setMatch] = useState<Recommendation | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [ratings, setRatings] = useState<Rating[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [myRating, setMyRating] = useState(0);
  const [comment, setComment] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [profileData, resourceData, ratingData] = await Promise.all([
        api.profile(userId),
        api.resources({ owner_id: userId, limit: 6 }),
        api.ratings(userId),
      ]);
      setProfile(profileData);
      setResources(resourceData.items.map((item) => item.resource));
      setRatings(ratingData.items);
      // Only meaningful between two people who both have profiles.
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
  }, [userId]);

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

  async function submitRating() {
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

  if (loading) return <Loading label="Loading profile" />;
  if (!profile) return <ErrorNote error={error ?? new Error("Profile not found")} />;

  const name = profile.user ? `${profile.user.first_name} ${profile.user.last_name}` : "Educator";
  const isSelf = user?.id === userId;

  return (
    <div className="space-y-6">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="press inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-ink"
      >
        <span aria-hidden>←</span> Back to discovery
      </button>

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
              <div className="mt-2">
                <Stars value={profile.average_rating} count={profile.rating_count} />
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
              <li key={reason} className="flex gap-2 rounded-xl bg-emerald-50/60 p-3 text-sm text-ink ring-1 ring-emerald-100">
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
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {resource.subject && <Badge tone="emerald">{humanize(resource.subject)}</Badge>}
                  {resource.education_level && (
                    <Badge tone="amber">{humanize(resource.education_level)}</Badge>
                  )}
                  {resource.difficulty && <Badge>{humanize(resource.difficulty)}</Badge>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-6 sm:p-7">
        <SectionHeading
          title="Colleague reviews"
          description="Feedback from educators who have worked together."
        />
        {!isSelf && (
          <div className="mt-3 rounded-lg bg-slate-50 p-4 ring-1 ring-line">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-ink">Your rating:</span>
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
              onClick={submitRating}
              loading={busy === "rate"}
              disabled={!myRating}
            >
              Post review
            </Button>
          </div>
        )}
        {ratings.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No reviews yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {ratings.map((rating) => (
              <li key={rating.id} className="py-3">
                <div className="flex items-center gap-2">
                  <Stars value={rating.rating} />
                  {rating.reviewer && (
                    <span className="text-sm text-muted">
                      {rating.reviewer.first_name} {rating.reviewer.last_name}
                    </span>
                  )}
                  {rating.is_verified_student && <Badge tone="emerald">Connected colleague</Badge>}
                </div>
                {rating.comment && <p className="mt-1 text-sm text-ink">{rating.comment}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
