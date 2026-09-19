import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./auth/AuthContext";
import { Avatar, Button, Loading, cx } from "./components/ui";
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

const NAV = [
  { to: "/", label: "Matches", end: true },
  { to: "/search", label: "Search" },
  { to: "/resources", label: "Resources" },
  { to: "/connections", label: "Connections" },
  { to: "/messages", label: "Messages" },
];

function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const name = user ? `${user.first_name} ${user.last_name}` : "";
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-line bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 sm:gap-6">
          <NavLink to="/" className="flex items-center gap-2 font-semibold text-ink">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-indigo-600 text-sm text-white">
              E
            </span>
            EduMatch
          </NavLink>
          <nav className="-mx-1 flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cx(
                    "rounded-lg px-3 py-1.5 text-sm font-medium transition",
                    isActive ? "bg-indigo-50 text-indigo-700" : "text-muted hover:bg-slate-100",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            <NavLink to="/profile" className="flex items-center gap-2">
              <Avatar name={name} size={30} />
              <span className="hidden text-sm font-medium text-ink sm:block">
                {user?.first_name}
              </span>
            </NavLink>
            <Button variant="ghost" size="sm" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
