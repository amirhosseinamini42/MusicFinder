const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function main() {
  const calls = [];
  const fetchedUrls = [];
  const auth = {
    getSession: async () => ({ data: { session: { access_token: "session-token", user: { id: "user-id" } } }, error: null }),
    refreshSession: async () => ({ data: { session: { access_token: "refreshed-token", user: { id: "user-id" } } }, error: null }),
    signInWithPassword: async value => { calls.push(["signInWithPassword", value]); return { data: { session: {} }, error: null }; },
    signUp: async value => { calls.push(["signUp", value]); return { data: { user: {}, session: null }, error: null }; },
    signInWithOAuth: async value => { calls.push(["signInWithOAuth", value]); return { data: {}, error: null }; },
    signOut: async value => { calls.push(["signOut", value]); return { error: null }; },
    resetPasswordForEmail: async (...value) => { calls.push(["resetPasswordForEmail", ...value]); return { error: null }; },
    resend: async value => { calls.push(["resend", value]); return { error: null }; },
    verifyOtp: async value => { calls.push(["verifyOtp", value]); return { data: { session: { access_token: "confirmed-token", user: { id: "confirmed-user" } } }, error: null }; },
    updateUser: async value => { calls.push(["updateUser", value]); return { data: { user: { id: "user-id" } }, error: null }; },
    onAuthStateChange: callback => { calls.push(["onAuthStateChange", callback]); return { data: { subscription: { unsubscribe() {} } } }; }
  };
  const client = { auth, storage: { from: () => ({}) } };
  const window = {
    location: { origin: "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app", hostname: "musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app", pathname: "/admin.html" },
    supabase: { createClient: (...args) => { calls.push(["createClient", ...args]); return client; } }
  };
  const context = vm.createContext({
    window,
    fetch: async url => { fetchedUrls.push(url); return ({ ok: true, json: async () => url.endsWith("/auth/v1/settings")
      ? ({ external: { email: true, google: true } })
      : ({ url: "https://project.supabase.co", publishableKey: "public-key" }) }); },
    URL: global.URL
  });
  const source = fs.readFileSync(path.join(__dirname, "..", "frontend", "auth-client.js"), "utf8");
  vm.runInContext(source, context, { filename: "auth-client.js" });
  const api = window.MFAuth;
  assert.ok(api, "MFAuth is exposed");
  await api.init();
  assert.equal(fetchedUrls[0], "https://musicfinder-api-git-feat-site-auth-system-music-finder.vercel.app/config/supabase", "Preview uses its matching Preview API");
  assert.equal(api.isGoogleEnabled(), true, "Google provider is detected from Supabase's object-shaped provider settings");
  await api.getSession();
  await api.refreshSession();
  await api.signIn("person@example.com", "password123");
  await api.signUp("person@example.com", "password123");
  await api.signInWithGoogle();
  await api.resetPassword("person@example.com");
  await api.resendSignup("person@example.com");
  await api.verifyOtp("confirmation-hash", "email");
  await assert.rejects(api.verifyOtp("confirmation-hash", "recovery"), /confirmation_type_invalid/);
  await api.updatePassword("new-password123");
  await api.updateName("New Name");
  await api.signOut();
  assert.equal(calls.filter(call => call[0] === "createClient").length, 1, "client initializes once");
  assert.equal(calls.find(call => call[0] === "signInWithPassword")[1].email, "person@example.com");
  assert.equal(calls.find(call => call[0] === "signUp")[1].email, "person@example.com");
  assert.equal(calls.find(call => call[0] === "signUp")[1].password, "password123");
  assert.equal(calls.find(call => call[0] === "signInWithOAuth")[1].provider, "google");
  assert.equal(calls.find(call => call[0] === "signInWithOAuth")[1].options.redirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/admin.html", "Google sign-in returns to the page where it started");
  assert.equal(calls.find(call => call[0] === "resetPasswordForEmail")[2].redirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/?auth=recovery");
  assert.equal(calls.find(call => call[0] === "resend")[1].type, "signup");
  assert.equal(calls.find(call => call[0] === "resend")[1].options.emailRedirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/?auth=confirmed", "resend confirmation uses the active site origin");
  const verificationArgs = calls.find(call => call[0] === "verifyOtp")[1];
  assert.equal(verificationArgs.token_hash, "confirmation-hash", "confirmation passes the Supabase token hash");
  assert.equal(verificationArgs.type, "email", "confirmation uses the email OTP flow");
  assert.equal(calls.find(call => call[0] === "signOut")[1].scope, "local");
  for (const file of ["index.html", "admin.html"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", "frontend", file), "utf8");
    assert.ok(html.includes('currentHost.startsWith("musicfinder-web-git-")') && html.includes('"https://musicfinder-api" + currentHost.slice("musicfinder-web".length)'), `${file} routes every Vercel Preview to its matching API`);
    assert.ok(html.includes("https://musicfinder-api.vercel.app"), `${file} retains Production API fallback`);
  }
  const home = fs.readFileSync(path.join(__dirname, "..", "frontend", "index.html"), "utf8");
  assert.ok(home.includes('<span class="logoText">Music<span>Finder</span></span>'), "homepage brand text stays in one flex item without an internal gap");
  assert.ok(home.includes(".logoText span") && !home.includes(".logo span {"), "homepage brand accent styles target only the nested Finder word");
  assert.ok(home.includes("function handleEmailConfirmation(session)"), "email confirmation callback is handled");
  assert.ok(home.includes('MFLoginPanel.open("profile", currentUser)'), "confirmed signup opens the existing profile setup panel");
  const callbackBlock = home.match(/let emailConfirmationUiHandled = false;[\s\S]*?function handleEmailConfirmation\(session\) \{[\s\S]*?\n\}/);
  const initBlock = home.match(/async function initAccountAuth\(\) \{[\s\S]*?\n\}/);
  assert.ok(callbackBlock && initBlock, "auth state and confirmation callbacks can be isolated for testing");
  let callbackContext;
  let profileOpenCount = 0;
  let openedProfile = null;
  const signedInUsers = [];
  callbackContext = vm.createContext({
    URL, URLSearchParams,
    document: { title: "MusicFinder" },
    window: {
      location: { href: "https://musicfinder-web.vercel.app/", search: "" },
      history: { replaceState: (_state, _title, url) => { callbackContext.cleanedUrl = url; } }
    },
    MFAuth: {
      init: async () => {},
      onAuthStateChange: callback => { callbackContext.authStateListener = callback; },
      getSession: async () => null
    },
    signInUser: user => { signedInUsers.push(user); callbackContext.currentUser = user; },
    refreshAdminShortcut: session => { callbackContext.lastAdminSession = session || null; },
    renderAuth: () => {},
    MFLoginPanel: { open: (mode, user) => { profileOpenCount++; openedProfile = { mode, user }; } }
  });
  vm.runInContext(callbackBlock[0] + "\n" + initBlock[0], callbackContext);
  await vm.runInContext("initAccountAuth()", callbackContext);
  callbackContext.authStateListener("SIGNED_IN", { user: { id: "google-user" } });
  assert.equal(callbackContext.currentUser.id, "google-user", "ordinary Google/email sign-in updates the account UI without a confirmation query");
  assert.equal(profileOpenCount, 0, "ordinary sign-in does not open the email-confirmation profile flow");
  callbackContext.window.location.href = "https://musicfinder-web.vercel.app/?code=pkce-code&auth=confirmed";
  callbackContext.authStateListener("SIGNED_IN", { user: { id: "confirmed-user" } });
  callbackContext.authStateListener("SIGNED_IN", { user: { id: "confirmed-user" } });
  assert.equal(profileOpenCount, 1, "confirmation opens profile setup once");
  assert.equal(openedProfile.mode, "profile");
  assert.equal(openedProfile.user.id, "confirmed-user");
  assert.equal(callbackContext.cleanedUrl, "/?code=pkce-code", "confirmation marker is removed while preserving other callback parameters");
  assert.equal(signedInUsers.length, 3, "each successful auth event synchronizes the signed-in user");
  const css = fs.readFileSync(path.join(__dirname, "..", "frontend", "auth.css"), "utf8");
  assert.ok(css.includes("100dvh") && css.includes("env(safe-area-inset-top)"), "auth dialog supports mobile viewport and safe areas");
  const authUi = fs.readFileSync(path.join(__dirname, "..", "frontend", "auth-ui.js"), "utf8");
  assert.ok(authUi.includes("musicFinderLang") && authUi.includes("function localizePanel"), "shared login panel follows the saved Persian language preference");
  assert.ok(authUi.includes('setAttribute("dir", isFa() ? "rtl" : "ltr")'), "Persian login panel switches to RTL");
  assert.ok(authUi.includes('src="${brandLogo}"') && authUi.includes('const brandLogo = "/favicon.svg"'), "login panel uses the real MusicFinder logo");
  assert.ok(authUi.includes("Find your next favorite sound") && authUi.includes("Sign in to the MusicFinder admin workspace"), "homepage and admin login descriptions are separate");
  assert.ok(!authUi.includes("One account for MusicFinder and its admin panel"), "homepage login no longer advertises the admin panel");
  const adminHtml = fs.readFileSync(path.join(__dirname, "..", "frontend", "admin.html"), "utf8");
  assert.ok(adminHtml.includes("--bg:#07080d") && adminHtml.includes("rgba(110,90,255,.18)"), "admin background matches the homepage glass palette");
  assert.ok(css.includes("Cormorant Garamond") && css.includes("mf-auth-brand-logo"), "login brand uses the site typography and logo styling");
  const emailTemplate = fs.readFileSync(path.join(__dirname, "..", "docs", "supabase-confirmation-email.html"), "utf8");
  assert.ok(emailTemplate.includes("{{ .TokenHash }}") && emailTemplate.includes("{{ .SiteURL }}"), "branded confirmation template uses the PKCE token-hash flow");
  assert.ok(emailTemplate.includes("https://musicfinder-web.vercel.app/favicon-192x192.png"), "confirmation email embeds the public MusicFinder logo asset");
  assert.ok(!emailTemplate.includes("{{ .ConfirmationURL }}"), "confirmation template does not auto-consume the one-time verification URL");
  const confirmPage = fs.readFileSync(path.join(__dirname, "..", "frontend", "confirm.html"), "utf8");
  assert.ok(confirmPage.includes('meta name="referrer" content="no-referrer"'), "confirmation token is not sent as a referrer to third-party assets");
  assert.ok(confirmPage.includes('confirmButton.addEventListener("click"') && confirmPage.includes('MFAuth.verifyOtp(confirmationTokenHash, "email")'), "confirmation token is exchanged only after an explicit user click");
  const confirmScripts = [...confirmPage.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
  assert.equal(confirmScripts.length, 2, "confirmation page has a token-cleanup script and a user-action script");
  let confirmClick;
  let confirmTarget = "";
  let verifyCalls = 0;
  const confirmContext = vm.createContext({
    URL,
    document: {
      title: "Confirm your MusicFinder email",
      getElementById: id => id === "confirmEmail"
        ? { disabled: false, textContent: "Confirm email", addEventListener: (_event, callback) => { confirmClick = callback; } }
        : { textContent: "" }
    },
    window: {
      location: { href: "https://musicfinder-web.vercel.app/confirm.html?token_hash=one-time-hash&type=email", replace: target => { confirmTarget = target; } },
      history: { replaceState: (_state, _title, url) => { confirmContext.cleanedConfirmUrl = url; } },
      MFAuth: {
        init: async () => {},
        verifyOtp: async (tokenHash, type) => {
          verifyCalls++;
          assert.equal(tokenHash, "one-time-hash");
          assert.equal(type, "email");
          return { session: { access_token: "test-session" } };
        }
      }
    },
    console: { error() {} }
  });
  vm.runInContext(confirmScripts[0], confirmContext);
  vm.runInContext(confirmScripts[1], confirmContext);
  assert.equal(confirmContext.cleanedConfirmUrl, "/confirm.html", "one-time token is removed from browser history before third-party scripts load");
  assert.equal(verifyCalls, 0, "opening the confirmation page alone does not consume the token");
  await confirmClick();
  assert.equal(verifyCalls, 1, "explicit confirmation click verifies the token once");
  assert.equal(confirmTarget, "/?auth=confirmed", "successful verification returns to the homepage confirmation handler");
  console.log("AUTH CLIENT TESTS: PASS (Preview routing, PKCE token verification, click-to-confirm flow, profile setup, header spacing, responsive CSS, branded email template)");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
