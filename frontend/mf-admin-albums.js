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
    async function checkAdmin(token) {
        const r = await fetch(`${API_BASE}/admin/me`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" });
        if (!r.ok) return false;
        const d = await r.json();
        return !!d && (d.role === "owner" || d.role === "admin");
    }
    function setAdminVisible(on) {
        if (typeof document === "undefined") return;
        const a = document.getElementById("mfAdminLink");
        if (a) a.hidden = !on;
    }
    async function onToken(token) {
        adminToken = token;
        try { verifiedAdmin = await checkAdmin(token); } catch (e) { verifiedAdmin = false; }
        setAdminVisible(verifiedAdmin);
        try {
            if (verifiedAdmin && typeof currentUser !== "undefined" && currentUser && currentUser.sub) localStorage.setItem(HINT_KEY, currentUser.sub);
            else localStorage.removeItem(HINT_KEY);
        } catch (e) {}
    }
    function forgetAdmin() {
        adminToken = null; verifiedAdmin = false; setAdminVisible(false);
        try { localStorage.removeItem(HINT_KEY); } catch (e) {}
    }

    window.__mfAdminAlbums = { albumRef, albumLinkHtml, checkAdmin, onToken, forgetAdmin, state: () => ({ verifiedAdmin, adminToken }) };
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
    let silent = false;
    function mainCb() { return typeof handleGoogleCredential === "function" ? handleGoogleCredential : () => {}; }
    function wrapCallback(cb) {
        return function (resp) {
            const token = resp && resp.credential;
            if (silent) {                                    /* silent re-check: only accept the SAME account, never switch users */
                silent = false;
                try { if (token && currentUser && decodeJwtPayload(token).sub === currentUser.sub) onToken(token); } catch (e) {}
                return;
            }
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
    function silentRecheck() {
        /* After a reload there is no token. If this account was verified as admin before, ask Google for a fresh one
           (same account only). The icon still appears ONLY after the backend confirms. Untested against real Google. */
        try {
            if (typeof currentUser === "undefined" || !currentUser || !currentUser.sub) return;
            if (localStorage.getItem(HINT_KEY) !== currentUser.sub) return;
            silent = true;
            google.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID, callback: mainCb(), auto_select: true });
            google.accounts.id.prompt();
        } catch (e) { silent = false; }
    }
    (function waitForGoogle(n) {
        if (hookGoogle()) { silentRecheck(); return; }
        if (n < 40) setTimeout(() => waitForGoogle(n + 1), 250);
    })(0);

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
