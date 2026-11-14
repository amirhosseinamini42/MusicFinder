-- Per-user write isolation for public profile avatars.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('mf-avatars', 'mf-avatars', true, 3145728, array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;
drop policy if exists "mf_avatars_insert_own" on storage.objects;
create policy "mf_avatars_insert_own" on storage.objects for insert to authenticated
with check (bucket_id = 'mf-avatars' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "mf_avatars_update_own" on storage.objects;
create policy "mf_avatars_update_own" on storage.objects for update to authenticated
using (bucket_id = 'mf-avatars' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'mf-avatars' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "mf_avatars_delete_own" on storage.objects;
create policy "mf_avatars_delete_own" on storage.objects for delete to authenticated
using (bucket_id = 'mf-avatars' and (storage.foldername(name))[1] = auth.uid()::text);
