-- Rollback for 001. DESTRUCTIVE: deletes uploaded-track metadata and admin roles. Empty buckets first.
drop table if exists public.mf_tracks;
drop trigger if exists mf_admins_guard on public.mf_admins;
drop table if exists public.mf_admins;
drop function if exists public.mf_admins_guard();
-- delete from storage.buckets where id in ('mf-audio','mf-covers');  -- only after objects are removed via the Storage API
