/* Compact shared sign-in/profile dialog for MusicFinder. */
(function (w, d) {
    "use strict";
    let mode = "login";
    let user = null;
    const esc = value => String(value || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const messages = {
        invalid_credentials: "Email or password is incorrect.",
        email_not_confirmed: "Please verify your email before signing in.",
        user_already_exists: "An account with this email already exists.",
        email_exists: "An account with this email already exists.",
        weak_password: "Choose a stronger password with at least 8 characters.",
        over_email_send_rate_limit: "Too many emails were requested. Wait a little and try again.",
        provider_disabled: "This sign-in provider is not enabled yet. Finish its setup in Supabase.",
        flow_state_not_found: "The sign-in session expired. Start again from the MusicFinder sign-in page.",
        otp_expired: "This confirmation link has expired. Request a new email and try again.",
        redirect_to_not_allowed: "The return address is not allowed in Supabase Auth URL Configuration.",
        email_address_invalid: "Enter a valid email address.",
        same_password: "Choose a password different from your current password.",
        "Invalid login credentials": "Email or password is incorrect.",
        "Email not confirmed": "Please verify your email before signing in.",
        "User already registered": "An account with this email already exists.",
        "Password should be at least 6 characters": "Use a password with at least 8 characters.",
        auth_sdk_unavailable: "The sign-in service could not load. Refresh and try again.",
        auth_not_configured: "The sign-in service is not configured yet.",
        avatar_invalid: "Choose a JPG, PNG or WebP image under 3 MB."
    };
    function errorText(error) {
        const raw = error && (error.code || error.message) || "Something went wrong. Please try again.";
        return messages[raw] || raw.replace(/<[^>]*>/g, "").slice(0, 180);
    }
    function ensureHost() {
        let host = d.getElementById("mfAuthOverlay");
        if (!host) { host = d.createElement("div"); host.id = "mfAuthOverlay"; host.className = "mf-auth-overlay"; host.hidden = true; d.body.appendChild(host); }
        return host;
    }
    let previousOverflow = "";
    function close() {
        const host = d.getElementById("mfAuthOverlay");
        if (host) { host.hidden = true; host.innerHTML = ""; host.onkeydown = null; }
        d.body.style.overflow = previousOverflow;
    }
    function showMessage(text, kind) {
        const el = d.querySelector("#mfAuthMessage");
        if (el) { el.textContent = text; el.className = "mf-auth-message" + (kind ? " " + kind : ""); el.hidden = !text; }
    }
    function render() {
        const host = ensureHost();
        if (host.hidden) previousOverflow = d.body.style.overflow;
        d.body.style.overflow = "hidden";
        host.hidden = false;
        const profile = mode === "profile";
        const recovery = mode === "recovery";
        const signup = mode === "signup";
        const title = profile ? "Your account" : recovery ? "Choose a new password" : signup ? "Create your account" : "Welcome back";
        host.innerHTML = `<section class="mf-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="mfAuthTitle">
            <button class="mf-auth-close" type="button" aria-label="Close">×</button>
            <div class="mf-auth-brand"><span class="mf-auth-brand-mark">M</span><span>MusicFinder</span></div>
            <div class="mf-auth-eyebrow">YOUR MUSIC SPACE</div><h2 id="mfAuthTitle">${title}</h2>
            ${profile ? `<p class="mf-auth-muted">${esc(user && user.email)}</p>` : `<p class="mf-auth-muted">One account for MusicFinder and its admin panel.</p>`}
            <div id="mfAuthMessage" class="mf-auth-message" hidden></div>
            ${profile ? `<form id="mfProfileForm"><label>Display name<input name="name" type="text" maxlength="80" required value="${esc(user && (user.name || user.user_metadata?.full_name || user.user_metadata?.name))}"></label>
                <label>Profile photo <input name="avatar" type="file" accept="image/png,image/jpeg,image/webp"></label>
                <label for="mfProfilePassword">New password</label><div class="mf-auth-password-field"><input id="mfProfilePassword" name="password" type="password" minlength="8" autocomplete="new-password" placeholder="Leave blank to keep current"><button class="mf-auth-password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show password</button></div>
                <button class="mf-auth-primary" type="submit">Save changes</button></form>
                <button class="mf-auth-secondary" id="mfAuthSignOut" type="button">Sign out</button>` : recovery ?
                `<form id="mfRecoveryForm"><label for="mfRecoveryPassword">New password</label><div class="mf-auth-password-field"><input id="mfRecoveryPassword" name="password" type="password" minlength="8" autocomplete="new-password" required><button class="mf-auth-password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show password</button></div><button class="mf-auth-primary" type="submit">Update password</button></form>` :
                `<div class="mf-auth-tabs"><button type="button" data-mode="login" class="${!signup ? "active" : ""}">Sign in</button><button type="button" data-mode="signup" class="${signup ? "active" : ""}">Create account</button></div>
                <form id="mfAuthForm">${signup ? `<label>Your name<input name="name" type="text" maxlength="80" autocomplete="name" required></label>` : ""}
                <label>Email<input name="email" type="email" maxlength="254" autocomplete="email" required></label>
                <label for="mfAuthPassword">Password</label><div class="mf-auth-password-field"><input id="mfAuthPassword" name="password" type="password" minlength="8" autocomplete="${signup ? "new-password" : "current-password"}" required><button class="mf-auth-password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show password</button></div>
                <button class="mf-auth-primary" type="submit">${signup ? "Create account" : "Sign in"}</button></form>
                ${!signup ? `<button class="mf-auth-link" id="mfForgot" type="button">Forgot password?</button>` : `<button class="mf-auth-link" id="mfResend" type="button" hidden>Resend verification email</button>`}
                <div class="mf-auth-divider"><span>OR</span></div><button class="mf-auth-google" id="mfGoogle" type="button"><span class="mf-auth-google-mark" aria-hidden="true">G</span><span>Continue with Google</span></button>`}
        </section>`;
        host.querySelectorAll(".mf-auth-password-toggle").forEach(toggle => {
            toggle.onclick = () => {
                const input = toggle.parentElement.querySelector("input");
                const visible = input.type === "password";
                input.type = visible ? "text" : "password";
                toggle.textContent = visible ? "Hide password" : "Show password";
                toggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
                toggle.setAttribute("aria-pressed", String(visible));
            };
        });
        host.querySelector(".mf-auth-close").onclick = close;
        host.onclick = event => { if (event.target === host) close(); };
        host.onkeydown = event => {
            if (event.key === "Escape") { event.preventDefault(); close(); return; }
            if (event.key !== "Tab") return;
            const items = Array.from(host.querySelectorAll('button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])'));
            if (!items.length) return;
            const first = items[0], last = items[items.length - 1];
            if (event.shiftKey && d.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && d.activeElement === last) { event.preventDefault(); first.focus(); }
        };
        host.querySelectorAll("[data-mode]").forEach(button => button.onclick = () => { mode = button.dataset.mode; render(); });
        const form = host.querySelector("#mfAuthForm");
        if (form) form.onsubmit = async event => {
            event.preventDefault(); const data = new FormData(form); const submit = form.querySelector("button[type=submit]"); submit.disabled = true;
            try {
                await w.MFAuth.init();
                if (signup) {
                    const result = await w.MFAuth.signUp(data.get("name"), data.get("email"), data.get("password"));
                    if (!result.session) {
                        showMessage("Check your inbox and verify your email before signing in.", "success");
                        const resend = host.querySelector("#mfResend"); if (resend) resend.hidden = false;
                    } else close();
                } else { await w.MFAuth.signIn(data.get("email"), data.get("password")); close(); }
            } catch (error) { showMessage(errorText(error), "error"); }
            finally { submit.disabled = false; }
        };
        const resend = host.querySelector("#mfResend");
        if (resend) resend.onclick = async () => {
            const email = form && form.elements.email.value.trim();
            if (!email) { showMessage("Enter your email address first.", "error"); return; }
            resend.disabled = true;
            try { await w.MFAuth.resendSignup(email); showMessage("If the address can receive a verification message, a new email has been sent.", "success"); }
            catch (error) { showMessage(errorText(error), "error"); }
            finally { resend.disabled = false; }
        };
        const google = host.querySelector("#mfGoogle");
        if (google) {
            google.onclick = async () => {
                google.disabled = true;
                try {
                    await w.MFAuth.init();
                    if (!w.MFAuth.isGoogleEnabled()) {
                        showMessage("Google sign-in is not enabled for this project yet.", "error");
                        return;
                    }
                    await w.MFAuth.signInWithGoogle();
                } catch (error) { showMessage(errorText(error), "error"); }
                finally { google.disabled = false; }
            };
        }
        const forgot = host.querySelector("#mfForgot");
        if (forgot) forgot.onclick = async () => {
            const email = form.elements.email.value.trim();
            if (!email) { showMessage("Enter your email address first.", "error"); form.elements.email.focus(); return; }
            try { await w.MFAuth.resetPassword(email); showMessage("Password reset instructions have been sent if the account exists.", "success"); }
            catch (error) { showMessage(errorText(error), "error"); }
        };
        const recoveryForm = host.querySelector("#mfRecoveryForm");
        if (recoveryForm) recoveryForm.onsubmit = async event => {
            event.preventDefault(); const button = recoveryForm.querySelector("button"); button.disabled = true;
            try { await w.MFAuth.updatePassword(new FormData(recoveryForm).get("password")); showMessage("Password updated. You can now use it to sign in.", "success"); setTimeout(close, 1200); }
            catch (error) { showMessage(errorText(error), "error"); }
            finally { button.disabled = false; }
        };
        const profileForm = host.querySelector("#mfProfileForm");
        if (profileForm) profileForm.onsubmit = async event => {
            event.preventDefault(); const button = profileForm.querySelector("button[type=submit]"); button.disabled = true;
            try {
                const data = new FormData(profileForm); const name = String(data.get("name") || "").trim();
                if (!name) throw new Error("Enter your display name.");
                const updatedName = await w.MFAuth.updateName(name);
                if (user && updatedName) { user.name = name; user.user_metadata = { ...(user.user_metadata || {}), full_name: name }; }
                const photo = profileForm.elements.avatar.files[0];
                if (photo) {
                    const updatedPhoto = await w.MFAuth.uploadAvatar(photo);
                    if (user && updatedPhoto) { user.picture = updatedPhoto.user_metadata?.avatar_url || user.picture; user.user_metadata = updatedPhoto.user_metadata || user.user_metadata; }
                }
                const password = String(data.get("password") || ""); if (password) await w.MFAuth.updatePassword(password);
                showMessage("Profile updated.", "success");
            } catch (error) { showMessage(errorText(error), "error"); }
            finally { button.disabled = false; }
        };
        const signOut = host.querySelector("#mfAuthSignOut");
        if (signOut) signOut.onclick = async () => { signOut.disabled = true; try { await w.MFAuth.signOut(); close(); } catch (error) { showMessage(errorText(error), "error"); signOut.disabled = false; } };
        const first = host.querySelector("input") || host.querySelector(".mf-auth-close"); if (first) first.focus();
    }
    w.MFLoginPanel = Object.freeze({ open: (nextMode, nextUser) => { mode = nextMode || "login"; user = nextUser || null; render(); }, close });
})(window, document);
