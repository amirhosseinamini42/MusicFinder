/*
   MusicFinder download helper (Vercel serverless function)

   Streams a legally free song through our own server so the browser saves
   it as a real file with a proper name (cross-origin links would just play).
   Only addresses from approved free-music hosts are accepted.

   GET /api/download?url=<file url>&name=<artist - title>&ext=mp3
   GET /api/download?play=1&url=<file url>      (streams for the player; supports seeking)

   Going through our own server also helps visitors whose network blocks
   the original music host.
*/

const { Readable } = require("stream");
const { isAllowedUrl, cleanFileName } = require("./_shared.js");

function openUpstream(url, range, long) {

    const headers = { "User-Agent": "MusicFinder/1.0" };

    if (range) headers.Range = range;

    return fetch(url, {
        redirect: "follow",
        headers,
        signal: AbortSignal.timeout(long ? 55000 : 25000)
    });

}

module.exports = async function handler(req, res) {

    const url = String(req.query.url || "");
    const play = String(req.query.play || "") === "1";
    const range = play ? (req.headers?.range || "") : "";
    const baseName = cleanFileName(req.query.name, "song");
    const extension = String(req.query.ext || "mp3").replace(/[^a-z0-9]/gi, "").slice(0, 5) || "mp3";

    if (!isAllowedUrl(url)) {
        res.status(400).send("This address is not allowed.");
        return;
    }

    try {

        let upstream = await openUpstream(url, range, play);

        // Audius: if /download is refused, the artist-enabled stream is the same track
        if (!upstream.ok && /api\.audius\.co\/v1\/tracks\/[^/]+\/download/.test(url)) {
            upstream = await openUpstream(url.replace("/download", "/stream"), range, play);
        }

        if (!upstream.ok || !upstream.body) {
            res.status(502).send(`The file could not be fetched (${upstream.status}).`);
            return;
        }

        const type = upstream.headers.get("content-type") || "audio/mpeg";

        if (/text\/html|application\/json/i.test(type)) {
            res.status(502).send("The source did not return an audio file.");
            return;
        }

        const fileName = `${baseName}.${extension}`;

        const asciiName = fileName
            .replace(/[^\x20-\x7e]/g, "_")
            .replace(/"/g, "");

        const encodedName = encodeURIComponent(fileName)
            .replace(/['()*]/g, char => "%" + char.charCodeAt(0).toString(16).toUpperCase());

        res.setHeader("Content-Type", type);

        if (play) {

            res.setHeader("Content-Disposition", "inline");
            res.setHeader("Cache-Control", "private, max-age=3600");
            res.setHeader("Accept-Ranges", "bytes");

            const contentRange = upstream.headers.get("content-range");

            if (contentRange) res.setHeader("Content-Range", contentRange);

        } else {

            res.setHeader(
                "Content-Disposition",
                `attachment; filename="${asciiName}"; filename*=UTF-8''${encodedName}`
            );
            res.setHeader("Cache-Control", "private, no-store");

        }

        const length = upstream.headers.get("content-length");

        if (length && !upstream.headers.get("content-encoding")) {
            res.setHeader("Content-Length", length);
        }

        res.status(play && upstream.status === 206 ? 206 : 200);

        Readable.fromWeb(upstream.body).pipe(res);

    } catch (error) {

        if (!res.headersSent) {
            res.status(502).send("Download failed.");
        } else {
            res.end();
        }

    }

};
