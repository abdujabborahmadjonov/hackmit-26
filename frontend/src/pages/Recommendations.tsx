import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Recommendation, RecommendationResponse } from "../api/types";
import { MatchCard } from "../components/MatchCard";
import { MatchCardSkeleton } from "../components/Skeleton";
import {
  FACTOR_ORDER,
  RankDelta,
  WeightStudio,
  normalise,
  scoreWith,
  type Weights,
} from "../components/WeightStudio";
import { Button, Card, ErrorNote } from "../components/ui";

/** How many candidates to pull. We show ten, but re-weighting only makes sense
 *  if there are others that can overtake them. */
const POOL = 30;
const SHOWN = 10;

export default function Recommendations() {
  const navigate = useNavigate();
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [weights, setWeights] = useState<Weights | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [excludeConnected, setExcludeConnected] = useState(false);
  const [tuning, setTuning] = useState(false);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [connected, setConnected] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.recommendations({
        limit: POOL,
        exclude_connected: excludeConnected,
      });
      setData(result);
      setWeights(result.weights);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [excludeConnected]);

  useEffect(() => {
    void load();
  }, [load]);

  const defaults = data?.weights ?? null;
  const changed = useMemo(() => {
    if (!weights || !defaults) return false;
    const a = normalise(weights);
    return FACTOR_ORDER.some((f) => Math.abs((a[f] ?? 0) - (defaults[f] ?? 0)) > 0.005);
  }, [weights, defaults]);

  /** Server order, then the order under the current sliders, so cards can show
   *  how far they moved. */
  const ranked = useMemo(() => {
    if (!data) return [] as (Recommendation & { localScore: number; delta: number })[];
    const serverRank = new Map(data.items.map((item, index) => [item.teacher.user_id, index]));
    const active = data.items.filter((item) => !dismissed.has(item.teacher.user_id));
    const scored = active.map((item) => ({
      ...item,
      localScore: weights && changed ? scoreWith(item.components, weights) : item.match_score,
    }));
    scored.sort((a, b) => b.localScore - a.localScore);
    return scored.map((item, index) => ({
      ...item,
      delta: (serverRank.get(item.teacher.user_id) ?? index) - index,
    }));
  }, [data, weights, changed, dismissed]);

  async function connect(userId: string) {
    setConnecting(userId);
    try {
      await api.connect(userId);
      setConnected((current) => new Set(current).add(userId));
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
    setDismissed((current) => new Set(current).add(userId));
    void api.feedback(userId, "dismissed").catch(() => undefined);
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Your matches</h1>
          <p className="mt-1 text-sm text-muted">
            Ranked by teaching philosophy, subject overlap, level, proximity and class size — every
            one explains itself.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-line text-indigo-600 focus:ring-indigo-500"
              checked={excludeConnected}
              onChange={(e) => setExcludeConnected(e.target.checked)}
            />
            Hide connections
          </label>
          <Button
            size="sm"
            variant={tuning ? "primary" : "secondary"}
            onClick={() => setTuning((open) => !open)}
          >
            {tuning ? "Done tuning" : "Tune the algorithm"}
          </Button>
        </div>
      </div>

      {tuning && weights && defaults && (
        <div className="rise mt-4">
          <WeightStudio
            weights={weights}
            defaults={defaults}
            onChange={setWeights}
            changed={changed}
          />
        </div>
      )}

      {data && !loading && (
        <p className="mt-4 text-xs text-muted">
          Scored {data.candidate_pool_size} candidates in {Math.round(data.took_ms)} ms
          {changed ? (
            <span className="ml-1 font-medium text-indigo-600">
              · re-ranked live with your weights
            </span>
          ) : (
            <>
              {" "}
              · weights{" "}
              {FACTOR_ORDER.map((f) => `${f.replace("_", " ")} ${Math.round(data.weights[f] * 100)}%`).join(
                " · ",
              )}
            </>
          )}
        </p>
      )}

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {loading ? (
        <div className="mt-4 space-y-4">
          {[0, 1, 2].map((n) => (
            <MatchCardSkeleton key={n} />
          ))}
        </div>
      ) : ranked.length > 0 ? (
        <div className="stagger mt-4 space-y-4">
          {ranked.slice(0, SHOWN).map((recommendation) => (
            <MatchCard
              key={recommendation.teacher.user_id}
              recommendation={recommendation}
              displayScore={recommendation.localScore}
              rankDelta={changed ? <RankDelta delta={recommendation.delta} /> : null}
              weights={changed && weights ? normalise(weights) : (data?.weights ?? undefined)}
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
