import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Recommendation, RecommendationResponse } from "../api/types";
import {
  clearRecommendationsCache,
  getRecommendationsCache,
  patchRecommendationsCache,
  setRecommendationsCache,
} from "../cache/recommendationsCache";
import { MatchCard } from "../components/MatchCard";
import { PinnedMentors } from "../components/PinnedMentors";
import { MatchCardSkeleton } from "../components/Skeleton";
import {
  FACTOR_ORDER,
  RankDelta,
  WeightStudio,
  normalise,
  scoreWith,
  type Weights,
} from "../components/WeightStudio";
import { Button, Card, ErrorNote, PageHeader } from "../components/ui";

/** How many candidates to pull. We show ten, but re-weighting only makes sense
 *  if there are others that can overtake them. */
const POOL = 20;
const SHOWN = 10;

function writeCache(parts: {
  data: RecommendationResponse;
  weights: Weights;
  weightsSaved: boolean;
  dismissed: Set<string>;
  connected: Set<string>;
  aiEnabled: boolean;
}) {
  setRecommendationsCache({
    data: parts.data,
    weights: parts.weights,
    weightsSaved: parts.weightsSaved,
    dismissed: [...parts.dismissed],
    connected: [...parts.connected],
    aiEnabled: parts.aiEnabled,
    fetchedAt: Date.now(),
  });
}

export default function Recommendations() {
  const navigate = useNavigate();
  const initial = getRecommendationsCache();

  const [data, setData] = useState<RecommendationResponse | null>(initial?.data ?? null);
  const [weights, setWeights] = useState<Weights | null>(initial?.weights ?? null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(!initial);
  const [tuning, setTuning] = useState(false);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [connected, setConnected] = useState<Set<string>>(
    () => new Set(initial?.connected ?? []),
  );
  const [dismissed, setDismissed] = useState<Set<string>>(
    () => new Set(initial?.dismissed ?? []),
  );
  const [aiEnabled, setAiEnabled] = useState(initial?.aiEnabled ?? false);
  const [weightsSaved, setWeightsSaved] = useState(initial?.weightsSaved ?? false);
  const [savingWeights, setSavingWeights] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Mount-only fetch. Do NOT depend on connected/dismissed/weights — that
  // previously caused an infinite setState → load → setState loop that froze
  // the whole SPA after Connect / Not a fit.
  useEffect(() => {
    let cancelled = false;

    async function fetchMatches(force: boolean) {
      if (!force && getRecommendationsCache()) return;

      if (force && getRecommendationsCache()) setRefreshing(true);
      else if (!getRecommendationsCache()) setLoading(true);

      setError(null);
      try {
        const result = await api.recommendations({
          limit: POOL,
          exclude_connected: true,
        });
        if (cancelled) return;
        setData(result);
        setWeights(result.weights);
        setWeightsSaved(result.weight_source === "profile");
        writeCache({
          data: result,
          weights: result.weights,
          weightsSaved: result.weight_source === "profile",
          dismissed: force ? new Set() : new Set(getRecommendationsCache()?.dismissed ?? []),
          connected: force ? new Set() : new Set(getRecommendationsCache()?.connected ?? []),
          aiEnabled: getRecommendationsCache()?.aiEnabled ?? false,
        });
        if (force) {
          setDismissed(new Set());
          setConnected(new Set());
        }
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    void fetchMatches(false);

    if (initial?.aiEnabled === undefined) {
      void api
        .aiStatus()
        .then((status) => {
          if (cancelled) return;
          setAiEnabled(status.enabled);
          patchRecommendationsCache({ aiEnabled: status.enabled });
        })
        .catch(() => {
          if (cancelled) return;
          setAiEnabled(false);
          patchRecommendationsCache({ aiEnabled: false });
        });
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional mount-only
  }, []);

  async function refresh() {
    clearRecommendationsCache();
    setRefreshing(true);
    setError(null);
    try {
      const result = await api.recommendations({
        limit: POOL,
        exclude_connected: true,
      });
      setData(result);
      setWeights(result.weights);
      setWeightsSaved(result.weight_source === "profile");
      setDismissed(new Set());
      setConnected(new Set());
      writeCache({
        data: result,
        weights: result.weights,
        weightsSaved: result.weight_source === "profile",
        dismissed: new Set(),
        connected: new Set(),
        aiEnabled,
      });
    } catch (err) {
      setError(err);
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }

  const defaults = data?.weights ?? null;
  const changed = useMemo(() => {
    if (!weights || !defaults) return false;
    const a = normalise(weights);
    return FACTOR_ORDER.some((f) => Math.abs((a[f] ?? 0) - (defaults[f] ?? 0)) > 0.005);
  }, [weights, defaults]);

  const ranked = useMemo(() => {
    if (!data) return [] as (Recommendation & { localScore: number; delta: number })[];
    const serverRank = new Map(data.items.map((item, index) => [item.teacher.user_id, index]));
    const active = data.items.filter(
      (item) =>
        !dismissed.has(item.teacher.user_id) && !connected.has(item.teacher.user_id),
    );
    const scored = active.map((item) => ({
      ...item,
      localScore: weights && changed ? scoreWith(item.components, weights) : item.match_score,
    }));
    scored.sort((a, b) => b.localScore - a.localScore);
    return scored.map((item, index) => ({
      ...item,
      delta: (serverRank.get(item.teacher.user_id) ?? index) - index,
    }));
  }, [data, weights, changed, dismissed, connected]);

  async function connect(userId: string) {
    setConnecting(userId);
    try {
      await api.connect(userId);
      setConnected((current) => {
        const next = new Set(current).add(userId);
        patchRecommendationsCache({ connected: [...next] });
        return next;
      });
      void api.feedback(userId, "connected").catch(() => undefined);
    } catch (err) {
      setError(err);
    } finally {
      setConnecting(null);
    }
  }

  async function message(userId: string) {
    try {
      await api.startConversation(userId);
      navigate("/messages");
    } catch (err) {
      setError(err);
    }
  }

  function dismiss(userId: string) {
    setDismissed((current) => {
      const next = new Set(current).add(userId);
      patchRecommendationsCache({ dismissed: [...next] });
      return next;
    });
    void api.feedback(userId, "dismissed").catch(() => undefined);
  }

  async function saveWeights() {
    if (!weights) return;
    setSavingWeights(true);
    try {
      const prefs = await api.saveRecommendationWeights(normalise(weights));
      setWeightsSaved(true);
      setWeights(prefs.weights);
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setSavingWeights(false);
    }
  }

  async function clearSavedWeights() {
    setSavingWeights(true);
    try {
      await api.clearRecommendationWeights();
      setWeightsSaved(false);
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setSavingWeights(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Personalized for your classroom"
        title="Your best matches"
        description="Hybrid ranking over teaching philosophy, subjects, levels, proximity, class size, network overlap, and peer quality. People you've already invited or connected with are hidden."
        actions={
          <>
            <Button
              size="sm"
              variant="ghost"
              disabled={loading || refreshing}
              onClick={() => void refresh()}
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </Button>
            <Button
              size="sm"
              variant={tuning ? "primary" : "secondary"}
              onClick={() => setTuning((open) => !open)}
            >
              {tuning ? "Done tuning" : "Tune the algorithm"}
            </Button>
          </>
        }
      />

      {tuning && weights && defaults && (
        <div className="rise mt-6">
          <WeightStudio
            weights={weights}
            defaults={defaults}
            onChange={setWeights}
            changed={changed}
            onSave={() => void saveWeights()}
            onClearSaved={() => void clearSavedWeights()}
            saving={savingWeights}
            saved={weightsSaved}
            weightSource={data?.weight_source}
          />
        </div>
      )}

      {data && !loading && (
        <div className="mt-6 grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
          <Card className="p-3 sm:p-4">
            <p className="text-xs text-muted">Candidates considered</p>
            <p className="mt-1 text-2xl font-semibold text-ink">{data.candidate_pool_size}</p>
          </Card>
          <Card className="p-3 sm:p-4">
            <p className="text-xs text-muted">Top match</p>
            <p className="mt-1 text-2xl font-semibold text-ink">
              {ranked[0] ? `${Math.round(ranked[0].localScore * 100)}%` : "—"}
            </p>
          </Card>
          <Card className="p-3 sm:p-4">
            <p className="text-xs text-muted">Weight source</p>
            <p className="mt-1 text-lg font-semibold capitalize text-ink">
              {data.weight_source ?? "default"}
            </p>
          </Card>
          <Card className="p-3 sm:p-4">
            <p className="text-xs text-muted">Bandit arm</p>
            <p className="mt-1 truncate text-lg font-semibold text-ink">
              {data.bandit_arm_id ?? "—"}
            </p>
          </Card>
        </div>
      )}

      <div className="mt-5">
        <ErrorNote error={error} />
      </div>

      <PinnedMentors
        title="Pinned first"
        description="Always here, whatever your matches look like"
      />

      {loading ? (
        <div className="mt-4 space-y-4">
          {[0, 1, 2].map((n) => (
            <MatchCardSkeleton key={n} />
          ))}
        </div>
      ) : ranked.length > 0 ? (
        <div className="mt-6 space-y-4">
          {ranked.slice(0, SHOWN).map((recommendation) => (
            <MatchCard
              key={recommendation.teacher.user_id}
              recommendation={recommendation}
              displayScore={recommendation.localScore}
              rankDelta={changed ? <RankDelta delta={recommendation.delta} /> : null}
              weights={changed && weights ? normalise(weights) : (data?.weights ?? undefined)}
              aiEnabled={aiEnabled}
              onConnect={connect}
              onMessage={message}
              onDismiss={dismiss}
              connecting={connecting === recommendation.teacher.user_id}
              connected={connected.has(recommendation.teacher.user_id)}
            />
          ))}
        </div>
      ) : (
        <Card className="mt-4 p-10 text-center">
          <p className="font-semibold text-ink">No matches yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Add your subjects and teaching style to your profile — matching needs something to work
            with.
          </p>
          <Button className="mt-5" onClick={() => navigate("/profile")}>
            Complete your profile
          </Button>
        </Card>
      )}
    </div>
  );
}
