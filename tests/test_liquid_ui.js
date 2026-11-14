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

assert.match(home, /id="adminShortcut"[^>]*href="\/admin\.html"[^>]*hidden[^>]*><svg/);
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
assert.match(home, /AUTUMN .* RAINY-EVENING ATMOSPHERE/);
assert.match(home, /#rainCanvas/);
assert.doesNotMatch(home, /mf-liquid-glass-final|#080b13|rgba\(92,120,255/);
assert.match(home, /--bg: #110b08/);
assert.match(admin, /class="mf-review-player"/);
assert.doesNotMatch(admin, /mf-liquid-glass-final|--bg:#080b13|rgba\(92,120,255/);
assert.match(admin, /--bg:#110b08/);
assert.match(admin, /rgba\(224,164,90/);
assert.match(admin, /id="rvSeek"/);
assert.doesNotMatch(admin, /<audio controls/);
assert.match(admin, /audio\.pause\(\); audio\.removeAttribute\("src"\)/);
assert.match(admin, /audioUploaded: false, coverUploaded: false/);
assert.match(admin, /Promise\.allSettled\(tasks\)/);
assert.match(admin, /x\.timeout = 180000/);
assert.match(admin, /uploadWithRetry\("audio"/);
assert.match(authCss, /rgba\(255,220,180/);
assert.match(authCss, /linear-gradient\(110deg,rgba\(214,138,58/);
assert.doesNotMatch(authCss, /Unified neutral Liquid Glass account UI|rgba\(150,175,255/);
assert.match(confirm, /name="theme-color" content="#110b08"/);
assert.match(confirm, /rgba\(236,148,56/);
assert.doesNotMatch(confirm, /#080b13|rgba\(115,145,255/);

// Exercise the actual upload transport/retry helper from the admin page.
const helperStart = admin.indexOf("function putFile(");
const helperEnd = admin.indexOf("const bar =", helperStart);
assert.ok(helperStart >= 0 && helperEnd > helperStart, "upload helper block exists");
const helperSource = admin.slice(helperStart, helperEnd) + "\nglobalThis.testUploadWithRetry = uploadWithRetry;";

async function runTransport(statuses) {
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
        stopped: false,
        setTimeout: callback => { callback(); return 0; },
        decl: file => ({ filename: file.name, size: file.size, content_type: file.type }),
        api: async (path, options) => {
            refreshes++;
            assert.equal(path, "/admin/tracks/track-1/upload-urls");
            assert.equal(options.body.audio.filename, "demo.mp3");
            return { uploads: { audio: { url: "fresh-signed-url", content_type: "audio/mpeg" } } };
        }
    };
    vm.createContext(context);
    vm.runInContext(helperSource, context);
    const progress = [];
    const file = { name: "demo.mp3", size: 1024, type: "audio/mpeg" };
    let error = null;
    try { await context.testUploadWithRetry("audio", file, { url: "expired-url", content_type: "audio/mpeg" }, value => progress.push(value)); }
    catch (caught) { error = caught; }
    return { refreshes, progress, error };
}

(async () => {
    const recovered = await runTransport([503, 200]);
    assert.equal(recovered.refreshes, 1, "transient storage failures renew the signed URL");
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
