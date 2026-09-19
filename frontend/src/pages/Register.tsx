import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, ErrorNote, Field, Input } from "../components/ui";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function update(key: keyof typeof form) {
    return (event: { target: { value: string } }) =>
      setForm((current) => ({ ...current, [key]: event.target.value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(form);
      navigate("/profile");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Create your account</h1>
      <p className="mt-2 text-sm text-muted">
        Next you'll describe how you teach — that's what the matching runs on.
      </p>

      <Card className="mt-6 p-6">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name">
              <Input value={form.first_name} onChange={update("first_name")} required />
            </Field>
            <Field label="Last name">
              <Input value={form.last_name} onChange={update("last_name")} required />
            </Field>
          </div>
          <Field label="Email">
            <Input type="email" value={form.email} onChange={update("email")} required />
          </Field>
          <Field label="Password" hint="At least 8 characters, with a letter and a number.">
            <Input
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={update("password")}
              minLength={8}
              required
            />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" loading={busy} className="w-full">
            Create account
          </Button>
        </form>
      </Card>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-700">
          Sign in
        </Link>
      </p>
    </div>
  );
}
