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

module.exports = async function handler(req, res) {

    const title = String(req.query.title || "").slice(0, 200).trim();
    const artist = String(req.query.artist || "").slice(0, 200).trim();

    res.setHeader("Cache-Control", "no-store");

    if (!title) {
        res.status(400).json({ videoId: null, error: "title is required" });
        return;
    }

    const apiKey = process.env.YOUTUBE_API_KEY;

    if (!apiKey) {
        res.status(200).json({ videoId: null, error: "YOUTUBE_API_KEY is not set in Vercel" });
        return;
    }

    const query = `${artist} - ${cleanTitle(title)} official audio`.trim();

    const url =
        "https://www.googleapis.com/youtube/v3/search" +
        "?part=snippet&type=video&videoCategoryId=10" +
        "&videoEmbeddable=true&videoSyndicated=true&maxResults=5" +
        `&q=${encodeURIComponent(query)}` +
        `&key=${encodeURIComponent(apiKey)}`;

    try {

        const response = await fetch(url, { signal: AbortSignal.timeout(6000) });
        const data = await response.json();

        if (!response.ok) {
            const reason = data.error?.errors?.[0]?.reason || response.status;
            res.status(200).json({
                videoId: null,
                error: `YouTube API error: ${reason}`
            });
            return;
        }

        const best = chooseVideo(data.items || [], title, artist);

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

        res.status(200).json({ videoId: null, error: "lookup failed" });

    }
};
