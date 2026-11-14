const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function main() {
  const calls = [];
  const auth = {
    getSession: async () => ({ data: { session: { access_token: "session-token", user: { id: "user-id" } } }, error: null }),
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
    location: { origin: "https://musicfinder-web.vercel.app", pathname: "/admin.html" },
    supabase: { createClient: (...args) => { calls.push(["createClient", ...args]); return client; } }
  };
  const context = vm.createContext({
    window,
    fetch: async url => ({ ok: true, json: async () => url.endsWith("/auth/v1/settings")
      ? ({ external: ["email"] })
      : ({ url: "https://project.supabase.co", publishableKey: "public-key" }) }),
    URL: global.URL
  });
  const source = fs.readFileSync(path.join(__dirname, "..", "frontend", "auth-client.js"), "utf8");
  vm.runInContext(source, context, { filename: "auth-client.js" });
  const api = window.MFAuth;
  assert.ok(api, "MFAuth is exposed");
  await api.init();
  assert.equal(api.isGoogleEnabled(), false, "disabled Google provider is detected");
  await api.getSession();
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
  assert.equal(calls.find(call => call[0] === "signInWithOAuth")[1].provider, "google");
  assert.equal(calls.find(call => call[0] === "resetPasswordForEmail")[2].redirectTo, "https://musicfinder-web.vercel.app/?auth=recovery");
  assert.equal(calls.find(call => call[0] === "resend")[1].type, "signup");
  assert.equal(calls.find(call => call[0] === "signOut")[1].scope, "local");
  console.log("AUTH CLIENT TESTS: PASS (9 operations, singleton initialization)");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
