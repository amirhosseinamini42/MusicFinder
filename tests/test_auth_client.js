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
  await api.signUp("Person", "person@example.com", "password123");
  await api.signInWithGoogle();
  await api.resetPassword("person@example.com");
  await api.resendSignup("person@example.com");
  await api.updatePassword("new-password123");
  await api.updateName("New Name");
  await api.signOut();
  assert.equal(calls.filter(call => call[0] === "createClient").length, 1, "client initializes once");
  assert.equal(calls.find(call => call[0] === "signInWithPassword")[1].email, "person@example.com");
  assert.equal(calls.find(call => call[0] === "signUp")[1].options.data.full_name, "Person");
  assert.equal(calls.find(call => call[0] === "signUp")[1].options.emailRedirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/?auth=confirmed", "signup confirmation returns to the active site origin");
  assert.equal(calls.find(call => call[0] === "signInWithOAuth")[1].provider, "google");
  assert.equal(calls.find(call => call[0] === "signInWithOAuth")[1].options.redirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/admin.html", "Google sign-in returns to the page where it started");
  assert.equal(calls.find(call => call[0] === "resetPasswordForEmail")[2].redirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/?auth=recovery");
  assert.equal(calls.find(call => call[0] === "resend")[1].type, "signup");
  assert.equal(calls.find(call => call[0] === "resend")[1].options.emailRedirectTo, "https://musicfinder-web-git-feat-site-auth-system-music-finder.vercel.app/?auth=confirmed", "resend confirmation uses the active site origin");
  assert.equal(calls.find(call => call[0] === "signOut")[1].scope, "local");
  for (const file of ["index.html", "admin.html"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", "frontend", file), "utf8");
    assert.ok(html.includes('currentHost.startsWith("musicfinder-web-git-")') && html.includes('"https://musicfinder-api" + currentHost.slice("musicfinder-web".length)'), `${file} routes every Vercel Preview to its matching API`);
    assert.ok(html.includes("https://musicfinder-api.vercel.app"), `${file} retains Production API fallback`);
  }
  const home = fs.readFileSync(path.join(__dirname, "..", "frontend", "index.html"), "utf8");
  assert.ok(home.includes("function handleEmailConfirmation(session)"), "email confirmation callback is handled");
  assert.ok(home.includes('MFLoginPanel.open("profile", currentUser)'), "confirmed signup opens the existing profile setup panel");
  const callbackBlock = home.match(/let emailConfirmationUiHandled = false;[\s\S]*?function handleEmailConfirmation\(session\) \{[\s\S]*?\n\}/);
  assert.ok(callbackBlock, "confirmation callback implementation can be isolated for testing");
  let callbackContext;
  let profileOpenCount = 0;
  let openedProfile = null;
  callbackContext = vm.createContext({
    URL,
    document: { title: "MusicFinder" },
    window: {
      location: { href: "https://musicfinder-web.vercel.app/?code=pkce-code&auth=confirmed" },
      history: { replaceState: (_state, _title, url) => { callbackContext.cleanedUrl = url; } }
    },
    signInUser: user => { callbackContext.currentUser = user; },
    MFLoginPanel: { open: (mode, user) => { profileOpenCount++; openedProfile = { mode, user }; } }
  });
  vm.runInContext(callbackBlock[0], callbackContext);
  vm.runInContext("handleEmailConfirmation({ user: { id: 'confirmed-user' } }); handleEmailConfirmation({ user: { id: 'confirmed-user' } });", callbackContext);
  assert.equal(profileOpenCount, 1, "confirmation opens profile setup once");
  assert.equal(openedProfile.mode, "profile");
  assert.equal(openedProfile.user.id, "confirmed-user");
  assert.equal(callbackContext.cleanedUrl, "/?code=pkce-code", "confirmation marker is removed while preserving other callback parameters");
  const css = fs.readFileSync(path.join(__dirname, "..", "frontend", "auth.css"), "utf8");
  assert.ok(css.includes("100dvh") && css.includes("env(safe-area-inset-top)"), "auth dialog supports mobile viewport and safe areas");
  const emailTemplate = fs.readFileSync(path.join(__dirname, "..", "docs", "supabase-confirmation-email.html"), "utf8");
  assert.ok(emailTemplate.includes("{{ .ConfirmationURL }}") && emailTemplate.includes("{{ .SiteURL }}"), "branded confirmation template uses Supabase URL variables");
  console.log("AUTH CLIENT TESTS: PASS (Preview routing, signup redirect, confirmation callback, profile setup, responsive CSS, branded email template)");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
