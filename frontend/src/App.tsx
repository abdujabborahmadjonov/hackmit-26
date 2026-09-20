import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Logo } from "./components/Logo";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useAuth } from "./auth/AuthContext";
import { Avatar, Loading, cx } from "./components/ui";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ProfileSetup from "./pages/ProfileSetup";
import Recommendations from "./pages/Recommendations";
import Search from "./pages/Search";
import TeacherDetail from "./pages/TeacherDetail";
import Resources from "./pages/Resources";
import Connections from "./pages/Connections";
import Messages from "./pages/Messages";
import Mentors from "./pages/Mentors";
import MentorProfile from "./pages/MentorProfile";
import Forum from "./pages/Forum";
import Classes from "./pages/Classes";
import ClassSearch from "./pages/ClassSearch";
import ClassPlanning from "./pages/ClassPlanning";
import TechniqueDetail from "./pages/TechniqueDetail";
import StudentRate from "./pages/StudentRate";

// Two things are deliberately absent. Mentor is reached from the pinned
// educators at the top of Discover, in context with the rest of the network;
// Network itself is in the account menu, with the other things that are yours.
const NAV = [
  { to: "/", label: "Matches", icon: "spark", end: true },
  { to: "/classes", label: "Classes", icon: "class" },
  { to: "/search", label: "Discover", icon: "search" },
  { to: "/resources", label: "Resources", icon: "book" },
  { to: "/forum", label: "Forum", icon: "forum" },
  { to: "/messages", label: "Messages", icon: "message" },
];

function NavIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    spark: <path d="m12 3 1.2 4.1L17 9l-3.8 1.9L12 15l-1.2-4.1L7 9l3.8-1.9L12 3ZM5 14l.7 2.3L8 17.5l-2.3 1.2L5 21l-.7-2.3L2 17.5l2.3-1.2L5 14Z" />,
    class: <><path d="M4 19V5a1 1 0 0 1 1-1h6v16H5a1 1 0 0 1-1-1Z" /><path d="M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5V4Z" /><path d="M8 8h2M8 12h2" /></>,
    search: <><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" /><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5v-16Z" /></>,
    forum: <><path d="M7 7h10M7 12h7M5 4h14v16l-4-3H5V4Z" /></>,
    people: <><circle cx="9" cy="8" r="3" /><path d="M3 19c.5-3.5 2.5-5 6-5s5.5 1.5 6 5M16 5.5a3 3 0 0 1 0 5.8M17 14c2.3.4 3.6 1.8 4 4" /></>,
    message: <path d="M4 5h16v11H9l-5 4V5Z" />,
    edit: <path d="M4 20h4L19 9a2.5 2.5 0 0 0-3.5-3.5L4 16v4Z" />,
    exit: <><path d="M10 4H5v16h5" /><path d="M15 8l4 4-4 4M19 12H9" /></>,
    mentor: <><circle cx="12" cy="7.5" r="3.5" /><path d="M5 20c.6-4 3.3-6 7-6s6.4 2 7 6" /><path d="M17.5 3.2a3 3 0 0 1 0 4.6" /></>,
  };
  return (
    <svg aria-hidden="true" className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

/** Everything about you, behind your own face.
 *
 *  These were three controls competing for the same corner. One button that
 *  looks like you, holding the things that are yours. */
function AccountMenu({
  name,
  firstName,
  myPageTo,
  onSignOut,
}: {
  name: string;
  firstName?: string;
  myPageTo: string;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const location = useLocation();

  // Navigating away should close it, however the navigation happened.
  useEffect(() => setOpen(false), [location.pathname]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item =
    "press flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm font-medium";

  return (
    <div ref={wrapper} className="relative shrink-0">
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cx(
          "press flex items-center gap-2 rounded-xl p-1.5 hover:bg-slate-100",
          open && "bg-slate-100",
        )}
      >
        <span className="relative">
          <Avatar name={name} size={32} />
          <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-paper bg-emerald-500" />
        </span>
        <span className="hidden text-sm font-medium text-ink sm:block">{firstName}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className={cx(
            "h-3.5 w-3.5 text-muted transition-transform",
            open && "rotate-180",
          )}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="rise absolute right-0 top-full z-30 mt-2 w-56 rounded-2xl bg-white p-1.5 shadow-lg ring-1 ring-line"
        >
          <div className="px-2.5 pb-2 pt-1.5">
            <p className="truncate text-sm font-semibold text-ink">{name}</p>
          </div>
          <div className="my-1 h-px bg-line" />

          <NavLink role="menuitem" to={myPageTo} className={cx(item, "text-ink hover:bg-slate-100")}>
            <NavIcon name="people" />
            My public page
          </NavLink>
          <NavLink role="menuitem" to="/profile" className={cx(item, "text-ink hover:bg-slate-100")}>
            <NavIcon name="edit" />
            Edit profile
          </NavLink>
          <NavLink
            role="menuitem"
            to="/connections"
            className={cx(item, "text-ink hover:bg-slate-100")}
          >
            <NavIcon name="people" />
            Network
          </NavLink>

          <div className="my-1 h-px bg-line" />
          <button
            role="menuitem"
            type="button"
            onClick={onSignOut}
            className={cx(item, "text-rose-600 hover:bg-rose-50")}
          >
            <NavIcon name="exit" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { user, profile, logout } = useAuth();
  const name = user ? `${user.first_name} ${user.last_name}` : "";
  const myPageTo = user && profile ? `/teachers/${user.id}` : "/profile";
  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-20 border-b border-line/80 bg-paper/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-5 px-4 sm:px-6">
          <NavLink
            to="/"
            className="press flex shrink-0 items-center gap-2.5 font-semibold tracking-tight text-ink"
          >
            <Logo size={32} />
            EduMatch
          </NavLink>
          <nav className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto md:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cx(
                    "press flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium",
                    isActive ? "bg-indigo-50 text-indigo-700" : "text-muted hover:bg-slate-100 hover:text-ink",
                  )
                }
              >
                <NavIcon name={item.icon} />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <AccountMenu name={name} firstName={user?.first_name} myPageTo={myPageTo} onSignOut={logout} />
        </div>
      </header>
      <main key={useLocation().pathname} className="rise mx-auto max-w-6xl px-4 py-8 pb-28 sm:px-6 sm:py-10 md:pb-10">
        {children}
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-6 border-t border-line bg-white/95 px-1 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-1.5 backdrop-blur-xl md:hidden">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cx(
                "press flex min-w-0 flex-col items-center gap-1 rounded-xl px-0.5 py-1.5 text-[9px] font-medium sm:text-[10px]",
                isActive ? "text-indigo-700" : "text-muted",
              )
            }
          >
            <NavIcon name={item.icon} />
            <span className="truncate">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, profile, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading label="Signing you in" />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  // Matching is profile-driven, so onboarding comes before anything else.
  if (!profile && location.pathname !== "/profile") return <Navigate to="/profile" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  const { user, loading } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={loading ? <Loading /> : user ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/register"
        element={loading ? <Loading /> : user ? <Navigate to="/" replace /> : <Register />}
      />
      <Route path="/rate/:token" element={<StudentRate />} />
      <Route
        path="/"
        element={
          loading ? (
            <Loading />
          ) : !user ? (
            // Logged-out visitors get the pitch, not a bare login form.
            <Landing />
          ) : (
            <RequireAuth>
              <Recommendations />
            </RequireAuth>
          )
        }
      />
      <Route
        path="/profile"
        element={
          <RequireAuth>
            <ProfileSetup />
          </RequireAuth>
        }
      />
      <Route
        path="/search"
        element={
          <RequireAuth>
            <Search />
          </RequireAuth>
        }
      />
      <Route
        path="/teachers/:userId"
        element={
          <RequireAuth>
            <TeacherDetail />
          </RequireAuth>
        }
      />
      <Route
        path="/mentor"
        element={
          <RequireAuth>
            <Mentors />
          </RequireAuth>
        }
      />
      <Route
        path="/mentor/:slug"
        element={
          <RequireAuth>
            <MentorProfile />
          </RequireAuth>
        }
      />
      <Route
        path="/resources"
        element={
          <RequireAuth>
            <Resources />
          </RequireAuth>
        }
      />
      <Route
        path="/connections"
        element={
          <RequireAuth>
            <Connections />
          </RequireAuth>
        }
      />
      <Route
        path="/messages"
        element={
          <RequireAuth>
            <Messages />
          </RequireAuth>
        }
      />
      <Route
        path="/forum"
        element={
          <RequireAuth>
            <Forum />
          </RequireAuth>
        }
      />
      <Route
        path="/classes"
        element={
          <RequireAuth>
            <Classes />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:classId/search"
        element={
          <RequireAuth>
            <ClassSearch />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:classId/planning"
        element={
          <RequireAuth>
            <ClassPlanning />
          </RequireAuth>
        }
      />
      <Route
        path="/techniques/:id"
        element={
          <RequireAuth>
            <TechniqueDetail />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
