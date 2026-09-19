import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Conversation, Message } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Avatar, Button, Card, ErrorNote, Input, Loading, cx } from "../components/ui";

export default function Messages() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    try {
      const data = await api.conversations();
      setConversations(data.items);
      setActiveId((current) => current ?? data.items[0]?.id ?? null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  const loadMessages = useCallback(async (conversationId: string) => {
    try {
      const data = await api.messages(conversationId);
      setMessages([...data.items].reverse()); // API returns newest first
      await api.markRead(conversationId).catch(() => undefined);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    if (activeId) void loadMessages(activeId);
  }, [activeId, loadMessages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function send() {
    if (!activeId || !draft.trim()) return;
    setSending(true);
    try {
      const message = await api.sendMessage(activeId, draft.trim());
      setMessages((current) => [...current, message]);
      setDraft("");
      void loadConversations();
    } catch (err) {
      setError(err);
    } finally {
      setSending(false);
    }
  }

  function title(conversation: Conversation): string {
    const other = conversation.participants.find((p) => p.id !== user?.id);
    return other ? `${other.first_name} ${other.last_name}` : "Conversation";
  }

  if (loading) return <Loading label="Loading messages" />;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Messages</h1>
      <p className="mt-1 text-xs text-muted">
        Encrypted in transit over HTTPS and stored on the server — not end-to-end encrypted.
      </p>
      <ErrorNote error={error} />

      {conversations.length === 0 ? (
        <Card className="mt-5 p-10 text-center text-sm text-muted">
          No conversations yet. Open a match and hit “Message” to start one.
        </Card>
      ) : (
        <div className="mt-5 grid gap-4 md:grid-cols-[260px_1fr]">
          <Card className="divide-y divide-line overflow-hidden">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                onClick={() => setActiveId(conversation.id)}
                className={cx(
                  "flex w-full items-center gap-3 p-3 text-left transition",
                  conversation.id === activeId ? "bg-indigo-50" : "hover:bg-slate-50",
                )}
              >
                <Avatar name={title(conversation)} size={34} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{title(conversation)}</p>
                  <p className="truncate text-xs text-muted">
                    {conversation.last_message?.content ?? "No messages yet"}
                  </p>
                </div>
                {conversation.unread_count > 0 && (
                  <span className="rounded-full bg-indigo-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    {conversation.unread_count}
                  </span>
                )}
              </button>
            ))}
          </Card>

          <Card className="flex min-h-[420px] flex-col">
            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              {messages.map((message) => {
                const mine = message.sender_id === user?.id;
                return (
                  <div key={message.id} className={cx("flex", mine && "justify-end")}>
                    <div
                      className={cx(
                        "max-w-[75%] rounded-2xl px-3 py-2 text-sm",
                        mine ? "bg-indigo-600 text-white" : "bg-slate-100 text-ink",
                      )}
                    >
                      {message.content}
                    </div>
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>
            <div className="flex gap-2 border-t border-line p-3">
              <Input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && void send()}
                placeholder="Write a message…"
              />
              <Button onClick={send} loading={sending} disabled={!draft.trim()}>
                Send
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
