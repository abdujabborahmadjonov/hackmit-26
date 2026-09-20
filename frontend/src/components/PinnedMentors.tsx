import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Mentor } from "../api/types";
import { Avatar, Badge, Card } from "./ui";

/** Educators pinned to the top of the directory.
 *
 *  Deliberately not a TeacherCard: these are not accounts. A card that looked
 *  like a member profile would read as the person's own, which is exactly the
 *  claim we are not making - so it says what it is, and links to the guide
 *  rather than to a profile, a connect button or a message thread. */
export function PinnedMentors() {
  const [mentors, setMentors] = useState<Mentor[]>([]);

  useEffect(() => {
    // A directory that renders without its pinned row is fine; an error here
    // should not take the search page down with it.
    api
      .mentors()
      .then((all) => setMentors(all.filter((mentor) => mentor.pinned)))
      .catch(() => setMentors([]));
  }, []);

  if (mentors.length === 0) return null;

  return (
    <section className="mt-6">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Pinned</h2>
        <p className="text-xs text-muted">Learn from their published teaching</p>
      </div>
      <div className="stagger grid gap-4 sm:grid-cols-2">
        {mentors.map((mentor) => (
          <Card key={mentor.slug} className="h-full p-5" interactive>
            <Link to={`/mentor/${mentor.slug}`} className="flex h-full items-start gap-4">
              <Avatar name={mentor.avatar_seed || mentor.name} src={mentor.avatar_url} size={46} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate font-semibold text-ink">{mentor.name}</p>
                  <Badge tone="indigo">
                    {mentor.mode === "guide" ? "AI guide" : "AI persona"}
                  </Badge>
                </div>
                <p className="truncate text-sm text-muted">
                  {[mentor.title, mentor.institution].filter(Boolean).join(" · ")}
                </p>
                {mentor.known_for && (
                  <p className="mt-2 line-clamp-2 text-sm leading-5 text-ink/80">
                    {mentor.known_for}
                  </p>
                )}
                <p className="mt-3 text-xs font-medium text-indigo-700">
                  {mentor.mode === "guide"
                    ? `Ask about ${mentor.name.split(" ").slice(-1)[0]}'s teaching →`
                    : "Start a conversation →"}
                </p>
              </div>
            </Link>
          </Card>
        ))}
      </div>
      <p className="mt-2 text-xs leading-5 text-muted">
        Pinned educators are AI guides to published material, not member accounts — you cannot
        connect to or message them.
      </p>
    </section>
  );
}
