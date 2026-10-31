/* MusicFinder: (1) Admin Panel shortcut, (2) clickable album names that open the in-site album view.
   Additive: load AFTER all inline scripts and uploads-integration.js. It wraps a few existing globals and edits no other code.
   Relies on existing globals: API_BASE, GOOGLE_CLIENT_ID, currentUser, googleInitDone, currentModalTrack, escapeHtml,
   decodeJwtPayload, handleGoogleCredential, signOutUser, openTrackFromEncoded, openAlbum (album modal + tracklist + shared player). */
(function () {
    "use strict";
    const HINT_KEY = "mfAdminHint";            /* only decides whether to try a silent re-check; it NEVER shows the icon */
    let adminToken = null;                      /* Google ID token, kept in memory only */
    let verifiedAdmin = false;

    /* ---------- albums ---------- */
    function albumRef(track) {
        const a = track && track.album;
        if (!a || !a.name || typeof a.id !== "string" || !/^[A-Za-z0-9]{1,40}$/.test(a.id)) return null;
        return { id: a.id, name: a.name };
    }
    function albumLinkHtml(track) {
        const r = albumRef(track);
        return r ? `<span class="mfAlbumLink" role="link" tabindex="0" data-mf-album="${escapeHtml(r.id)}">${escapeHtml(r.name)}</span>` : null;
    }

    /* ---------- admin check (the backend decides; the icon is only a shortcut) ---------- */
    const TOKEN_KEY = "mfAdminTok";             /* tab-scoped (sessionStorage); cleared on sign-out / denial; shared with admin.html */
    const RECHECK_MS = 120000, MIN_GAP_MS = 30000;
    let gen = 0, recheckTimer = null, refreshTimer = null, silentTimer = null, lastCheck = 0, silent = false;

    /* "admin" | "denied" (403) | "expired" (401) | "unknown" (network / 5xx: keep the current state) */
    async function checkAdmin(token) {
        let r;
        try { r = await fetch(`${API_BASE}/admin/me`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" }); }
        catch (e) { return "unknown"; }
        if (r.status === 401) return "expired";
        if (r.status === 403) return "denied";
        if (!r.ok) return "unknown";
        try { const d = await r.json(); return d && (d.role === "owner" || d.role === "admin") ? "admin" : "denied"; }
        catch (e) { return "unknown"; }
    }
    function tokenPayload(t) { try { return decodeJwtPayload(t) || {}; } catch (e) { return {}; } }
    const tokenExp = t => (tokenPayload(t).exp || 0) * 1000;
    const tokenSub = t => tokenPayload(t).sub || null;
    const signedInSub = () => (typeof currentUser !== "undefined" && currentUser && currentUser.sub) || null;

    function setAdminVisible(on) {
        if (typeof document === "undefined") return;
        const a = document.getElementById("mfAdminLink");
        if (a) a.hidden = !on;
    }
    function stopSilent() { silent = false; clearTimeout(silentTimer); }
    function hideOnly() { verifiedAdmin = false; setAdminVisible(false); }      /* session may still be refreshable */
    function forgetAdmin() {                                                   /* sign-out / revoked / switched account */
        gen++; clearInterval(recheckTimer); clearTimeout(refreshTimer); recheckTimer = refreshTimer = null; stopSilent();
        adminToken = null; hideOnly();
        try { sessionStorage.removeItem(TOKEN_KEY); localStorage.removeItem(HINT_KEY); } catch (e) {}
    }
    function schedule(token) {
        if (!recheckTimer) recheckTimer = setInterval(recheck, RECHECK_MS);
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(requestFresh, Math.max(tokenExp(token) - Date.now() - 300000, 5000));
    }
    async function verify(token, g) {
        const res = await checkAdmin(token);
        if (g !== gen) return;                                                 /* a newer sign-in / sign-out won the race */
        lastCheck = Date.now();
        if (res === "admin") {
            verifiedAdmin = true; setAdminVisible(true); schedule(token);
            try { if (signedInSub()) localStorage.setItem(HINT_KEY, signedInSub()); } catch (e) {}
        } else if (res === "denied") forgetAdmin();                            /* not (or no longer) an admin */
        else if (res === "expired") { hideOnly(); requestFresh(); }
    }
    function onToken(token) {
        if (!token) return Promise.resolve();
        const g = ++gen; adminToken = token;
        try { sessionStorage.setItem(TOKEN_KEY, token); } catch (e) {}
        return verify(token, g);
    }
    function recheck() {
        if (!adminToken || (typeof document !== "undefined" && document.hidden)) return Promise.resolve();
        if (tokenExp(adminToken) <= Date.now() + 15000) { hideOnly(); requestFresh(); return Promise.resolve(); }
        return verify(adminToken, ++gen);
    }
    /* Ask Google for a fresh ID token for the SAME account (One Tap auto-select). Visible state stays backend-verified. */
    function requestFresh() {
        if (silent || !signedInSub() || !(window.google && google.accounts && google.accounts.id)) return;
        try {
            silent = true; silentTimer = setTimeout(stopSilent, 10000);
            google.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID, callback: mainCb(), auto_select: true });
            google.accounts.id.prompt();
        } catch (e) { stopSilent(); }
    }
    function restore() {                                                       /* page load / refresh / coming back from admin.html */
        let t = null;
        try { t = sessionStorage.getItem(TOKEN_KEY); } catch (e) {}
        if (t && signedInSub() && tokenSub(t) === signedInSub() && tokenExp(t) > Date.now() + 15000) { onToken(t); return true; }
        if (t) { try { sessionStorage.removeItem(TOKEN_KEY); } catch (e) {} }
        return false;
    }
    function silentRecheck() {
        try { if (signedInSub() && localStorage.getItem(HINT_KEY) === signedInSub()) requestFresh(); } catch (e) {}
    }
    function mainCb() { return typeof handleGoogleCredential === "function" ? handleGoogleCredential : () => {}; }

    window.__mfAdminAlbums = { albumRef, albumLinkHtml, checkAdmin, onToken, forgetAdmin, recheck, restore, state: () => ({ verifiedAdmin, adminToken }) };
    if (typeof document === "undefined" || !document.getElementById) return;      /* DOM part below runs in the browser only */

    /* ---------- styles + icon ---------- */
    const st = document.createElement("style");
    st.textContent = `
.mfAdminBtn { display:inline-flex; align-items:center; justify-content:center; }
.mfAdminBtn[hidden] { display:none; }
.mfAlbumLink { cursor:pointer; background-image:linear-gradient(currentColor,currentColor); background-repeat:no-repeat;
    background-size:0 1px; background-position:0 100%; padding-bottom:1px; transition:background-size .25s ease; }
html[dir="rtl"] .mfAlbumLink { background-position:100% 100%; }
.mfAlbumLink:hover, .mfAlbumLink:focus-visible { background-size:100% 1px; outline:none; }
.mfAlbumLink:focus-visible { outline:2px solid rgba(224,164,90,.8); outline-offset:2px; border-radius:3px; }`;
    document.head.appendChild(st);
    if (window.MF_FA) window.MF_FA["Admin Panel"] = "پنل مدیریت";

    function ensureIcon() {
        if (document.getElementById("mfAdminLink")) return;
        const nav = document.querySelector(".navRight");
        if (!nav) return;
        const a = document.createElement("a");
        a.id = "mfAdminLink"; a.className = "navButton mfAdminBtn"; a.href = "admin.html"; a.hidden = true;
        a.title = "Admin Panel"; a.setAttribute("aria-label", "Admin Panel");
        a.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/></svg>';
        nav.insertBefore(a, nav.querySelector(".menuButton"));
    }
    ensureIcon();

    /* ---------- get the Google ID token when the user signs in (the site itself discards it) ---------- */
    function wrapCallback(cb) {
        return function (resp) {
            const token = resp && resp.credential;
            if (token && silent && signedInSub() && tokenSub(token) === signedInSub()) {   /* silent refresh: same account only */
                stopSilent(); onToken(token); return;
            }
            stopSilent();
            if (token) onToken(token);
            return cb.apply(this, arguments);
        };
    }
    function hookGoogle() {
        const gid = window.google && google.accounts && google.accounts.id;
        if (!gid) return false;
        if (gid.__mfHooked) return true;
        try {
            const orig = gid.initialize.bind(gid);
            gid.initialize = function (opts) {
                return orig(opts && typeof opts.callback === "function" ? Object.assign({}, opts, { callback: wrapCallback(opts.callback) }) : opts);
            };
            gid.__mfHooked = true;
        } catch (e) { return true; }                         /* cannot hook: fail closed (icon stays hidden), sign-in itself is untouched */
        if (typeof googleInitDone !== "undefined" && googleInitDone) {      /* site initialized before we hooked: re-initialize identically */
            gid.initialize({ client_id: GOOGLE_CLIENT_ID, callback: mainCb() });
        }
        return true;
    }
    const restored = restore();                              /* no Google round-trip needed when this tab already has a token */
    (function waitForGoogle(n) {
        if (hookGoogle()) { if (!restored) silentRecheck(); return; }
        if (n < 40) setTimeout(() => waitForGoogle(n + 1), 250);
    })(0);
    document.addEventListener("visibilitychange", () => { if (!document.hidden && adminToken && Date.now() - lastCheck > MIN_GAP_MS) recheck(); });
    window.addEventListener("pageshow", e => { if (e.persisted && adminToken) recheck(); });
    window.addEventListener("storage", e => { if (e.key === "musicFinderUser" && !e.newValue) forgetAdmin(); });   /* sign-out in another tab */

    if (typeof signOutUser === "function") {
        const so = window.signOutUser;
        window.signOutUser = function () { forgetAdmin(); return so.apply(this, arguments); };
    }

    /* ---------- album names -> in-site album view (existing openAlbum modal + shared player) ---------- */
    if (typeof openTrackFromEncoded === "function") {
        const origOpen = window.openTrackFromEncoded;
        window.openTrackFromEncoded = function () {
            const out = origOpen.apply(this, arguments);
            try {
                const p = document.querySelectorAll("#modalBody .modalHero > div > p.modalMuted")[1];   /* [artist, album] */
                const html = typeof currentModalTrack !== "undefined" && albumLinkHtml(currentModalTrack);
                if (p && html) p.innerHTML = html;
            } catch (e) {}
            return out;
        };
    }
    function linkCards() {
        document.querySelectorAll("#searchResults .resultCard").forEach(card => {
            if (card.dataset.mfAlbumDone) return;
            card.dataset.mfAlbumDone = "1";
            const btn = card.querySelector('[onclick*="currentTracks.find"]');
            const m = btn && (btn.getAttribute("onclick") || "").match(/t\.id === '([^']+)'/);
            const track = m && (window.currentTracks || []).find(t => t.id === m[1]);
            const html = track && albumLinkHtml(track);
            const meta = card.querySelector(".cardMeta");
            if (html && meta) meta.innerHTML = html;
        });
    }
    const box = document.getElementById("searchResults");
    if (box) new MutationObserver(linkCards).observe(box, { childList: true, subtree: true });
    linkCards();

    function openFrom(e) {
        const el = e.target.closest && e.target.closest("[data-mf-album]");
        if (!el) return false;
        e.preventDefault(); e.stopPropagation();
        openAlbum(el.dataset.mfAlbum);
        return true;
    }
    document.addEventListener("click", openFrom, true);
    document.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") openFrom(e); }, true);
})();