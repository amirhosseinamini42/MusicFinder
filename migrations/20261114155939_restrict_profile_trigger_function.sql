-- Restrict direct RPC execution of the SECURITY DEFINER profile trigger function.
-- The auth.users trigger remains attached and continues to invoke this function.
revoke execute on function public.handle_new_musicfinder_user() from public, anon, authenticated;
