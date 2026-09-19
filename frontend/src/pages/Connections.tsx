import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Connection } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Avatar, Badge, Button, Card, ErrorNote, Loading } from "../components/ui";

export default function Connections() {
  const { user } = useAuth();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.connections({ limit: 50 });
      setConnections(data.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function respond(id: string, status: "accepted" | "rejected") {
    setBusy(id);
    try {
      await api.respondToConnection(id, status);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <Loading label="Loading connections" />;

  const incoming = connections.filter(
    (c) => c.receiver_id === user?.id && c.status === "pending",
  );
  const accepted = connections.filter((c) => c.status === "accepted");
  const outgoing = connections.filter(
    (c) => c.requester_id === user?.id && c.status === "pending",
  );

  function other(connection: Connection) {
    const person =
      connection.requester_id === user?.id ? connection.receiver : connection.requester;
    return {
      id: connection.requester_id === user?.id ? connection.receiver_id : connection.requester_id,
      name: person ? `${person.first_name} ${person.last_name}` : "Educator",
    };
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Connections</h1>
        <p className="mt-1 text-sm text-muted">
          {accepted.length} connected · {incoming.length} waiting on you · {outgoing.length} sent
        </p>
      </div>
      <ErrorNote error={error} />

      {incoming.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
            Waiting on you
          </h2>
          <div className="space-y-2">
            {incoming.map((connection) => {
              const person = other(connection);
              return (
                <Card key={connection.id} className="flex items-center gap-3 p-4">
                  <Avatar name={person.name} size={40} />
                  <Link
                    to={`/teachers/${person.id}`}
                    className="font-medium text-ink hover:text-indigo-700"
                  >
                    {person.name}
                  </Link>
                  <div className="ml-auto flex gap-2">
                    <Button
                      size="sm"
                      loading={busy === connection.id}
                      onClick={() => respond(connection.id, "accepted")}
                    >
                      Accept
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => respond(connection.id, "rejected")}
                    >
                      Decline
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
          Your network
        </h2>
        {accepted.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted">
            No connections yet — your matches page is the place to start.
          </Card>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {accepted.map((connection) => {
              const person = other(connection);
              return (
                <Card key={connection.id} className="flex items-center gap-3 p-4">
                  <Avatar name={person.name} size={36} />
                  <Link
                    to={`/teachers/${person.id}`}
                    className="font-medium text-ink hover:text-indigo-700"
                  >
                    {person.name}
                  </Link>
                  <Badge tone="emerald">Connected</Badge>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {outgoing.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
            Requests you sent
          </h2>
          <div className="space-y-2">
            {outgoing.map((connection) => {
              const person = other(connection);
              return (
                <Card key={connection.id} className="flex items-center gap-3 p-4">
                  <Avatar name={person.name} size={36} />
                  <span className="text-ink">{person.name}</span>
                  <Badge tone="amber">Pending</Badge>
                </Card>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
