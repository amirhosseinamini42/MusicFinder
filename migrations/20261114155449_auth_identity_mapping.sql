-- Stable account ownership across email/password and linked Google identities.
create table if not exists public.mf_auth_accounts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  owner_key text not null unique check (char_length(owner_key) between 1 and 255),
  legacy_google_sub text unique check (legacy_google_sub is null or char_length(legacy_google_sub) between 1 and 255),
  created_at timestamptz not null default now()
);
alter table public.mf_auth_accounts enable row level security;
revoke all on table public.mf_auth_accounts from anon, authenticated;
grant all on table public.mf_auth_accounts to service_role;
