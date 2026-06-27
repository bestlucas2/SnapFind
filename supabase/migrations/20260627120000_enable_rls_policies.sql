-- Enable Row Level Security and lock all application tables to server-side
-- access only.
--
-- Context
-- -------
-- SnapFind authenticates users itself (session cookies + bcrypt, see auth.py)
-- and never reads or writes these tables through the Supabase `anon` /
-- `authenticated` client keys. Every query goes through the backend over the
-- Session pooler connection, which connects as the `postgres` role — the table
-- owner — and therefore BYPASSES RLS. The Supabase Storage REST calls use the
-- `service_role` key, which also bypasses RLS.
--
-- Secure posture
-- --------------
-- RLS ON for every public table, with the only policies explicitly DENYING the
-- public-facing `anon` and `authenticated` roles. The backend keeps working
-- (owner bypass); a leaked anon key exposes nothing. This also clears the
-- Supabase "RLS enabled, no policy" advisor.
--
-- We deliberately do NOT use FORCE ROW LEVEL SECURITY: that would subject the
-- owner role to RLS as well and break the app.
--
-- Future: if you migrate auth to Supabase Auth and start querying these tables
-- from a client with the anon key, replace the deny policy with an ownership
-- policy, e.g.  USING (user_id = auth.uid())  (requires user_id to be a uuid
-- matching auth.users.id).
--
-- Idempotent: safe to re-run.

do $$
declare
  t text;
  app_tables text[] := array[
    'users',
    'screenshots',
    'tags',
    'saved_searches',
    'screenshot_tags'
  ];
begin
  foreach t in array app_tables loop
    -- Skip anything that doesn't exist yet (partial schema / fresh project).
    if to_regclass(format('public.%I', t)) is null then
      raise notice 'skipping %, table does not exist', t;
      continue;
    end if;

    execute format('alter table public.%I enable row level security;', t);

    execute format(
      'drop policy if exists "deny_anon_and_authenticated" on public.%I;', t
    );

    -- Single policy: clients holding the anon or authenticated key get nothing.
    -- The backend (postgres owner / service_role) bypasses RLS and is unaffected.
    execute format($pol$
      create policy "deny_anon_and_authenticated"
        on public.%I
        as permissive
        for all
        to anon, authenticated
        using (false)
        with check (false);
    $pol$, t);
  end loop;
end $$;
