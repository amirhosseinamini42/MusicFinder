/* Run from the repo root: node tests/test_admin_albums.js   (adjust the path below if the file sits next to index.html) */
const fs = require("fs"), vm = require("vm"), assert = require("assert");
let calls = [], store = {}, status = 200, body = { role: "admin" }, netFail = false;
const ctx = {
  API_BASE: "http://api", GOOGLE_CLIENT_ID: "cid", currentUser: { sub: "u1" },
  escapeHtml: s => String(s).replace(/[&<>"']/g, c => "&#" + c.charCodeAt(0) + ";"),
  fetch: async (u, o) => { calls.push([u, o && o.headers && o.headers.Authorization]); if (netFail) throw new Error("net"); return { ok: status === 200, json: async () => body }; },
  localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } },
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
  // admin verification
  assert.strictEqual(await T.checkAdmin("tok"), true);
  assert.deepStrictEqual(calls[0], ["http://api/admin/me", "Bearer tok"]);
  body = { role: "owner" }; assert.strictEqual(await T.checkAdmin("t"), true);
  body = { role: "viewer" }; assert.strictEqual(await T.checkAdmin("t"), false);
  status = 403; assert.strictEqual(await T.checkAdmin("t"), false);                                                  // backend says no
  status = 200; body = { role: "admin" };
  await T.onToken("tok"); assert.strictEqual(T.state().verifiedAdmin, true); assert.strictEqual(store.mfAdminHint, "u1");
  status = 403; await T.onToken("tok2"); assert.strictEqual(T.state().verifiedAdmin, false); assert.strictEqual(store.mfAdminHint, undefined);
  status = 200; netFail = true; await T.onToken("tok3"); assert.strictEqual(T.state().verifiedAdmin, false);        // network error => hidden
  netFail = false; await T.onToken("tok"); T.forgetAdmin();
  assert.strictEqual(T.state().verifiedAdmin, false); assert.strictEqual(T.state().adminToken, null); assert.strictEqual(store.mfAdminHint, undefined);
  console.log("admin/albums helper checks: all passed");
})().catch(e => { console.error("FAIL", e.message); process.exit(1); });
