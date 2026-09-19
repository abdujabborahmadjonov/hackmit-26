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
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex flex-wrap items-start gap-4">
          <Avatar name={name} size={64} />
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold text-ink">{name}</h1>
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

        {profile.bio && <p className="mt-4 text-sm text-ink">{profile.bio}</p>}
        {profile.teaching_style && (
          <blockquote className="mt-3 border-l-2 border-indigo-200 pl-3 text-sm italic text-ink/85">
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
      </Card>

      {match && !isSelf && (
        <Card className="p-6">
          <h2 className="text-base font-semibold text-ink">Why you two match</h2>
          <ul className="mt-3 space-y-1.5">
            {match.reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-sm text-ink">
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

      <Card className="p-6">
        <h2 className="text-base font-semibold text-ink">
          Resources from {profile.user?.first_name ?? "this educator"}
        </h2>
        {resources.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No resources shared yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {resources.map((resource) => (
              <li key={resource.id} className="py-3">
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

      <Card className="p-6">
        <h2 className="text-base font-semibold text-ink">Reviews</h2>
        {!isSelf && (
          <div className="mt-3 rounded-lg bg-slate-50 p-4 ring-1 ring-line">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-ink">Your rating:</span>
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMyRating(value)}
                  className={value <= myRating ? "text-amber-500" : "text-slate-300"}
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
