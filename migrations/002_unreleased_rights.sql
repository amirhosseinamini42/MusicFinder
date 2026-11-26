-- MusicFinder 002: admin-controlled "Unreleased" flag + one-time rights acknowledgment.
-- ADDITIVE ONLY. NOT applied automatically. Run after 001, in the Supabase SQL editor.
alter table public.mf_tracks add column if not exists is_unreleased boolean not null default false;

create table if not exists public.mf_rights_ack (
  email     text primary key check (email = lower(email)),
  acked_at  timestamptz not null default now()
);
alter table public.mf_rights_ack enable row level security;
revoke all on public.mf_rights_ack from anon, authenticated;
