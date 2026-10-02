/*
   MusicFinder free music search (Vercel serverless function)

   Searches only music that artists have made free to download:
     - Jamendo   (Creative Commons; needs a free JAMENDO_CLIENT_ID, optional)
     - Audius    (only tracks whose artist enabled downloads)
     - Openverse (Creative Commons / public domain audio)

   GET /api/free?q=piano
   -> { "tracks": [ { id, source, title, artist, image, duration, license,
                      licenseUrl, pageUrl, streamUrl, downloadUrl, extension } ],
        "status": { jamendo: "...", audius: "...", openverse: "..." } }
*/

const { isAllowedUrl } = require("./_shared.js");

const APP_NAME = "MusicFinder";

function normalize(text) {
    return (text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^\p{L}\p{N} ]/gu, " ")
        .replace(/\s+/g, " ")
        .trim();
}

async function getJson(url, headers = {}) {

    const response = await fetch(url, {
        headers: { "User-Agent": "MusicFinder/1.0", ...headers },
        signal: AbortSignal.timeout(7000)
    });

    if (!response.ok) {
        throw new Error("HTTP " + response.status);
    }

    return response.json();
}

function licenseName(url) {

    const match = /creativecommons\.org\/(licenses|publicdomain)\/([a-z-]+)\/?([0-9.]+)?/i.exec(url || "");

    if (!match) return "Free license";

    if (match[1].toLowerCase() === "publicdomain") {
        return match[2].toLowerCase() === "zero" ? "CC0" : "Public domain";
    }

    return ("CC " + match[2] + (match[3] ? " " + match[3] : "")).toUpperCase();
}

function extensionFromUrl(url) {

    const match = /\.([a-z0-9]{2,4})(?:\?|$)/i.exec(String(url || "").split("#")[0]);

    return match ? match[1].toLowerCase() : "";
}

/* ---------- Jamendo ---------- */

async function fromJamendo(query) {

    const clientId = (process.env.JAMENDO_CLIENT_ID || "").trim();

    if (!clientId) {
        return { tracks: [], note: "skipped (JAMENDO_CLIENT_ID is not set)" };
    }

    const params = new URLSearchParams({
        client_id: clientId,
        format: "json",
        limit: "15",
        search: query,
        order: "relevance",
        audiodlformat: "mp32"
    });

    const data = await getJson("https://api.jamendo.com/v3.0/tracks/?" + params.toString());

    const tracks = (data.results || [])
        .filter(track => track.audiodownload_allowed && track.audiodownload)
        .map(track => ({
            id: "jamendo:" + track.id,
            source: "Jamendo",
            title: track.name,
            artist: track.artist_name,
            image: track.image || "",
            duration: Number(track.duration) || 0,
            license: licenseName(track.license_ccurl),
            licenseUrl: track.license_ccurl || "",
            pageUrl: track.shareurl || `https://www.jamendo.com/track/${track.id}`,
            streamUrl: track.audio || track.audiodownload,
            downloadUrl: track.audiodownload,
            extension: "mp3"
        }));

    return { tracks, note: "ok" };
}

/* ---------- Audius ---------- */

function isFreeAudiusTrack(track) {

    const downloadable =
        track.downloadable === true ||
        track.is_downloadable === true ||
        track.download?.is_downloadable === true;

    const blocked =
        track.is_streamable === false ||
        track.is_unlisted === true ||
        track.is_delete === true ||
        track.is_stream_gated ||
        track.is_download_gated ||
        track.download?.requires_follow;

    return downloadable && !blocked;
}

async function fromAudius(query) {

    const headers = process.env.AUDIUS_API_KEY
        ? { Authorization: "Bearer " + process.env.AUDIUS_API_KEY }
        : {};

    const params = new URLSearchParams({
        query,
        app_name: APP_NAME,
        limit: "40"
    });

    const data = await getJson(
        "https://api.audius.co/v1/tracks/search?" + params.toString(),
        headers
    );

    const tracks = (data.data || [])
        .filter(isFreeAudiusTrack)
        .slice(0, 15)
        .map(track => {

            const base = "https://api.audius.co/v1/tracks/" + encodeURIComponent(track.id);

            return {
                id: "audius:" + track.id,
                source: "Audius",
                title: track.title,
                artist: track.user?.name || track.user?.handle || "Unknown artist",
                image: track.artwork?.["480x480"] || track.artwork?.["150x150"] || "",
                duration: Number(track.duration) || 0,
                license: "Download enabled by the artist",
                licenseUrl: "",
                pageUrl: track.permalink ? "https://audius.co" + track.permalink : "https://audius.co",
                streamUrl: `${base}/stream?app_name=${APP_NAME}`,
                downloadUrl: `${base}/download?app_name=${APP_NAME}`,
                extension: "mp3"
            };

        });

    return { tracks, note: "ok" };
}

/* ---------- Openverse ---------- */

async function fromOpenverse(query) {

    const params = new URLSearchParams({
        q: query,
        category: "music",
        page_size: "20"
    });

    const data = await getJson("https://api.openverse.org/v1/audio/?" + params.toString());

    const tracks = (data.results || [])
        .filter(track => track.url && isAllowedUrl(track.url))
        .map(track => ({
            id: "openverse:" + track.id,
            source: "Openverse",
            title: track.title || "Untitled",
            artist: track.creator || "Unknown artist",
            image: track.thumbnail || "",
            duration: Math.round((Number(track.duration) || 0) / 1000),
            license: track.license
                ? ("CC " + track.license + (track.license_version ? " " + track.license_version : "")).toUpperCase()
                : "Free license",
            licenseUrl: track.license_url || "",
            pageUrl: track.foreign_landing_url || `https://openverse.org/audio/${track.id}`,
            streamUrl: track.url,
            downloadUrl: track.url,
            extension: track.filetype || extensionFromUrl(track.url) || "mp3"
        }));

    return { tracks, note: "ok" };
}

/* ---------- Merge ---------- */

function mergeResults(lists) {

    const seen = new Set();
    const merged = [];
    const longest = Math.max(0, ...lists.map(list => list.length));

    // Take one from each source in turn, so every source is represented
    for (let i = 0; i < longest; i++) {

        for (const list of lists) {

            const track = list[i];

            if (!track) continue;

            const key = normalize(track.title) + "|" + normalize(track.artist);

            if (seen.has(key)) continue;

            seen.add(key);
            merged.push(track);

        }

    }

    return merged.slice(0, 36);
}

module.exports = async function handler(req, res) {

    const query = String(req.query.q || "").slice(0, 100).trim();

    if (!query) {
        res.status(400).json({ tracks: [], error: "q is required" });
        return;
    }

    const names = ["jamendo", "audius", "openverse"];

    const settled = await Promise.allSettled([
        fromJamendo(query),
        fromAudius(query),
        fromOpenverse(query)
    ]);

    const status = {};
    const lists = [];

    settled.forEach((result, index) => {

        if (result.status === "fulfilled") {

            status[names[index]] = result.value.note + ` (${result.value.tracks.length})`;
            lists.push(result.value.tracks);

        } else {

            status[names[index]] = "error: " + (result.reason?.message || "unknown");
            lists.push([]);

        }

    });

    const tracks = mergeResults(lists);

    res.setHeader("Cache-Control", tracks.length ? "s-maxage=300" : "no-store");
    res.status(200).json({ tracks, status });
};
