/* Compact shared sign-in/profile dialog for MusicFinder. */
(function (w, d) {
    "use strict";
    let mode = "login";
    let user = null;
    const isAdminPage = () => /(?:^|\/)(?:admin(?:\.html)?|adminpanel)(?:\/|$)/i.test(w.location.pathname);
    const isFa = () => d.documentElement.lang === "fa" || (isAdminPage() && (() => { try { return w.localStorage.getItem("musicFinderLang") === "fa"; } catch { return false; } })());
    const tr = (en, fa) => isFa() ? fa : en;
    const brandLogo = "/favicon.svg";
    const faCopy = {
        "Your account": "\u062d\u0633\u0627\u0628 \u06a9\u0627\u0631\u0628\u0631\u06cc \u0634\u0645\u0627",
        "Choose a new password": "\u0627\u0646\u062a\u062e\u0627\u0628 \u06af\u0630\u0631\u0648\u0627\u0698\u0647\u0654 \u062c\u062f\u06cc\u062f",
        "Forgot password?": "\u06af\u0630\u0631\u0648\u0627\u0698\u0647 \u0631\u0627 \u0641\u0631\u0627\u0645\u0648\u0634 \u06a9\u0631\u062f\u0647\u200c\u0627\u06cc\u062f\u061f",
        "Create your account": "\u0633\u0627\u062e\u062a \u062d\u0633\u0627\u0628 \u06a9\u0627\u0631\u0628\u0631\u06cc",
        "Welcome back": "\u062e\u0648\u0634 \u0628\u0631\u06af\u0634\u062a\u06cc\u062f",
        "YOUR MUSIC SPACE": "\u0641\u0636\u0627\u06cc \u0645\u0648\u0633\u06cc\u0642\u06cc \u0634\u0645\u0627",
        "Display name": "\u0646\u0627\u0645 \u0646\u0645\u0627\u06cc\u0634\u06cc",
        "Profile photo": "\u062a\u0635\u0648\u06cc\u0631 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644",
        "New password": "\u06af\u0630\u0631\u0648\u0627\u0698\u0647\u0654 \u062c\u062f\u06cc\u062f",
        "Leave blank to keep current": "\u0628\u0631\u0627\u06cc \u062d\u0641\u0638 \u06af\u0630\u0631\u0648\u0627\u0698\u0647\u0654 \u0641\u0639\u0644\u06cc \u062e\u0627\u0644\u06cc \u0628\u06af\u0630\u0627\u0631\u06cc\u062f",
        "Show password": "\u0646\u0645\u0627\u06cc\u0634 \u06af\u0630\u0631\u0648\u0627\u0698\u0647",
        "Hide password": "\u067e\u0646\u0647\u0627\u0646 \u06a9\u0631\u062f\u0646 \u06af\u0630\u0631\u0648\u0627\u0698\u0647",
        "Save changes": "\u0630\u062e\u06cc\u0631\u0647\u0654 \u062a\u063a\u06cc\u06cc\u0631\u0627\u062a",
        "Sign out": "\u062e\u0631\u0648\u062c \u0627\u0632 \u062d\u0633\u0627\u0628",
        "Update password": "\u062a\u063a\u06cc\u06cc\u0631 \u06af\u0630\u0631\u0648\u0627\u0698\u0647",
        "Back to sign in": "\u0628\u0627\u0632\u06af\u0634\u062a \u0628\u0647 \u0648\u0631\u0648\u062f",
        "Sign in": "\u0648\u0631\u0648\u062f",
        "Create account": "\u0633\u0627\u062e\u062a \u062d\u0633\u0627\u0628",
        "Email": "\u0627\u06cc\u0645\u06cc\u0644",
        "Password": "\u06af\u0630\u0631\u0648\u0627\u0698\u0647",
        "OR": "\u06cc\u0627",
        "Continue with Google": "\u0627\u062f\u0627\u0645\u0647 \u0628\u0627 Google",
        "Close": "\u0628\u0633\u062a\u0646",
        "Password recovery is temporarily unavailable while this feature is being updated and repaired. Please try again later.": "\u0628\u0627\u0632\u06cc\u0627\u0628\u06cc \u06af\u0630\u0631\u0648\u0627\u0698\u0647 \u0645\u0648\u0642\u062a\u0627\u064b \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a \u0648 \u067e\u0633 \u0627\u0632 \u062a\u06a9\u0645\u06cc\u0644 \u0627\u0635\u0644\u0627\u062d\u0627\u062a \u062f\u0648\u0628\u0627\u0631\u0647 \u0641\u0639\u0627\u0644 \u0645\u06cc\u200c\u0634\u0648\u062f.",
        invalid_credentials: "\u0627\u06cc\u0645\u06cc\u0644 \u06cc\u0627 \u06af\u0630\u0631\u0648\u0627\u0698\u0647 \u0646\u0627\u062f\u0631\u0633\u062a \u0627\u0633\u062a.",
        email_not_confirmed: "\u067e\u06cc\u0634 \u0627\u0632 \u0648\u0631\u0648\u062f\u060c \u0627\u06cc\u0645\u06cc\u0644 \u062e\u0648\u062f \u0631\u0627 \u062a\u0623\u06cc\u06cc\u062f \u06a9\u0646\u06cc\u062f.",
        user_already_exists: "\u0628\u0627 \u0627\u06cc\u0646 \u0627\u06cc\u0645\u06cc\u0644 \u0642\u0628\u0644\u0627\u064b \u062d\u0633\u0627\u0628 \u0633\u0627\u062e\u062a\u0647 \u0634\u062f\u0647 \u0627\u0633\u062a.",
        email_exists: "\u0628\u0627 \u0627\u06cc\u0646 \u0627\u06cc\u0645\u06cc\u0644 \u0642\u0628\u0644\u0627\u064b \u062d\u0633\u0627\u0628 \u0633\u0627\u062e\u062a\u0647 \u0634\u062f\u0647 \u0627\u0633\u062a.",
        weak_password: "\u06af\u0630\u0631\u0648\u0627\u0698\u0647 \u0628\u0627\u06cc\u062f \u062f\u0633\u062a\u200c\u06a9\u0645 ۸ \u0646\u0648\u06cc\u0633\u0647 \u062f\u0627\u0634\u062a\u0647 \u0628\u0627\u0634\u062f.",
        over_email_send_rate_limit: "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0627\u06cc\u0645\u06cc\u0644 \u0628\u06cc\u0634 \u0627\u0632 \u062d\u062f \u0628\u0648\u062f\u0647 \u0627\u0633\u062a\u061b \u06a9\u0645\u06cc \u0628\u0639\u062f \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 \u06a9\u0646\u06cc\u062f.",
        provider_disabled: "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0648\u0631\u0648\u062f \u0647\u0646\u0648\u0632 \u0641\u0639\u0627\u0644 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.",
        flow_state_not_found: "\u0646\u0634\u0633\u062a \u0648\u0631\u0648\u062f \u0645\u0646\u0642\u0636\u06cc \u0634\u062f\u0647 \u0627\u0633\u062a\u061b \u062f\u0648\u0628\u0627\u0631\u0647 \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f.",
        otp_expired: "\u067e\u06cc\u0648\u0646\u062f \u062a\u0623\u06cc\u06cc\u062f \u0645\u0646\u0642\u0636\u06cc \u0634\u062f\u0647 \u0627\u0633\u062a\u061b \u0627\u06cc\u0645\u06cc\u0644 \u062a\u0627\u0632\u0647\u200c\u0627\u06cc \u062f\u0631\u062e\u0648\u0627\u0633\u062a \u06a9\u0646\u06cc\u062f.",
        redirect_to_not_allowed: "\u0646\u0634\u0627\u0646\u06cc \u0628\u0627\u0632\u06af\u0634\u062a \u062f\u0631 \u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0627\u062d\u0631\u0627\u0632 \u0647\u0648\u06cc\u062a \u0645\u062c\u0627\u0632 \u0646\u06cc\u0633\u062a.",
        email_address_invalid: "\u06cc\u06a9 \u0646\u0634\u0627\u0646\u06cc \u0627\u06cc\u0645\u06cc\u0644 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f.",
        same_password: "\u06af\u0630\u0631\u0648\u0627\u0698\u0647\u200c\u0627\u06cc \u0645\u062a\u0641\u0627\u0648\u062a \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.",
        auth_sdk_unavailable: "\u0633\u0631\u0648\u06cc\u0633 \u0648\u0631\u0648\u062f \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0646\u0634\u062f. \u0635\u0641\u062d\u0647 \u0631\u0627 \u062a\u0627\u0632\u0647\u200c\u0633\u0627\u0632\u06cc \u0648 \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 \u06a9\u0646\u06cc\u062f.",
        auth_not_configured: "\u0633\u0631\u0648\u06cc\u0633 \u0648\u0631\u0648\u062f \u0647\u0646\u0648\u0632 \u067e\u06cc\u06a9\u0631\u0628\u0646\u062f\u06cc \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.",
        avatar_invalid: "\u06cc\u06a9 \u062a\u0635\u0648\u06cc\u0631 JPG\u060c PNG \u06cc\u0627 WebP \u06a9\u0648\u0686\u06a9\u200c\u062a\u0631 \u0627\u0632 ۳ \u0645\u06af\u0627\u0628\u0627\u06cc\u062a \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f."
    };
    function localizePanel(host) {
        if (!isFa()) return;
        const walker = d.createTreeWalker(host, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const original = node.nodeValue;
            const trimmed = original.trim();
            if (faCopy[trimmed]) node.nodeValue = original.replace(trimmed, faCopy[trimmed]);
        }
        host.querySelectorAll("[aria-label], [placeholder]").forEach(el => {
            for (const attr of ["aria-label", "placeholder"]) {
                const value = el.getAttribute(attr);
                if (value && faCopy[value]) el.setAttribute(attr, faCopy[value]);
            }
        });
    }
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
        return (isFa() && faCopy[raw]) || messages[raw] || raw.replace(/<[^>]*>/g, "").slice(0, 180);
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
        const forgot = mode === "forgot";
        const signup = mode === "signup";
        const title = profile ? tr("Your account", faCopy["Your account"]) : recovery ? tr("Choose a new password", faCopy["Choose a new password"]) : forgot ? tr("Forgot password?", faCopy["Forgot password?"]) : signup ? tr("Create your account", faCopy["Create your account"]) : tr("Welcome back", faCopy["Welcome back"]);
        const subtitle = isAdminPage()
            ? tr("Sign in to the MusicFinder admin workspace. Access is granted according to your account role.", "\u0628\u0631\u0627\u06cc \u0648\u0631\u0648\u062f \u0628\u0647 \u0641\u0636\u0627\u06cc \u0645\u062f\u06cc\u0631\u06cc\u062a MusicFinder \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f. \u062f\u0633\u062a\u0631\u0633\u06cc \u0628\u0631 \u0627\u0633\u0627\u0633 \u0646\u0642\u0634 \u062d\u0633\u0627\u0628 \u0634\u0645\u0627 \u062a\u0639\u06cc\u06cc\u0646 \u0645\u06cc\u200c\u0634\u0648\u062f.")
            : tr("Find your next favorite sound. Your music experience starts here.", "\u0635\u062f\u0627\u06cc \u0628\u0639\u062f\u06cc\u0650 \u0645\u062d\u0628\u0648\u0628\u062a \u0631\u0627 \u067e\u06cc\u062f\u0627 \u06a9\u0646\u061b \u062a\u062c\u0631\u0628\u0647\u0654 \u0645\u0648\u0633\u06cc\u0642\u06cc \u062a\u0648 \u0627\u0632 \u0627\u06cc\u0646\u062c\u0627 \u0634\u0631\u0648\u0639 \u0645\u06cc\u200c\u0634\u0648\u062f.");
        host.innerHTML = `<section class="mf-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="mfAuthTitle">
            <button class="mf-auth-close" type="button" aria-label="Close">×</button>
            <div class="mf-auth-brand"><img class="mf-auth-brand-logo" src="${brandLogo}" alt=""><span>MusicFinder</span></div>
            <div class="mf-auth-eyebrow">YOUR MUSIC SPACE</div><h2 id="mfAuthTitle">${title}</h2>
            ${profile ? `<p class="mf-auth-muted" dir="auto">${esc(user && user.email)}</p>` : `<p class="mf-auth-muted">${subtitle}</p>`}
            <div id="mfAuthMessage" class="mf-auth-message" hidden></div>
            ${profile ? `<form id="mfProfileForm"><label>Display name<input name="name" type="text" maxlength="80" required value="${esc(user && (user.name || user.user_metadata?.full_name || user.user_metadata?.name))}"></label>
                <label>Profile photo <input name="avatar" type="file" accept="image/png,image/jpeg,image/webp"></label>
                <label for="mfProfilePassword">New password</label><div class="mf-auth-password-field"><input id="mfProfilePassword" name="password" type="password" minlength="8" autocomplete="new-password" placeholder="Leave blank to keep current"><button class="mf-auth-password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show password</button></div>
                <button class="mf-auth-primary" type="submit">Save changes</button></form>
                <button class="mf-auth-secondary" id="mfAuthSignOut" type="button">Sign out</button>` : recovery ?
                `<form id="mfRecoveryForm"><label for="mfRecoveryPassword">New password</label><div class="mf-auth-password-field"><input id="mfRecoveryPassword" name="password" type="password" minlength="8" autocomplete="new-password" required><button class="mf-auth-password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show password</button></div><button class="mf-auth-primary" type="submit">Update password</button></form>` :
                forgot ?
                `<div class="mf-auth-message" role="status">Password recovery is temporarily unavailable while this feature is being updated and repaired. Please try again later.</div><button class="mf-auth-secondary" id="mfBackToLogin" type="button">Back to sign in</button>` :
                `<div class="mf-auth-tabs"><button type="button" data-mode="login" class="${!signup ? "active" : ""}">Sign in</button><button type="button" data-mode="signup" class="${signup ? "active" : ""}">Create account</button></div>
                <form id="mfAuthForm">
                <label>Email<input name="email" type="email" maxlength="254" autocomplete="email" required></label>
                <label for="mfAuthPassword">Password</label><div class="mf-auth-password-field"><input id="mfAuthPassword" name="password" type="password" minlength="8" autocomplete="${signup ? "new-password" : "current-password"}" required><button class="mf-auth-password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show password</button></div>
                <button class="mf-auth-primary" type="submit">${signup ? "Create account" : "Sign in"}</button></form>
                ${!signup ? `<button class="mf-auth-link" id="mfForgot" type="button">Forgot password?</button>` : ""}
                <div class="mf-auth-divider"><span>OR</span></div><button class="mf-auth-google" id="mfGoogle" type="button"><span class="mf-auth-google-mark" aria-hidden="true">G</span><span>Continue with Google</span></button>`}
        </section>`;
        host.querySelector(".mf-auth-dialog").setAttribute("dir", isFa() ? "rtl" : "ltr");
        host.querySelector(".mf-auth-dialog").setAttribute("lang", isFa() ? "fa" : "en");
        localizePanel(host);
        host.querySelectorAll(".mf-auth-password-toggle").forEach(toggle => {
            toggle.onclick = () => {
                const input = toggle.parentElement.querySelector("input");
                const visible = input.type === "password";
                input.type = visible ? "text" : "password";
                toggle.textContent = visible ? tr("Hide password", faCopy["Hide password"]) : tr("Show password", faCopy["Show password"]);
                toggle.setAttribute("aria-label", visible ? tr("Hide password", faCopy["Hide password"]) : tr("Show password", faCopy["Show password"]));
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
                    const result = await w.MFAuth.signUp(data.get("email"), data.get("password"));
                    if (!result.session) {
                        showMessage(tr("Your account request was received. You can now try signing in with your email and password.", "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0633\u0627\u062e\u062a \u062d\u0633\u0627\u0628 \u062b\u0628\u062a \u0634\u062f. \u0627\u06a9\u0646\u0648\u0646 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc\u062f \u0628\u0627 \u0627\u06cc\u0645\u06cc\u0644 \u0648 \u06af\u0630\u0631\u0648\u0627\u0698\u0647 \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f."), "success");
                    } else close();
                } else { await w.MFAuth.signIn(data.get("email"), data.get("password")); close(); }
            } catch (error) { showMessage(errorText(error), "error"); }
            finally { submit.disabled = false; }
        };
        const google = host.querySelector("#mfGoogle");
        if (google) {
            google.onclick = async () => {
                google.disabled = true;
                try {
                    await w.MFAuth.init();
                    if (!w.MFAuth.isGoogleEnabled()) {
                        showMessage(tr("Google sign-in is not enabled for this project yet.", "\u0648\u0631\u0648\u062f \u0628\u0627 Google \u0647\u0646\u0648\u0632 \u0628\u0631\u0627\u06cc \u0627\u06cc\u0646 \u067e\u0631\u0648\u0698\u0647 \u0641\u0639\u0627\u0644 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."), "error");
                        return;
                    }
                    await w.MFAuth.signInWithGoogle();
                } catch (error) { showMessage(errorText(error), "error"); }
                finally { google.disabled = false; }
            };
        }
        const forgotButton = host.querySelector("#mfForgot");
        if (forgotButton) forgotButton.onclick = () => { mode = "forgot"; render(); };
        const backToLogin = host.querySelector("#mfBackToLogin");
        if (backToLogin) backToLogin.onclick = () => { mode = "login"; render(); };
        const recoveryForm = host.querySelector("#mfRecoveryForm");
        if (recoveryForm) recoveryForm.onsubmit = async event => {
            event.preventDefault(); const button = recoveryForm.querySelector("button"); button.disabled = true;
            try { await w.MFAuth.updatePassword(new FormData(recoveryForm).get("password")); showMessage(tr("Password updated. You can now use it to sign in.", "\u06af\u0630\u0631\u0648\u0627\u0698\u0647 \u062a\u063a\u06cc\u06cc\u0631 \u06a9\u0631\u062f\u061b \u0627\u06a9\u0646\u0648\u0646 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc\u062f \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f."), "success"); setTimeout(close, 1200); }
            catch (error) { showMessage(errorText(error), "error"); }
            finally { button.disabled = false; }
        };
        const profileForm = host.querySelector("#mfProfileForm");
        if (profileForm) profileForm.onsubmit = async event => {
            event.preventDefault(); const button = profileForm.querySelector("button[type=submit]"); button.disabled = true;
            try {
                const data = new FormData(profileForm); const name = String(data.get("name") || "").trim();
                if (!name) throw new Error(tr("Enter your display name.", "\u0646\u0627\u0645 \u0646\u0645\u0627\u06cc\u0634\u06cc \u062e\u0648\u062f \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."));
                const updatedName = await w.MFAuth.updateName(name);
                if (user && updatedName) { user.name = name; user.user_metadata = { ...(user.user_metadata || {}), full_name: name }; }
                const photo = profileForm.elements.avatar.files[0];
                if (photo) {
                    const updatedPhoto = await w.MFAuth.uploadAvatar(photo);
                    if (user && updatedPhoto) { user.picture = updatedPhoto.user_metadata?.avatar_url || user.picture; user.user_metadata = updatedPhoto.user_metadata || user.user_metadata; }
                }
                const password = String(data.get("password") || ""); if (password) await w.MFAuth.updatePassword(password);
                showMessage(tr("Profile updated.", "\u0627\u0637\u0644\u0627\u0639\u0627\u062a \u062d\u0633\u0627\u0628 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0634\u062f."), "success");
            } catch (error) { showMessage(errorText(error), "error"); }
            finally { button.disabled = false; }
        };
        const signOut = host.querySelector("#mfAuthSignOut");
        if (signOut) signOut.onclick = async () => { signOut.disabled = true; try { await w.MFAuth.signOut(); close(); } catch (error) { showMessage(errorText(error), "error"); signOut.disabled = false; } };
        const first = host.querySelector("input") || host.querySelector(".mf-auth-close"); if (first) first.focus();
    }
    w.MFLoginPanel = Object.freeze({ open: (nextMode, nextUser) => { mode = nextMode || "login"; user = nextUser || null; render(); }, close });
    new MutationObserver(() => {
        const host = d.getElementById("mfAuthOverlay");
        if (host && !host.hidden) render();
    }).observe(d.documentElement, { attributes: true, attributeFilter: ["lang", "dir"] });
})(window, document);
