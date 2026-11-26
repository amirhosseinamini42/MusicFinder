-- MusicFinder listening history and taste summary.
-- Additive only. Not applied automatically; review and apply manually in Supabase.
-- Rollback: 20261126170000_listening_history.down.sql

create table if not exists public.mf_listens (
  user_sub     text not null check (char_length(user_sub) between 1 and 255),
  song_id      text not null check (char_length(song_id) between 1 and 64),
  listened_at  timestamptz not null,
  song         jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  constraint mf_listens_user_song_time_unique unique (user_sub, song_id, listened_at)
);

create index if not exists mf_listens_user_recent
  on public.mf_listens (user_sub, listened_at desc);

alter table public.mf_listens enable row level security;
revoke all on table public.mf_listens from anon, authenticated;
grant all on table public.mf_listens to service_role;
