/*
   MusicFinder full-song finder (Vercel serverless function)

   Finds the best matching embeddable YouTube video for a song, so the site
   can play the FULL song through YouTube's official embedded player.

   Needs one environment variable in Vercel:  YOUTUBE_API_KEY

   GET /api/youtube?title=Blinding%20Lights&artist=The%20Weeknd
   -> { "videoId": "4NRXx6U8ABQ", "title": "..." }
*/

function cleanTitle(name) {
    return (name || "")
        .replace(/\(.*?\)|\[.*?\]/g, " ")
        .replace(/\s-\s.*$/, " ")
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

const UNWANTED = /\b(cover|karaoke|reaction|remix|live|instrumental|tutorial|slowed|sped)\b/;

function chooseVideo(items, title, artist) {

    const wantedTitle = normalize(cleanTitle(title));
    const wantedArtist = normalize(artist);
    const originalTitle = normalize(title);

    const scored = items.map(item => {

        const videoTitle = normalize(item.snippet?.title);
        const channel = normalize(item.snippet?.channelTitle);

        let score = 0;

        if (wantedArtist && (videoTitle.includes(wantedArtist) || channel.includes(wantedArtist))) score += 2;
        if (wantedTitle && videoTitle.includes(wantedTitle)) score += 2;
        if (/official (audio|music video|video)/.test(videoTitle) || channel.endsWith(" topic")) score += 1;
        if (UNWANTED.test(videoTitle) && !UNWANTED.test(originalTitle)) score -= 2;

        return { item, score };

    });

    scored.sort((a, b) => b.score - a.score);

    return scored[0]?.item || null;
}

async function searchYouTube(apiKey, query, extraParams) {

    const params = new URLSearchParams({
        part: "snippet",
        type: "video",
        maxResults: "5",
        q: query,
        key: apiKey,
        ...extraParams
    });

    const response = await fetch(
        "https://www.googleapis.com/youtube/v3/search?" + params.toString(),
        { signal: AbortSignal.timeout(6000) }
    );

    const data = await response.json();

    return { ok: response.ok, status: response.status, data };
}

function describeError(result) {

    const error = result.data?.error || {};
    const reason = error.errors?.[0]?.reason || result.status;

    return `YouTube API error (${reason}): ${error.message || "unknown error"}`;
}

function isInvalidKey(result) {
    return /api key not valid|keyInvalid|API_KEY_INVALID/i.test(JSON.stringify(result.data || {}));
}

module.exports = async function handler(req, res) {

    const title = String(req.query.title || "").slice(0, 200).trim();
    const artist = String(req.query.artist || "").slice(0, 200).trim();

    res.setHeader("Cache-Control", "no-store");

    if (!title) {
        res.status(400).json({ videoId: null, error: "title is required" });
        return;
    }

    /* Remove accidental spaces, line breaks or quotes pasted with the key */
    const apiKey = (process.env.YOUTUBE_API_KEY || "")
        .trim()
        .replace(/^["']+|["']+$/g, "")
        .trim();

    if (!apiKey) {
        res.status(200).json({ videoId: null, error: "YOUTUBE_API_KEY is not set in Vercel" });
        return;
    }

    const query = `${artist} - ${cleanTitle(title)} official audio`.trim();

    /* Try strict filters first, then simpler ones if YouTube rejects them */
    const attempts = [
        { videoCategoryId: "10", videoEmbeddable: "true", videoSyndicated: "true" },
        { videoEmbeddable: "true" },
        {}
    ];

    try {

        let result = null;

        for (const extra of attempts) {

            result = await searchYouTube(apiKey, query, extra);

            if (result.ok) break;

            if (isInvalidKey(result)) {
                res.status(200).json({
                    videoId: null,
                    error: "The API key is not valid. Copy the key again into YOUTUBE_API_KEY in Vercel (it starts with AIza, no spaces or quotes), then Redeploy."
                });
                return;
            }

            // Only parameter problems (400) are worth retrying with fewer filters
            if (result.status !== 400) break;
        }

        if (!result.ok) {
            res.status(200).json({ videoId: null, error: describeError(result) });
            return;
        }

        const best = chooseVideo(result.data.items || [], title, artist);

        if (!best) {
            res.status(200).json({ videoId: null, error: "no video found" });
            return;
        }

        /* Video ids do not change, so this can be cached for a long time */
        res.setHeader("Cache-Control", "s-maxage=86400");

        res.status(200).json({
            videoId: best.id.videoId,
            title: best.snippet?.title || ""
        });

    } catch (error) {

        res.status(200).json({ videoId: null, error: "lookup failed: " + (error.message || "unknown") });

    }
};
