import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { Button, ErrorNote, Field, Input } from "../components/ui";

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
    <AuthShell
      eyebrow="Join EduMatch"
      title="Build a network around your teaching"
      description="Create your account, then tell us what your classroom feels like. Your first matches are only one short profile away."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
            Sign in
          </Link>
        </>
      }
    >
      <div className="rounded-2xl bg-white p-6 ring-1 ring-line shadow-sm">
        <form onSubmit={submit} className="space-y-5">
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
            Create account and continue
          </Button>
        </form>
        <p className="mt-4 text-center text-xs leading-5 text-muted">
          By continuing, you agree to keep EduMatch a constructive, educator-first community.
        </p>
      </div>
    </AuthShell>
  );
}
