"use client";

import { type FormEvent, useEffect, useState } from "react";

import { isSupabaseAuthConfigured, supabaseBrowserClient } from "@/lib/supabase-browser";

export function AuthGate({ children }: Readonly<{ children: React.ReactNode }>) {
  const [ready, setReady] = useState(!isSupabaseAuthConfigured());
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const browser = supabaseBrowserClient();
    if (!browser) return;
    void browser.auth.getSession().then(({ data }) => setReady(Boolean(data.session)));
    const { data: subscription } = browser.auth.onAuthStateChange((_event, session) => setReady(Boolean(session)));
    return () => subscription.subscription.unsubscribe();
  }, []);

  if (ready) return <>{children}</>;

  async function sendMagicLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const browser = supabaseBrowserClient();
    if (!browser) return;
    const { error } = await browser.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } });
    setNotice(error ? "Sign-in could not be started safely." : "Check your email for the secure sign-in link.");
  }

  return (
    <main className="auth-gate" aria-labelledby="auth-title">
      <p className="overline">Authenticated workspace</p>
      <h1 id="auth-title">Sign in to access your extraction workspace.</h1>
      <p>Use the email address registered with the configured Supabase project. No credential is sent to the API.</p>
      <form onSubmit={sendMagicLink}>
        <label htmlFor="auth-email">Email address</label>
        <input id="auth-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
        <button type="submit">Send secure sign-in link</button>
      </form>
      {notice && <p role="status">{notice}</p>}
    </main>
  );
}
