# Supabase Auth dashboard setup

These are external dashboard settings. They are deliberately not changed by the repository code.

## URL Configuration

- Site URL: `https://musicfinder-web.vercel.app`
- Production Redirect URL: `https://musicfinder-web.vercel.app/**`
- Preview Redirect URL: `https://*-music-finder.vercel.app/**`
- Local Redirect URL: `http://localhost:3000/**` (the current local web server port)
- Add `http://localhost:30000/**` only if a separate local server actually uses port `30000`.

Never use a localhost address as the hosted project's Site URL. Keep the Site URL on the canonical Production domain. The local URL belongs only in the additional Redirect URLs allow-list.

The signup and resend-confirmation flows request `/?auth=confirmed` on the origin currently serving the site. Google OAuth returns to the page that started the flow (`/` or `/admin.html`). The wildcard above follows Vercel's documented Preview URL pattern and covers the current and future branch Preview domains; keep the production URL exact.

## Google provider

1. Enable Google in Supabase Auth → Sign In / Providers.
2. Add the Google OAuth Client ID and Client Secret in the Supabase dashboard. Never put either value in frontend code or this repository.
3. In the Google OAuth client, add this exact Supabase callback URI as an authorized redirect URI:
   `https://tgkkasvidfzlerbgjtkb.supabase.co/auth/v1/callback`
4. If the Google OAuth consent screen is still in Testing mode, add the intended test accounts under Test users. Keep the application's production and Preview URLs in Supabase URL Configuration as listed above.

## Branded email sender

Use a custom SMTP server in Supabase Auth → SMTP Settings. For the requested Gmail sender, the intended values are:

Supabase's built-in email sender is for testing: it only sends to addresses belonging to members of the Supabase organization and has a low project-wide hourly limit. Configure custom SMTP before expecting signup confirmation emails to reach arbitrary users. A successful signup API response does not prove that an email was delivered.

- Sender email: `musicfinder.web00@gmail.com`
- Sender name: `MusicFinder`
- SMTP host: `smtp.gmail.com`
- SMTP port: `465` (SSL) or `587` (STARTTLS), according to the selected security mode
- SMTP username: `musicfinder.web00@gmail.com`
- SMTP password: a Google App Password entered directly in the Supabase dashboard by the account owner; never share it in chat or commit it

Gmail may require 2-Step Verification before an App Password can be created. The Gmail account owner should manage that credential and enter it directly into Supabase.

## Confirmation email template

Copy the complete HTML from `docs/supabase-confirmation-email.html` into Supabase Auth → Email Templates → Confirm signup. It uses the public MusicFinder favicon as the email logo and Supabase's `{{ .SiteURL }}` and `{{ .TokenHash }}` variables.

The confirmation button opens `/confirm.html` first. The page waits for the user to press **Confirm email** before calling `verifyOtp`, so automated email-link previews do not consume the one-time token before the user opens it. After successful verification, the browser returns to `/?auth=confirmed` with the new session saved by Supabase Auth.

This template change is a dashboard action: paste the complete HTML into the Confirm signup template and save it. Repository changes do not update the Supabase dashboard automatically.

The sender name/address are SMTP settings, not template fields. On newer Free projects, Supabase may require custom SMTP before allowing custom auth email templates.
