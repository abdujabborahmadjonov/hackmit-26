import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, ErrorNote, Field, Input } from "../components/ui";

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
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
      <div className="mb-8">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-600 font-semibold text-white">
          E
        </span>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-ink">
          Find the educators you'll teach best with
        </h1>
        <p className="mt-2 text-sm text-muted">
          EduMatch reads how you teach — not just what you teach — and explains every match it
          makes.
        </p>
      </div>

      <Card className="p-6">
        <form onSubmit={(e) => submit(e)} className="space-y-4">
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

        <div className="mt-4 border-t border-line pt-4">
          <Button
            variant="secondary"
            className="w-full"
            onClick={(e) => {
              setEmail(DEMO.email);
              setPassword(DEMO.password);
              void submit(e as unknown as FormEvent, DEMO);
            }}
          >
            Sign in as Alice (demo account)
          </Button>
          <p className="mt-2 text-center text-xs text-muted">
            High-school CS teacher in Boston, project-based. Her top match is Bob in Cambridge.
          </p>
        </div>
      </Card>

      <p className="mt-6 text-center text-sm text-muted">
        New here?{" "}
        <Link to="/register" className="font-medium text-indigo-600 hover:text-indigo-700">
          Create an account
        </Link>
      </p>
    </div>
  );
}
