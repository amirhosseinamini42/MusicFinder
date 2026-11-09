/* Run from the repo root: node tests/test_admin_albums.js */
const fs = require("fs"), vm = require("vm"), assert = require("assert");
let calls = [], store = {}, sess = {}, status = 200, body = { role: "admin" }, netFail = false;
let scripted = null;                                 // per-call mock queue: [status, body] | "net"
const ctx = {
  API_BASE: "http://api", GOOGLE_CLIENT_ID: "cid", currentUser: { sub: "u1" },
  escapeHtml: s => String(s).replace(/[&<>"']/g, c => "&#" + c.charCodeAt(0) + ";"),
  fetch: async (u, o) => {
    calls.push([u, o && o.headers && o.headers.Authorization]);
    const next = scripted && scripted.length ? scripted.shift() : [status, body];
    if (next === "net") throw new Error("net");
    return { ok: next[0] === 200, status: next[0], json: async () => next[1] };
  },
  localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } },
  sessionStorage: { getItem: k => sess[k] ?? null, setItem: (k, v) => { sess[k] = v; }, removeItem: k => { delete sess[k]; } },
  setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},   // vm has no timers; schedule() must not crash
  console
};
ctx.window = ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync("frontend/mf-admin-albums.js", "utf8"), ctx);
const T = ctx.__mfAdminAlbums;
(async () => {
  // album links
  assert.strictEqual(T.albumLinkHtml({ album: { id: "4aawyAB9vmqN3uQ7FjRGTy", name: "Abbey <Road>" } }).includes("data-mf-album=\"4aawyAB9vmqN3uQ7FjRGTy\""), true);
  assert(T.albumLinkHtml({ album: { id: "4aawyAB9vmqN3uQ7FjRGTy", name: "A<b>" } }).includes("&#60;b&#62;"));        // escaped
  assert.strictEqual(T.albumLinkHtml({ album: { name: "No id" } }), null);                                          // never invent an album
  assert.strictEqual(T.albumLinkHtml({ album: { id: "x'\"><script>", name: "Bad" } }), null);                       // unsafe id rejected
  assert.strictEqual(T.albumLinkHtml({}), null);
  // admin verification: checkAdmin returns "admin" | "denied" | "expired" | "unknown"; isAdminResult maps it to a boolean
  assert.strictEqual(await T.checkAdmin("tok"), "admin");                                                            // backend says yes
  assert.deepStrictEqual(calls[0], ["http://api/admin/me", "Bearer tok"]);                                           // correct URL + bearer header
  assert.strictEqual(T.isAdminResult("admin"), true);
  scripted = [[200, { role: "owner" }]];   assert.strictEqual(await T.checkAdmin("t"), "admin");                     // owner counts as admin
  scripted = [[200, { role: "viewer" }]];  assert.strictEqual(await T.checkAdmin("t"), "denied");                    // unknown role => denied
  scripted = [[403, {}]];                  assert.strictEqual(await T.checkAdmin("t"), "denied");                    // backend says no
  scripted = [[500, {}]];                  assert.strictEqual(await T.checkAdmin("t"), "unknown");                   // server error => keep current state
  scripted = [[401, {}]];                  assert.strictEqual(await T.checkAdmin("t"), "expired");                   // expired session
  scripted = ["net"];                      assert.strictEqual(await T.checkAdmin("t"), "unknown");                   // network error => keep current state
  scripted = null;
  status = 200; body = { role: "admin" };
  await T.onToken("tok"); assert.strictEqual(T.state().verifiedAdmin, true); assert.strictEqual(store.mfAdminHint, "u1");
  assert.strictEqual(sess.mfAdminTok, "tok");                                                            // token kept tab-scoped for admin.html
  scripted = [[403, {}]]; await T.onToken("tok2");                        // backend says no => forget everything
  assert.strictEqual(T.state().verifiedAdmin, false); assert.strictEqual(store.mfAdminHint, undefined); assert.strictEqual(sess.mfAdminTok, undefined);
  scripted = ["net"]; netFail = true; await T.onToken("tok3");             // network error => icon stays hidden, nothing verified
  assert.strictEqual(T.state().verifiedAdmin, false);
  netFail = false; scripted = null; await T.onToken("tok"); T.forgetAdmin();
  assert.strictEqual(T.state().verifiedAdmin, false); assert.strictEqual(T.state().adminToken, null); assert.strictEqual(store.mfAdminHint, undefined);
  console.log("admin/albums helper checks: all passed");
})().catch(e => { console.error("FAIL", e.message); process.exit(1); });
