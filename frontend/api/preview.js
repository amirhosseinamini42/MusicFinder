/*
   MusicFinder preview finder (Vercel serverless function)

   Runs on the server, so the browser never talks to Deezer / iTunes directly.
   That avoids CORS problems and regional blocking on the visitor's network.

   GET /api/preview?title=Blinding%20Lights&artist=The%20Weeknd
   -> { "sources": [ { "source": "deezer", "url": "..." }, { "source": "itunes", "url": "..." } ] }
*/

function cleanTitle(name) {
    return (name || "")
        .replace(/\(.*?\)|\[.*?\]/g, " ")   // (feat. X), (Remastered 2011)
        .replace(/\s-\s.*$/, " ")           // - Remastered, - Radio Edit
        .replace(/\s+/g, " ")
        .trim();
}

function normalize(text) {
    return (text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^\p{L}\p{N} ]/gu, " ")
        .replace(/\s+/g, " ")
        .trim();
}

/* Choose the result whose artist and title best match the wanted song */
function pickBest(items, wantedTitle, wantedArtist, read) {

    const title = normalize(cleanTitle(wantedTitle));
    const artist = normalize(wantedArtist);

    const usable = items.map(read).filter(item => item.url);

    const sameArtist = item => {
        const a = normalize(item.artist);
        return artist && a && (a.includes(artist) || artist.includes(a));
    };

    const sameTitle = item => {
        const t = normalize(cleanTitle(item.title));
        return t && title && (t.includes(title) || title.includes(t));
    };

    if (!artist) {
        return usable.find(sameTitle) || null;
    }

    return (
        usable.find(item => sameArtist(item) && sameTitle(item)) ||
        usable.find(sameArtist) ||
        null
    );
}

async function getJson(url) {
    const response = await fetch(url, { signal: AbortSignal.timeout(6000) });

    if (!response.ok) {
        throw new Error("HTTP " + response.status);
    }

    return response.json();
}

async function fromDeezer(title, artist) {

    const queries = [
        `track:"${cleanTitle(title)}" artist:"${artist}"`,
        `${cleanTitle(title)} ${artist}`
    ];

    for (const query of queries) {

        const data = await getJson(
            `https://api.deezer.com/search?q=${encodeURIComponent(query)}&limit=15`
        );

        const best = pickBest(
            data.data || [],
            title,
            artist,
            track => ({
                title: track.title,
                artist: track.artist?.name,
                url: track.preview
            })
        );

        if (best) return best.url;
    }

    return null;
}

async function fromItunes(title, artist) {

    for (const country of ["US", "GB"]) {

        const term = `${cleanTitle(title)} ${artist}`.trim();

        const data = await getJson(
            `https://itunes.apple.com/search?term=${encodeURIComponent(term)}` +
            `&media=music&entity=song&limit=25&country=${country}`
        );

        const best = pickBest(
            data.results || [],
            title,
            artist,
            track => ({
                title: track.trackName,
                artist: track.artistName,
                url: track.previewUrl
            })
        );

        if (best) return best.url;
    }

    return null;
}

module.exports = async function handler(req, res) {

    const title = String(req.query.title || "").slice(0, 200).trim();
    const artist = String(req.query.artist || "").slice(0, 200).trim();

    if (!title) {
        res.status(400).json({ error: "title is required", sources: [] });
        return;
    }

    const [deezer, itunes] = await Promise.allSettled([
        fromDeezer(title, artist),
        fromItunes(title, artist)
    ]);

    const sources = [];

    if (deezer.status === "fulfilled" && deezer.value) {
        sources.push({ source: "deezer", url: deezer.value });
    }

    if (itunes.status === "fulfilled" && itunes.value) {
        sources.push({ source: "itunes", url: itunes.value });
    }

    /* Preview links expire after a while, so only cache for a few minutes */
    res.setHeader(
        "Cache-Control",
        sources.length ? "s-maxage=300" : "no-store"
    );

    res.status(200).json({ sources });
};
