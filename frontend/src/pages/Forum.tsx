import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ForumPost, ForumTopic } from "../api/types";
import { FORUM_CATEGORIES, humanize } from "../api/vocab";
import { useAuth } from "../auth/AuthContext";
import {
  Avatar,
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  cx,
} from "../components/ui";

const TEXTAREA =
  "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line " +
  "placeholder:text-slate-400 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500";

function formatWhen(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function authorName(topic: { author: ForumTopic["author"] }): string {
  if (!topic.author) return "Educator";
  return `${topic.author.first_name} ${topic.author.last_name}`;
}

export default function Forum() {
  const { user } = useAuth();
  const [topics, setTopics] = useState<ForumTopic[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeTopic, setActiveTopic] = useState<ForumTopic | null>(null);
  const [posts, setPosts] = useState<ForumPost[]>([]);
  const [category, setCategory] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [composing, setComposing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [replying, setReplying] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [newCategory, setNewCategory] = useState<string>("general");
  const [reply, setReply] = useState("");

  const loadTopics = useCallback(async () => {
    try {
      const data = await api.forumTopics({
        category: category || undefined,
        q: query.trim() || undefined,
        limit: 50,
      });
      setTopics(data.items);
      setActiveId((current) => {
        if (current && data.items.some((item) => item.id === current)) return current;
        return data.items[0]?.id ?? null;
      });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [category, query]);

  useEffect(() => {
    void loadTopics();
  }, [loadTopics]);

  const loadThread = useCallback(async (topicId: string) => {
    setLoadingThread(true);
    try {
      const [topic, replies] = await Promise.all([
        api.forumTopic(topicId),
        api.forumPosts(topicId, { limit: 100 }),
      ]);
      setActiveTopic(topic);
      setPosts(replies.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoadingThread(false);
    }
  }, []);

  useEffect(() => {
    if (activeId) void loadThread(activeId);
    else {
      setActiveTopic(null);
      setPosts([]);
    }
  }, [activeId, loadThread]);

  async function createTopic(event: FormEvent) {
    event.preventDefault();
    if (!newTitle.trim() || !newBody.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const topic = await api.createForumTopic({
        title: newTitle.trim(),
        body: newBody.trim(),
        category: newCategory,
      });
      setNewTitle("");
      setNewBody("");
      setNewCategory("general");
      setComposing(false);
      setTopics((current) => [topic, ...current.filter((item) => item.id !== topic.id)]);
      setActiveId(topic.id);
    } catch (err) {
      setError(err);
    } finally {
      setCreating(false);
    }
  }

  async function sendReply(event: FormEvent) {
    event.preventDefault();
    if (!activeId || !reply.trim()) return;
    setReplying(true);
    setError(null);
    try {
      const post = await api.createForumPost(activeId, reply.trim());
      setPosts((current) => [...current, post]);
      setReply("");
      setActiveTopic((current) =>
        current
          ? {
              ...current,
              reply_count: current.reply_count + 1,
              last_activity_at: post.created_at ?? current.last_activity_at,
            }
          : current,
      );
      setTopics((current) => {
        const updated = current.map((topic) =>
          topic.id === activeId
            ? {
                ...topic,
                reply_count: topic.reply_count + 1,
                last_activity_at: post.created_at ?? topic.last_activity_at,
              }
            : topic,
        );
        return [...updated].sort((a, b) =>
          (b.last_activity_at ?? "").localeCompare(a.last_activity_at ?? ""),
        );
      });
    } catch (err) {
      setError(err);
    } finally {
      setReplying(false);
    }
  }

  async function removeTopic(topicId: string) {
    setDeletingId(topicId);
    try {
      await api.deleteForumTopic(topicId);
      setTopics((current) => current.filter((topic) => topic.id !== topicId));
      if (activeId === topicId) setActiveId(null);
    } catch (err) {
      setError(err);
    } finally {
      setDeletingId(null);
    }
  }

  async function removePost(postId: string) {
    setDeletingId(postId);
    try {
      await api.deleteForumPost(postId);
      setPosts((current) => current.filter((post) => post.id !== postId));
      setActiveTopic((current) =>
        current ? { ...current, reply_count: Math.max(0, current.reply_count - 1) } : current,
      );
      setTopics((current) =>
        current.map((topic) =>
          topic.id === activeId
            ? { ...topic, reply_count: Math.max(0, topic.reply_count - 1) }
            : topic,
        ),
      );
    } catch (err) {
      setError(err);
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) return <Loading label="Loading forum" />;

  return (
    <div>
      <PageHeader
        eyebrow="Community"
        title="Forum"
        description="Ask for co-planners, swap unit ideas, and talk through classroom challenges with other educators."
        actions={
          <Button variant={composing ? "secondary" : "primary"} onClick={() => setComposing((v) => !v)}>
            {composing ? "Cancel" : "New topic"}
          </Button>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {composing && (
        <Card className="mt-6 p-5">
          <form className="space-y-4" onSubmit={createTopic}>
            <Field label="Title">
              <Input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="What do you want to discuss?"
                minLength={3}
                maxLength={200}
                required
              />
            </Field>
            <Field label="Category">
              <Select value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                {FORUM_CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {humanize(value)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Post">
              <textarea
                className={TEXTAREA}
                rows={5}
                value={newBody}
                onChange={(e) => setNewBody(e.target.value)}
                placeholder="Share context, what you’ve tried, and what would help."
                minLength={1}
                maxLength={10000}
                required
              />
            </Field>
            <Button type="submit" loading={creating}>
              Post topic
            </Button>
          </form>
        </Card>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <form
          className="flex flex-1 gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(searchDraft.trim());
          }}
        >
          <Input
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            placeholder="Search topics…"
            className="flex-1"
          />
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
        <Select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="sm:w-48"
        >
          <option value="">All categories</option>
          {FORUM_CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {humanize(value)}
            </option>
          ))}
        </Select>
      </div>

      {topics.length === 0 ? (
        <Card className="mt-7 p-12 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
            <svg aria-hidden="true" className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M7 7h10M7 12h7M5 4h14v16l-4-3H5V4Z" />
            </svg>
          </span>
          <p className="mt-4 font-semibold text-ink">No topics yet</p>
          <p className="mt-2 text-sm text-muted">
            Start the first conversation — colleagues can reply with ideas and offers to collaborate.
          </p>
          <div className="mt-5">
            <Button onClick={() => setComposing(true)}>Start a topic</Button>
          </div>
        </Card>
      ) : (
        <div className="mt-7 grid gap-4 lg:grid-cols-[340px_1fr]">
          <Card className="overflow-hidden">
            <ul className="divide-y divide-line">
              {topics.map((topic) => {
                const selected = topic.id === activeId;
                return (
                  <li key={topic.id}>
                    <button
                      type="button"
                      onClick={() => setActiveId(topic.id)}
                      className={cx(
                        "w-full px-4 py-3.5 text-left transition",
                        selected ? "bg-indigo-50" : "hover:bg-slate-50",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className={cx("text-sm font-semibold", selected ? "text-indigo-800" : "text-ink")}>
                          {topic.title}
                        </p>
                        <Badge tone={selected ? "indigo" : "neutral"}>{humanize(topic.category)}</Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{topic.body}</p>
                      <p className="mt-2 text-[11px] text-muted">
                        {authorName(topic)} · {topic.reply_count}{" "}
                        {topic.reply_count === 1 ? "reply" : "replies"} · {formatWhen(topic.last_activity_at)}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card className="flex min-h-[28rem] flex-col p-5 sm:p-6">
            {loadingThread || !activeTopic ? (
              <Loading label="Loading discussion" />
            ) : (
              <>
                <div className="border-b border-line pb-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge tone="indigo">{humanize(activeTopic.category)}</Badge>
                        <span className="text-xs text-muted">{formatWhen(activeTopic.created_at)}</span>
                      </div>
                      <h2 className="text-xl font-semibold tracking-tight text-ink">{activeTopic.title}</h2>
                    </div>
                    {user?.id === activeTopic.author_id && (
                      <Button
                        variant="danger"
                        size="sm"
                        loading={deletingId === activeTopic.id}
                        onClick={() => void removeTopic(activeTopic.id)}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                  <div className="mt-4 flex items-center gap-3">
                    <Avatar name={authorName(activeTopic)} size={36} />
                    <div>
                      <Link
                        to={`/teachers/${activeTopic.author_id}`}
                        className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                      >
                        {authorName(activeTopic)}
                      </Link>
                      <p className="text-xs text-muted">Original post</p>
                    </div>
                  </div>
                  <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-ink">{activeTopic.body}</p>
                </div>

                <div className="flex-1 space-y-4 py-5">
                  {posts.length === 0 ? (
                    <p className="text-sm text-muted">No replies yet — be the first to jump in.</p>
                  ) : (
                    posts.map((post) => (
                      <div key={post.id} className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <Avatar name={authorName(post)} size={32} />
                            <div>
                              <Link
                                to={`/teachers/${post.author_id}`}
                                className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                              >
                                {authorName(post)}
                              </Link>
                              <p className="text-[11px] text-muted">{formatWhen(post.created_at)}</p>
                            </div>
                          </div>
                          {user?.id === post.author_id && (
                            <button
                              type="button"
                              className="text-xs font-medium text-rose-600 hover:text-rose-700 disabled:opacity-50"
                              disabled={deletingId === post.id}
                              onClick={() => void removePost(post.id)}
                            >
                              {deletingId === post.id ? "Removing…" : "Delete"}
                            </button>
                          )}
                        </div>
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink">{post.content}</p>
                      </div>
                    ))
                  )}
                </div>

                <form className="border-t border-line pt-4" onSubmit={sendReply}>
                  <Field label="Reply">
                    <textarea
                      className={TEXTAREA}
                      rows={3}
                      value={reply}
                      onChange={(e) => setReply(e.target.value)}
                      placeholder="Share an idea, resource, or offer to collaborate…"
                      maxLength={5000}
                      required
                    />
                  </Field>
                  <div className="mt-3">
                    <Button type="submit" loading={replying} disabled={!reply.trim()}>
                      Post reply
                    </Button>
                  </div>
                </form>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
