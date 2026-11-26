const vm = require("vm"), fs = require("fs"), assert = require("assert");
const log = [];
let inserted = "";
const box = { querySelector: () => null, insertAdjacentHTML: (_, h) => { inserted = h; } };
const ctx = {
  console, API_BASE: "http://api", window: null,
  escapeHtml: s => String(s ?? "").replace(/[&<>"']/g, c => "&#" + c.charCodeAt(0) + ";"),
  document: { getElementById: () => box },
  fetch: async (url) => { log.push(url);
    if (url.includes("/tracks/search")) return { ok: true, json: async () => ({ tracks: [{ id: "mf:abc", name: "<b>X</b>", artists: [{ name: "A" }], album: { name: "", images: [] }, download_enabled: true, is_unreleased: true }] }) };
    if (url.includes("/play")) return { ok: true, json: async () => ({ url: "http://signed" }) };
    return { ok: false }; },
};
ctx.window = ctx; ctx.mfSearchSeq = 1; ctx.currentTracks = [{ id: "sp1" }];
vm.createContext(ctx);
vm.runInContext(`function renderSearchResults(d,q){ window.rendered = q; } async function getPreviewSources(s){ return ["orig:"+s.id]; }`, ctx);
vm.runInContext(fs.readFileSync("frontend/uploads-integration.js", "utf8"), ctx);
(async () => {
  assert.strictEqual(JSON.stringify(await ctx.getPreviewSources({ id: "sp1" })), JSON.stringify(["orig:sp1"]));          // Spotify path untouched
  assert.strictEqual(JSON.stringify(await ctx.getPreviewSources({ id: "mf:abc" })), JSON.stringify(["http://signed"]));   // originals use signed URL
  assert(log.some(u => u.endsWith("/tracks/abc/play")));
  ctx.renderSearchResults({}, "hello world");
  await new Promise(r => setTimeout(r, 20));
  assert.strictEqual(ctx.rendered, "hello world");                                            // original render still runs
  assert(inserted.includes("Songs on MusicFinder") && !inserted.includes("Originals") && inserted.includes("&#60;b&#62;X"));    // injected + escaped, misleading label gone
  assert(inserted.includes("Unreleased Song") && inserted.includes("mfLearnUnreleased"));   // badge + Learn more
  assert.strictEqual(ctx.currentTracks.length, 2);
  // stale search must not inject
  inserted = ""; ctx.currentTracks = [{ id: "sp1" }];
  ctx.renderSearchResults({}, "q2"); ctx.mfSearchSeq = 2;
  await new Promise(r => setTimeout(r, 20));
  assert.strictEqual(inserted, "");
  console.log("integration script: all 5 checks passed");
})().catch(e => { console.error("FAIL", e.message); process.exit(1); });
