/*
   Shared helpers for the free-music API routes.
   (Files starting with "_" are not exposed as URLs by Vercel.)
*/

/* Hosts we are willing to download from: legal / openly licensed music only */
const ALLOWED_HOSTS = [
    "jamendo.com",
    "audius.co",
    "freesound.org",
    "wikimedia.org",
    "archive.org",
    "freemusicarchive.org",
    "ccmixter.org",
    "musopen.org"
];

function isAllowedUrl(value) {

    try {

        const url = new URL(value);

        if (url.protocol !== "https:") return false;

        const host = url.hostname.toLowerCase();

        return ALLOWED_HOSTS.some(
            allowed => host === allowed || host.endsWith("." + allowed)
        );

    } catch {

        return false;

    }

}

function cleanFileName(name, fallback = "song") {

    const cleaned = String(name || "")
        .replace(/[\\/:*?"<>|\u0000-\u001f]/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 120);

    return cleaned || fallback;

}

module.exports = { isAllowedUrl, cleanFileName };
