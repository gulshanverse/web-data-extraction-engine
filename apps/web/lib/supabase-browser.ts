"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
let client: SupabaseClient | null = null;

export function isSupabaseAuthConfigured(): boolean {
  return Boolean(url && key);
}

export function supabaseBrowserClient(): SupabaseClient | null {
  if (!url || !key) return null;
  client ??= createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true } });
  return client;
}

export async function getSupabaseAccessToken(): Promise<string | null> {
  const browser = supabaseBrowserClient();
  if (!browser) return null;
  const { data } = await browser.auth.getSession();
  return data.session?.access_token ?? null;
}
