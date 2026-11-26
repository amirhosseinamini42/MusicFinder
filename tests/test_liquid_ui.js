const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const home = fs.readFileSync("frontend/index.html", "utf8");
const admin = fs.readFileSync("frontend/admin.html", "utf8");
const authCss = fs.readFileSync("frontend/auth.css", "utf8");
const confirm = fs.readFileSync("frontend/confirm.html", "utf8");

for (const [name, html] of [["home", home], ["admin", admin]]) {
    assert.match(html, /data-barba="wrapper"/, `${name} has a Barba wrapper`);
    assert.match(html, /data-barba="container"/, `${name} has a Barba container`);
    assert.match(html, /lenis@1\.3\.11/, `${name} loads pinned Lenis`);
    assert.match(html, /@barba\/core@2\.10\.3/, `${name} loads pinned Barba`);
    assert.match(html, /new Lenis\(/, `${name} initializes Lenis`);
    assert.match(html, /barba\.init\(/, `${name} initializes Barba`);
    const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
    for (let i = 0; i < scripts.length; i++) {
        if (/\bsrc\s*=/.test(scripts[i][1])) continue;
        new vm.Script(scripts[i][2], { filename: `${name}-inline-${i}.js` });
    }
}

assert.match(home, /id="adminShortcut"[^>]*href="\/adminpanel"[^>]*hidden[^>]*><svg/);
assert.doesNotMatch(home, /id="adminShortcut"[\s\S]{0,500}>[\s\S]*?Admin Panel<\/a>/);
assert.match(home, /refreshAdminShortcut\(session\)/);
assert.match(home, /\["admin", "owner"\]\.includes\(admin\.role\)/);
assert.match(admin, /href="\/"[^>]*aria-label="Back to MusicFinder website"/);
assert.match(home, /class="playerFullContent" id="fullPlayer"/);
assert.doesNotMatch(home, /<div class="fullPlayer" id="fullPlayer">/);
assert.match(home, /musicPlayer\.classList\.add\("mode-full", "active"\)/);
assert.match(home, /id="playerClose"/);
assert.match(home, /musicPlayer\.minimized/);
assert.match(home, /id="mf-player-layout"/);
assert.match(home, /setPlayerMinimized\(false, false\)/);
assert.match(home, /\.mfMail\s*\{[^}]*color:\s*#e6b06a/i, "About email uses the site's warm button accent, not blue");
assert.match(home, /\.musicPlayer\.minimized \.playerControls\s*\{\s*display:flex !important/i, "mini player keeps playback controls visible");
assert.match(home, /\.musicPlayer\.minimized \.playerControls #playerPrevious\s*\{\s*display:none/i, "mini player keeps the compact play and next controls");
assert.match(home, /\.musicPlayer\.minimized \.playerControls #playerStop\s*\{\s*display:flex/i, "mini player exposes a dedicated stop control");
assert.match(home, /\.musicPlayer\.minimized \.playerMinBtn svg\s*\{\s*transform:rotate\(180deg\)/i, "expand chevron points upward while minimized");
assert.match(home, /id="playerNext"[\s\S]{0,120}aria-label="Next track"/);
assert.match(home, /id="playerPlay"[\s\S]{0,120}aria-label="Play"/);
assert.match(home, /playerStop\.addEventListener\("click",\s*\(\)\s*=>\s*\{[\s\S]*?musicAudio\.pause\(\)[\s\S]*?musicAudio\.currentTime\s*=\s*0/);
const pageShellStyle = home.match(/#pageShell\s*\{([^}]*)\}/);
assert.ok(pageShellStyle, "Barba page shell layout rule exists");
assert.doesNotMatch(pageShellStyle[1], /\btransform\s*:/, "page shell must not establish a fixed-position containing block");
assert.doesNotMatch(home, /html\.barba-leaving\s+#pageShell\s*\{[^}]*\btransform\s*:/,
    "Barba leave transition must not transform the fixed-UI ancestor");
const pageEnterAnimation = home.match(/@keyframes\s+mfPageEnter\s*\{([\s\S]*?)\n\s*\}/);
assert.ok(pageEnterAnimation, "page enter animation exists");
assert.doesNotMatch(pageEnterAnimation[1], /\btransform\s*:/,
    "page enter animation must not transform the fixed-UI ancestor");
assert.match(home, /function safeInitialRender\(name, render\)/);
assert.match(home, /safeInitialRender\("For You", renderForYou\)/);
assert.match(home, /could not save local taste data/);
assert.match(home, /try \{ registerTrackClick\(track\); \}/);
assert.match(home, /AUTUMN .* RAINY-EVENING ATMOSPHERE/);
assert.match(home, /#rainCanvas/);
assert.doesNotMatch(home, /mf-liquid-glass-final|#080b13|rgba\(92,120,255/);
assert.match(home, /--bg: #110b08/);
assert.match(admin, /class="mf-review-player"/);
assert.doesNotMatch(admin, /mf-liquid-glass-final|--bg:#080b13|rgba\(92,120,255/);
assert.match(admin, /--bg:#110b08/);
assert.match(admin, /rgba\(224,164,90/);
assert.match(admin, /--glass:rgba\(255,226,190,\.07\)/);
assert.match(admin, /--dynamic-color:rgba\(135,165,255,\.26\)/);
assert.match(admin, /MusicFinder<\/span><span class="adminPanelLabel">· adminpanel/);
assert.match(admin, /function adminUrl\(\) \{ return tab === "dashboard" \? "\/adminpanel" : "\/adminpanel\/"/);
assert.doesNotMatch(admin, /"#"\s*\+\s*tab/, "Admin routes must not use hash navigation");
assert.match(admin, /id="eAf"/);
assert.match(admin, /body: \{ audio: true, cover: false \}/);
assert.match(admin, /Unpublish this track before replacing its audio/);
assert.match(admin, /id="rvSeek"/);
assert.doesNotMatch(admin, /<audio controls/);
assert.match(admin, /audio\.pause\(\); audio\.removeAttribute\("src"\)/);
assert.match(admin, /audioUploaded: false, coverUploaded: false/);
assert.match(admin, /Promise\.allSettled\(tasks\)/);
assert.match(admin, /x\.timeout = 180000/);
assert.match(admin, /uploadWithRetry\("audio"/);
assert.match(admin, /async function optimizeCoverFile\(file\)/);
assert.match(admin, /createImageBitmap\(file\)/);
assert.match(admin, /image\/webp/);
assert.match(admin, /Audio is uploaded\s+\/\/ byte-for-byte/);
assert.match(authCss, /rgba\(135,165,255/);
assert.match(authCss, /linear-gradient\(110deg,rgba\(214,138,58/);
assert.match(authCss, /\.mf-auth-dialog\[dir="rtl"\] \.mf-auth-brand\{direction:rtl/);
assert.doesNotMatch(authCss, /rgba\(110,90,255|rgba\(0,180,255|rgba\(255,0,100/);
assert.match(authCss, /linear-gradient\(155deg,rgba\(24,14,9/);
assert.match(admin, /--text:#f4e8d4/);
assert.match(admin, /--border:rgba\(255,220,180,\.14\)/);
assert.match(home, /data-mode="lyrics" aria-pressed="false" disabled aria-disabled="true"/);
assert.match(home, /Search by lyrics · temporarily disabled/);
assert.match(home, /#searchSection \*, #searchResults, #searchResults \*/);
assert.match(home, /user-select:text/);
assert.match(home, /"Temporarily disabled": "موقتاً غیرفعال"/);
assert.match(home, /"Search by lyrics · temporarily disabled": "جستجو با متن آهنگ · موقتاً غیرفعال"/);
assert.match(home, /name="theme-color" content="#110b08"/);
const routes = JSON.parse(require("node:fs").readFileSync("frontend/vercel.json", "utf8"));
assert.deepEqual(routes.rewrites.map(x => [x.source, x.destination]), [
    ["/adminpanel", "/admin.html"], ["/adminpanel/:path*", "/admin.html"]
]);
assert.doesNotMatch(authCss, /Unified neutral Liquid Glass account UI|rgba\(150,175,255/);
assert.match(confirm, /name="theme-color" content="#110b08"/);
assert.match(confirm, /rgba\(236,148,56/);
assert.doesNotMatch(confirm, /#080b13|rgba\(115,145,255/);

// Exercise the actual upload transport/retry helper from the admin page.
const helperStart = admin.indexOf("function putFile(");
const helperEnd = admin.indexOf("const bar =", helperStart);
assert.ok(helperStart >= 0 && helperEnd > helperStart, "upload helper block exists");
const helperSource = admin.slice(helperStart, helperEnd) + "\nglobalThis.testUploadWithRetry = uploadWithRetry;";

async function runTransport(statuses, targetTrackId = "track-1", isStopped = false) {
    let refreshes = 0;
    class FakeXHR {
        constructor() { this.upload = {}; this.status = 0; }
        open() {}
        setRequestHeader() {}
        send() { this.status = statuses.shift(); this.onload(); }
        abort() { if (this.onabort) this.onabort(); }
    }
    const context = {
        XMLHttpRequest: FakeXHR,
        liveXhrs: new Set(),
        pending: { trackId: "track-1" },
        stopped: isStopped,
        setTimeout: callback => { callback(); return 0; },
        decl: file => ({ filename: file.name, size: file.size, content_type: file.type }),
        api: async (path, options) => {
            refreshes++;
            assert.equal(path, `/admin/tracks/${targetTrackId}/upload-urls`);
            assert.equal(options.body.audio.filename, "demo.mp3");
            return { uploads: { audio: { url: "fresh-signed-url", content_type: "audio/mpeg" } } };
        }
    };
    vm.createContext(context);
    vm.runInContext(helperSource, context);
    const progress = [];
    const file = { name: "demo.mp3", size: 1024, type: "audio/mpeg" };
    let error = null;
    try { await context.testUploadWithRetry("audio", file, { url: "expired-url", content_type: "audio/mpeg" }, value => progress.push(value), targetTrackId, !isStopped); }
    catch (caught) { error = caught; }
    return { refreshes, progress, error };
}

(async () => {
    // Browser storage from older builds can be malformed or unavailable. It must
    // not break Details, player boot, or the search UI.
    const tasteSource = home.match(/function getTasteData\(\) \{[\s\S]*?\n\}/);
    assert.ok(tasteSource, "taste storage reader exists");
    const storageContext = vm.createContext({
        TASTE_KEY: "taste",
        localStorage: { getItem: () => JSON.stringify({ searches: "bad", artists: null, tracks: [] }) },
        console: { warn() {} }
    });
    vm.runInContext(tasteSource[0] + "\nglobalThis.readTaste = getTasteData;", storageContext);
    const normalized = storageContext.readTaste();
    assert.equal(Array.isArray(normalized.searches), true);
    assert.equal(typeof normalized.artists, "object");
    assert.equal(Array.isArray(normalized.tracks), false);
    storageContext.localStorage.getItem = () => { throw new Error("storage blocked"); };
    const unavailable = storageContext.readTaste();
    assert.deepEqual(JSON.parse(JSON.stringify(unavailable)), { searches: [], artists: {}, tracks: {} });

    // Large cover images are resized and converted to WebP before upload; audio is untouched.
    const optimizeSource = admin.match(/async function optimizeCoverFile\(file\) \{[\s\S]*?\n\}/);
    assert.ok(optimizeSource, "cover optimizer exists");
    let drawnSize = null;
    const optimizeContext = vm.createContext({
        createImageBitmap: async () => ({ width: 3000, height: 2000, close() {} }),
        File,
        Blob,
        document: { createElement: () => ({
            getContext: () => ({ drawImage: (_bitmap, _x, _y, width, height) => { drawnSize = [width, height]; } }),
            toBlob: callback => callback(new Blob([new Uint8Array(120)], { type: "image/webp" }))
        }) },
        console: { warn() {} }
    });
    vm.runInContext(optimizeSource[0] + "\nglobalThis.optimize = optimizeCoverFile;", optimizeContext);
    const optimizedCover = await optimizeContext.optimize({ name: "cover.png", size: 900000, type: "image/png", lastModified: 1 });
    assert.equal(optimizedCover.name, "cover.webp");
    assert.equal(optimizedCover.type, "image/webp");
    assert.deepEqual(drawnSize, [1800, 1200]);

    const recovered = await runTransport([503, 200]);
    assert.equal(recovered.refreshes, 1, "transient storage failures renew the signed URL");
    const replacementRecovered = await runTransport([503, 200], "existing-track", true);
    assert.equal(replacementRecovered.refreshes, 1, "audio replacement retries against its own track and ignores a previous canceled upload state");
    const rejected = await runTransport([413]);
    assert.equal(rejected.refreshes, 0, "permanent size errors are not retried");
    assert.equal(rejected.error && rejected.error.message, "upload_http_413");

    const shortcutBlock = home.match(/let adminShortcutRequest = 0;[\s\S]*?async function refreshAdminShortcut\(session\) \{[\s\S]*?\n\}/);
    assert.ok(shortcutBlock, "server-verified admin shortcut logic exists");
    let role = "admin";
    const link = { hidden: true };
    const shortcutContext = vm.createContext({
        API_BASE: "https://api.example",
        document: { getElementById: () => link },
        fetch: async (url, options) => {
            assert.equal(url, "https://api.example/admin/me");
            assert.equal(options.headers.Authorization, "Bearer session-token");
            return { ok: true, json: async () => ({ role }) };
        },
        console: { debug() {} }
    });
    vm.runInContext(shortcutBlock[0] + "\nglobalThis.checkAdminShortcut = refreshAdminShortcut;", shortcutContext);
    await shortcutContext.checkAdminShortcut({ access_token: "session-token" });
    assert.equal(link.hidden, false, "admin receives the shortcut after server verification");
    role = "owner";
    await shortcutContext.checkAdminShortcut({ access_token: "session-token" });
    assert.equal(link.hidden, false, "owner receives the shortcut after server verification");
    role = "user";
    await shortcutContext.checkAdminShortcut({ access_token: "session-token" });
    assert.equal(link.hidden, true, "ordinary users do not receive the shortcut");
    console.log("liquid UI + upload regression checks: PASS");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
