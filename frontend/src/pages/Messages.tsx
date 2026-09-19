import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Conversation, Message } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Avatar, Button, Card, ErrorNote, Input, Loading, PageHeader, cx } from "../components/ui";

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
  const activeConversation = conversations.find((conversation) => conversation.id === activeId);
  const formatTime = (value: string) =>
    new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value));

  if (loading) return <Loading label="Loading messages" />;

  return (
    <div>
      <PageHeader
        eyebrow="Collaborate directly"
        title="Messages"
        description="Turn a promising match into a shared lesson, resource exchange, or ongoing professional connection."
      />
      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {conversations.length === 0 ? (
        <Card className="mt-7 p-12 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
            <svg aria-hidden="true" className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M4 5h16v11H9l-5 4V5Z" />
            </svg>
          </span>
          <p className="mt-4 font-semibold text-ink">No conversations yet</p>
          <p className="mt-2 text-sm text-muted">Open a match and choose “Message” to start planning together.</p>
        </Card>
      ) : (
        <div className="mt-7 grid gap-4 md:grid-cols-[300px_1fr]">
          <Card className="overflow-hidden">
            <div className="border-b border-line px-4 py-3">
              <p className="text-sm font-semibold text-ink">Conversations</p>
              <p className="text-xs text-muted">{conversations.length} active threads</p>
            </div>
            <div className="divide-y divide-line">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                onClick={() => setActiveId(conversation.id)}
                className={cx(
                  "flex w-full items-center gap-3 p-4 text-left transition",
                  conversation.id === activeId ? "bg-indigo-50 ring-inset ring-1 ring-indigo-100" : "hover:bg-slate-50",
                )}
              >
                <Avatar name={title(conversation)} size={34} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{title(conversation)}</p>
                  <p className="truncate text-xs text-muted">
                    {conversation.last_message?.content ?? "No messages yet"}
                  </p>
                  {conversation.last_message && (
                    <p className="mt-1 text-[10px] text-slate-400">
                      {formatTime(conversation.last_message.created_at)}
                    </p>
                  )}
                </div>
                {conversation.unread_count > 0 && (
                  <span className="rounded-full bg-indigo-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    {conversation.unread_count}
                  </span>
                )}
              </button>
            ))}
            </div>
          </Card>

          <Card className="flex min-h-[560px] flex-col overflow-hidden">
            {activeConversation && (
              <div className="flex items-center gap-3 border-b border-line px-5 py-4">
                <Avatar name={title(activeConversation)} size={38} />
                <div>
                  <p className="font-semibold text-ink">{title(activeConversation)}</p>
                  <p className="text-xs text-emerald-600">In your educator network</p>
                </div>
              </div>
            )}
            <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/50 p-4 sm:p-5">
              {messages.length === 0 && (
                <div className="flex h-full items-center justify-center text-center">
                  <p className="max-w-xs text-sm text-muted">Start the conversation with an idea, question, or resource you would like to build together.</p>
                </div>
              )}
              {messages.map((message) => {
                const mine = message.sender_id === user?.id;
                return (
                  <div key={message.id} className={cx("flex items-end gap-2", mine && "justify-end")}>
                    <div
                      className={cx(
                        "max-w-[82%] px-3.5 py-2.5 text-sm leading-5 shadow-sm sm:max-w-[70%]",
                        mine ? "rounded-2xl rounded-br-md bg-indigo-600 text-white" : "rounded-2xl rounded-bl-md bg-white text-ink ring-1 ring-line",
                      )}
                    >
                      <p>{message.content}</p>
                      <p className={cx("mt-1 text-[10px]", mine ? "text-indigo-200" : "text-slate-400")}>
                        {formatTime(message.created_at)}
                      </p>
                    </div>
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>
            <div className="border-t border-line bg-white p-3">
              <div className="flex gap-2">
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
              <p className="mt-2 px-1 text-[10px] text-muted">
                Messages are encrypted in transit and stored securely, but are not end-to-end encrypted.
              </p>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
