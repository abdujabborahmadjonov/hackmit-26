import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { Button, ErrorNote, Field, Input } from "../components/ui";

const DEMO = { email: "demo_teacher@example.com", password: "DemoPassword123!" };

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent, credentials = { email, password }) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(credentials.email, credentials.password);
      navigate("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to your educator network"
      description="Return to your matches, conversations, and shared teaching resources."
      footer={
        <>
          New to EduMatch?{" "}
          <Link to="/register" className="font-semibold text-indigo-600 hover:text-indigo-700">
            Create an account
          </Link>
        </>
      }
    >
      <div className="rounded-2xl bg-white p-6 ring-1 ring-line shadow-sm">
        <form onSubmit={(e) => submit(e)} className="space-y-5">
          <Field label="Email">
            <Input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@school.edu"
              required
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" loading={busy} className="w-full">
            Sign in
          </Button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-line" />
          </div>
          <div className="relative flex justify-center">
            <span className="bg-white px-3 text-[11px] font-medium uppercase tracking-wider text-muted">
              or explore instantly
            </span>
          </div>
        </div>

        <div>
          <Button
            variant="secondary"
            className="w-full border-indigo-100 bg-indigo-50 text-indigo-700 ring-indigo-100 hover:bg-indigo-100"
            onClick={(e) => {
              setEmail(DEMO.email);
              setPassword(DEMO.password);
              void submit(e as unknown as FormEvent, DEMO);
            }}
          >
            Explore Alice's demo account
          </Button>
          <p className="mt-2 text-center text-xs text-muted">
            No setup required · project-based CS teacher in Boston
          </p>
        </div>
      </div>
    </AuthShell>
  );
}
