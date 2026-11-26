-- Keep the admin guard trigger's name resolution independent of caller-controlled search_path.
alter function public.mf_admins_guard() set search_path = '';
