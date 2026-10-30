/* MusicFinder: published uploaded tracks ("MusicFinder Originals") in the existing search + player.
   Additive: loaded AFTER the main inline scripts. It wraps two existing globals and touches nothing else:
     - renderSearchResults(data, query): after the normal render, appends an "Originals" group
     - getPreviewSources(song): for ids like "mf:<uuid>" asks the API for a fresh short-lived signed URL
   Relies on existing globals: API_BASE, escapeHtml, playMusicFinderSong (the single player), window.currentTracks. */
(function () {
    if (typeof renderSearchResults !== "function" || typeof getPreviewSources !== "function") return;

    const isMf = id => typeof id === "string" && id.startsWith("mf:");
    if (window.MF_FA) window.MF_FA["MusicFinder Originals"] = "آثار اصلی MusicFinder";

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
            <div class="cardActions">
                <button type="button" class="smallBtn primary full"
                    onclick="event.stopPropagation(); playMusicFinderSong(window.currentTracks.find(t => t.id === '${id}'), window.currentTracks)">Play</button>
                ${t.download_enabled ? `<button type="button" class="smallBtn" onclick="mfDownloadOriginal('${id}')">Download</button>` : ""}
            </div></div>`;
    }
    function originalsHtml(tracks) {
        return `<div class="resultGroup" data-mf-originals>
            <h3 class="resultGroupTitle">🎧 MusicFinder Originals</h3>
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
