-- MusicFinder: uploads + admin roles. ADDITIVE ONLY (no drops, no changes to existing tables).
-- NOT applied automatically. Run manually in Supabase SQL editor after review.
-- Rollback: see 001_uploads_admin.down.sql

-- ---------- Admin allowlist / roles ----------
create table if not exists public.mf_admins (
  email       text primary key
              check (email = lower(email) and char_length(email) <= 254 and email ~ '^[^@\s]+@[^@\s]+$'),
  role        text not null check (role in ('owner','admin')),
  added_by    text,
  created_at  timestamptz not null default now(),
  revoked_at  timestamptz
);
-- at most one owner
create unique index if not exists mf_admins_single_owner on public.mf_admins ((role)) where role = 'owner';

-- DB-level backstop: the owner row can never be updated/deleted through normal queries,
-- and no row can be promoted to 'owner'. (The API never does either; this protects against bugs.)
create or replace function public.mf_admins_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    if old.role = 'owner' then raise exception 'owner row is protected'; end if;
    return old;
  end if;
  if tg_op = 'UPDATE' then
    if old.role = 'owner' then raise exception 'owner row is protected'; end if;
    if new.role = 'owner' then raise exception 'cannot promote to owner'; end if;
  end if;
  return new;
end $$;
drop trigger if exists mf_admins_guard on public.mf_admins;
create trigger mf_admins_guard before update or delete on public.mf_admins
  for each row execute function public.mf_admins_guard();

-- Bootstrap (initial allowlist). Presence here is NOT access: the API additionally requires a
-- verified Google ID token whose email_verified=true and email matches, on every request.
insert into public.mf_admins (email, role, added_by) values
  ('amirhosseinamini428@gmail.com', 'owner', 'bootstrap'),
  ('musicfinder.web00@gmail.com',   'admin', 'bootstrap'),
  ('amirhosseinamini528@gmail.com', 'admin', 'bootstrap')
on conflict (email) do nothing;

-- ---------- Tracks ----------
create table if not exists public.mf_tracks (
  id                uuid primary key default gen_random_uuid(),
  title             text not null check (char_length(title) between 1 and 200),
  artist            text not null check (char_length(artist) between 1 and 200),
  album             text not null default '' check (char_length(album) <= 200),
  description       text not null default '' check (char_length(description) <= 2000),
  status            text not null default 'draft' check (status in ('draft','review','published','unpublished')),
  download_enabled  boolean not null default false,
  rights_confirmed  boolean not null default false,
  -- live files (set only after server-side validation)
  audio_path        text, audio_ext text, audio_size bigint,
  cover_path        text, cover_ext text,
  -- files awaiting finalize (issued signed upload URL, not yet validated)
  audio_path_new    text, audio_ext_new text,
  cover_path_new    text, cover_ext_new text,
  client_request_id text,
  created_by        text not null,
  updated_by        text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  published_at      timestamptz
);
create unique index if not exists mf_tracks_idem on public.mf_tracks (created_by, client_request_id)
  where client_request_id is not null;
create index if not exists mf_tracks_public on public.mf_tracks (status, published_at desc);

-- RLS on, no policies: anon/authenticated keys cannot touch these tables. Only the server (service role).
alter table public.mf_admins enable row level security;
alter table public.mf_tracks enable row level security;

-- ---------- Storage buckets (private) ----------
-- Free plan: global per-file cap is 50 MB; we use 30 MB for audio.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types) values
  ('mf-audio',  'mf-audio',  false, 31457280, array['audio/mpeg','audio/mp4','audio/wav','audio/ogg','audio/flac']),
  ('mf-covers', 'mf-covers', false,  5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;
-- No storage.objects policies are created => no direct access with anon keys. Access is via
-- server-issued signed URLs only.
