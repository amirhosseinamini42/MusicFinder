/* MusicFinder: published uploaded tracks ("Songs on MusicFinder") in the existing search + player.
   Additive: loaded AFTER the main inline scripts. It wraps two existing globals and touches nothing else:
     - renderSearchResults(data, query): after the normal render, appends an "Originals" group
     - getPreviewSources(song): for ids like "mf:<uuid>" asks the API for a fresh short-lived signed URL
   Relies on existing globals: API_BASE, escapeHtml, playMusicFinderSong (the single player), window.currentTracks. */
(function () {
    if (typeof renderSearchResults !== "function" || typeof getPreviewSources !== "function") return;

    const isMf = id => typeof id === "string" && id.startsWith("mf:");
    if (window.MF_FA) Object.assign(window.MF_FA, {
        "Songs on MusicFinder": "آهنگ‌های MusicFinder", "Unreleased Song": "آهنگ منتشرنشده", "Learn more": "بیشتر بدانید"
    });

    /* Reusable "Learn more" popup (uses the site's existing overlay styles) */
    window.mfShowInfo = function (title, text) {
        document.getElementById("mfInfoOv")?.remove();
        const ov = document.createElement("div");
        ov.id = "mfInfoOv"; ov.className = "mfOverlay";
        ov.innerHTML = `<div class="mfPicker glass" role="dialog" aria-modal="true"><h4>${escapeHtml(title)}</h4>
            <p class="modalText">${escapeHtml(text)}</p>
            <button type="button" class="smallBtn" style="width:100%">Close</button></div>`;
        ov.onclick = e => { if (e.target === ov || e.target.tagName === "BUTTON") ov.remove(); };
        document.body.appendChild(ov);
        ov.querySelector("button").focus();
    };
    window.mfLearnUnreleased = () => mfShowInfo("Unreleased Song",
        "This song has not been officially released yet. It is shared on MusicFinder by the site's administrators and may change or be removed.");

    /* --- playback source: signed URL fetched at play time (URLs expire; never cached long) --- */
    const origSources = getPreviewSources;
    window.getPreviewSources = async function (song) {
        if (!song || !isMf(song.id)) return origSources(song);
        try {
            const r = await fetch(`${API_BASE}/tracks/${encodeURIComponent(song.id.slice(3))}/play`, { cache: "no-store" });
            if (!r.ok) throw new Error("play " + r.status);
            return [(await r.json()).url];
        } catch (e) {
            return [];
        }
    };

    /* --- search: append published originals after the Spotify results --- */
    const origRender = renderSearchResults;
    window.renderSearchResults = function (data, query) {
        origRender(data, query);
        const seq = window.mfSearchSeq;
        const base = window.currentTracks;
        fetch(`${API_BASE}/tracks/search?q=${encodeURIComponent(query)}&limit=10`, { cache: "no-store" })
            .then(r => (r.ok ? r.json() : { tracks: [] }))
            .then(({ tracks }) => {
                if (seq !== window.mfSearchSeq || base !== window.currentTracks || !tracks || !tracks.length) return;
                window.currentTracks = base.concat(tracks);          // lets favorites/playlists buttons attach via existing inject()
                const box = document.getElementById("searchResults");
                if (!box) return;
                box.querySelector("[data-mf-originals]")?.remove();
                box.insertAdjacentHTML("afterbegin", originalsHtml(tracks));
            })
            .catch(() => {});                                         // originals are optional; Spotify results already shown
    };

    function card(t) {
        const img = t.album?.images?.[0]?.url || "";
        const id = escapeHtml(t.id);
        return `<div class="resultCard glass">
            ${img ? `<img class="cover" src="${escapeHtml(img)}" alt="">` : `<div class="cover"></div>`}
            <div class="cardTitle">${escapeHtml(t.name)}</div>
            <div class="cardArtist">${escapeHtml(t.artists?.[0]?.name || "")}</div>
            <div class="cardMeta">${escapeHtml(t.album?.name || "")}</div>
            ${t.is_unreleased ? `<div class="cardMeta"><span class="historyItem" style="cursor:default;padding:3px 9px;border-radius:999px;font-size:11px">Unreleased Song</span>
                <button type="button" class="smallBtn" style="flex:none;padding:3px 9px;font-size:11px" onclick="mfLearnUnreleased()">Learn more</button></div>` : ""}
            <div class="cardActions">
                <button type="button" class="smallBtn primary full"
                    onclick="event.stopPropagation(); playMusicFinderSong(window.currentTracks.find(t => t.id === '${id}'), window.currentTracks)">Play</button>
                ${t.download_enabled ? `<button type="button" class="smallBtn" onclick="mfDownloadOriginal('${id}')">Download</button>` : ""}
            </div></div>`;
    }
    function originalsHtml(tracks) {
        return `<div class="resultGroup" data-mf-originals>
            <h3 class="resultGroupTitle">🎧 Songs on MusicFinder</h3>
            <div class="resultGrid">${tracks.map(card).join("")}</div></div>`;
    }

    window.mfDownloadOriginal = async function (id) {
        try {
            const r = await fetch(`${API_BASE}/tracks/${encodeURIComponent(id.slice(3))}/download`, { cache: "no-store" });
            if (!r.ok) throw new Error();
            window.open((await r.json()).url, "_blank", "noopener");
        } catch (e) { alert("Download is not available for this track."); }
    };
})();