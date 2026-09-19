import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Connection } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Avatar, Badge, Button, Card, ErrorNote, Loading, PageHeader, SectionHeading } from "../components/ui";

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
      <PageHeader
        eyebrow="Your educator network"
        title="Connections"
        description="Keep track of the educators you collaborate with and respond to new introductions."
        actions={
          <Link
            to="/search"
            className="press inline-flex items-center justify-center rounded-xl bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
          >
            Discover educators
          </Link>
        }
      />
      <div className="grid grid-cols-3 gap-3">
        {[
          ["Connected", accepted.length],
          ["Waiting on you", incoming.length],
          ["Requests sent", outgoing.length],
        ].map(([label, count]) => (
          <Card key={label} className="p-4">
            <p className="text-xs text-muted">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-ink">{count}</p>
          </Card>
        ))}
      </div>
      <ErrorNote error={error} />

      {incoming.length > 0 && (
        <section>
          <SectionHeading title="Waiting on you" description="Educators who would like to connect." />
          <div className="space-y-3">
            {incoming.map((connection) => {
              const person = other(connection);
              return (
                <Card key={connection.id} className="flex flex-wrap items-center gap-3 border-l-4 border-l-indigo-500 p-4 sm:flex-nowrap">
                  <Avatar name={person.name} size={44} />
                  <Link
                    to={`/teachers/${person.id}`}
                    className="font-semibold text-ink hover:text-indigo-700"
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
        <SectionHeading title="Your network" description="People you can message and collaborate with." />
        {accepted.length === 0 ? (
          <Card className="p-10 text-center">
            <p className="font-semibold text-ink">Your network is ready to grow</p>
            <p className="mt-2 text-sm text-muted">Start with a strong match and send a thoughtful introduction.</p>
            <Link
              to="/"
              className="press mt-5 inline-flex items-center justify-center rounded-xl bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              View your matches
            </Link>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {accepted.map((connection) => {
              const person = other(connection);
              return (
                <Card key={connection.id} className="p-4" interactive>
                  <Link to={`/teachers/${person.id}`} className="flex items-center gap-3">
                    <Avatar name={person.name} size={42} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-ink">{person.name}</p>
                      <p className="mt-0.5 text-xs text-muted">View profile and shared resources</p>
                    </div>
                    <Badge tone="emerald">Connected</Badge>
                  </Link>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {outgoing.length > 0 && (
        <section>
          <SectionHeading title="Requests you sent" />
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
