import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { RecommendationResponse } from "../api/types";
import { MatchCard } from "../components/MatchCard";
import { Button, Card, ErrorNote, Loading } from "../components/ui";

export default function Recommendations() {
  const navigate = useNavigate();
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [excludeConnected, setExcludeConnected] = useState(false);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [connected, setConnected] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.recommendations({ limit: 10, exclude_connected: excludeConnected }));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [excludeConnected]);

  useEffect(() => {
    void load();
  }, [load]);

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
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-line text-indigo-600 focus:ring-indigo-500"
              checked={excludeConnected}
              onChange={(e) => setExcludeConnected(e.target.checked)}
            />
            Hide existing connections
          </label>
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Refresh
          </Button>
        </div>
      </div>

      {data && !loading && (
        <p className="mt-4 text-xs text-muted">
          Scored {data.candidate_pool_size} candidates in {Math.round(data.took_ms)} ms · weights{" "}
          {Object.entries(data.weights)
            .map(([key, weight]) => `${key.replace("_", " ")} ${Math.round(weight * 100)}%`)
            .join(" · ")}
        </p>
      )}

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {loading ? (
        <Loading label="Finding educators who teach like you" />
      ) : data && data.items.length > 0 ? (
        <div className="mt-4 space-y-4">
          {data.items.map((recommendation) => (
            <MatchCard
              key={recommendation.teacher.user_id}
              recommendation={recommendation}
              onConnect={connect}
              onMessage={message}
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
        </Card>
      )}
    </div>
  );
}
