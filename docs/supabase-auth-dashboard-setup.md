# Supabase Auth dashboard setup

These are external dashboard settings. They are deliberately not changed by the repository code.

## URL Configuration

- Site URL: `https://musicfinder-web.vercel.app`
- Redirect URL: `https://musicfinder-web.vercel.app/**`
- Preview Redirect URL: `https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/**`
- Keep `http://localhost:30000/**` only if local development still needs it. Do not use localhost as the Site URL.

The signup client now requests `/?auth=confirmed` on the origin currently serving the site. Both production and the named Preview origin therefore need to be allow-listed.

## Google provider

1. Enable Google in Supabase Auth → Sign In / Providers.
2. Add the Google OAuth Client ID and Client Secret in the Supabase dashboard. Never put either value in frontend code or this repository.
3. In the Google OAuth client, add this exact Supabase callback URI as an authorized redirect URI:
   `https://tgkkasvidfzlerbgjtkb.supabase.co/auth/v1/callback`
4. Keep the application's production and Preview URLs in Supabase URL Configuration as listed above.

## Branded email sender

Use a custom SMTP server in Supabase Auth → SMTP Settings. For the requested Gmail sender, the intended values are:

- Sender email: `musicfinder.web00@gmail.com`
- Sender name: `MusicFinder`
- SMTP host: `smtp.gmail.com`
- SMTP port: `465` (SSL) or `587` (STARTTLS), according to the selected security mode
- SMTP username: `musicfinder.web00@gmail.com`
- SMTP password: a Google App Password entered directly in the Supabase dashboard by the account owner; never share it in chat or commit it

Gmail may require 2-Step Verification before an App Password can be created. The Gmail account owner should manage that credential and enter it directly into Supabase.

## Confirmation email template

Copy the complete HTML from `docs/supabase-confirmation-email.html` into Supabase Auth → Email Templates → Confirm signup. It uses Supabase's `{{ .ConfirmationURL }}` and `{{ .SiteURL }}` variables. The header reproduces the existing MusicFinder `M` monogram and wordmark used by the account panel; the site currently has no separate standalone logo asset.

The sender name/address are SMTP settings, not template fields. On newer Free projects, Supabase may require custom SMTP before allowing custom auth email templates.
