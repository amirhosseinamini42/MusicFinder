/* Shared Supabase Auth client for MusicFinder site + admin. Public key only. */
(function (w) {
    "use strict";
    const API_BASE = "https://musicfinder-api.vercel.app";
    let client = null;
    let initPromise = null;
    let googleEnabled = false;

    async function init() {
        if (client) return client;
        if (initPromise) return initPromise;
        initPromise = (async () => {
            if (!w.supabase || typeof w.supabase.createClient !== "function") {
                throw new Error("auth_sdk_unavailable");
            }
            const response = await fetch(API_BASE + "/config/supabase", { cache: "no-store" });
            if (!response.ok) throw new Error("auth_not_configured");
            const config = await response.json();
            if (!config || typeof config.url !== "string" || typeof config.publishableKey !== "string" ||
                !config.url.startsWith("https://") || !config.publishableKey) {
                throw new Error("auth_config_invalid");
            }
            client = w.supabase.createClient(config.url, config.publishableKey, {
                auth: {
                    autoRefreshToken: true,
                    persistSession: true,
                    detectSessionInUrl: true,
                    flowType: "pkce"
                }
            });
            try {
                const settingsResponse = await fetch(config.url.replace(/\/$/, "") + "/auth/v1/settings", {
                    headers: { apikey: config.publishableKey }, cache: "no-store"
                });
                if (settingsResponse.ok) {
                    const settings = await settingsResponse.json();
                    googleEnabled = Array.isArray(settings.external) && settings.external.includes("google");
                }
            } catch { googleEnabled = false; }
            return client;
        })();
        try { return await initPromise; }
        catch (error) { initPromise = null; throw error; }
    }

    async function auth() { const c = await init(); return c.auth; }
    async function getSession() {
        const a = await auth();
        const { data, error } = await a.getSession();
        if (error) throw error;
        return data.session || null;
    }
    async function signIn(email, password) {
        const a = await auth();
        const { data, error } = await a.signInWithPassword({ email: email.trim(), password });
        if (error) throw error;
        return data;
    }
    async function signUp(name, email, password) {
        const a = await auth();
        const { data, error } = await a.signUp({
            email: email.trim(), password,
            options: { data: { full_name: name.trim() } }
        });
        if (error) throw error;
        return data;
    }
    async function signInWithGoogle() {
        const a = await auth();
        // Keep OAuth on the canonical same-origin home URL; the session is shared with /admin.html.
        const redirectTo = window.location.origin + "/";
        const { data, error } = await a.signInWithOAuth({
            provider: "google",
            options: { redirectTo, queryParams: { access_type: "offline", prompt: "select_account" } }
        });
        if (error) throw error;
        return data;
    }
    async function signOut() {
        const a = await auth();
        const { error } = await a.signOut({ scope: "local" });
        if (error) throw error;
    }
    async function resetPassword(email) {
        const a = await auth();
        const redirectTo = window.location.origin + "/?auth=recovery";
        const { error } = await a.resetPasswordForEmail(email.trim(), { redirectTo });
        if (error) throw error;
    }
    async function resendSignup(email) {
        const a = await auth();
        const { error } = await a.resend({ type: "signup", email: email.trim() });
        if (error) throw error;
    }
    async function updatePassword(password) {
        const a = await auth();
        const { data, error } = await a.updateUser({ password });
        if (error) throw error;
        return data.user;
    }
    async function updateName(name) {
        const a = await auth();
        const { data, error } = await a.updateUser({ data: { full_name: name.trim() } });
        if (error) throw error;
        return data.user;
    }
    async function uploadAvatar(file) {
        if (!(file instanceof File) || !["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size < 1 || file.size > 3 * 1024 * 1024) {
            throw new Error("avatar_invalid");
        }
        const c = await init();
        const session = await getSession();
        if (!session || !session.user) throw new Error("auth_required");
        const ext = file.type === "image/jpeg" ? "jpg" : file.type === "image/png" ? "png" : "webp";
        const path = session.user.id + "/" + crypto.randomUUID() + "." + ext;
        const oldPath = session.user.user_metadata && session.user.user_metadata.avatar_path;
        const bucket = c.storage.from("mf-avatars");
        const { error: uploadError } = await bucket.upload(path, file, {
            contentType: file.type, cacheControl: "3600", upsert: false
        });
        if (uploadError) throw uploadError;
        const { data } = bucket.getPublicUrl(path);
        const { data: updated, error } = await (await auth()).updateUser({ data: { avatar_url: data.publicUrl, avatar_path: path } });
        if (error) { await bucket.remove([path]).catch(() => {}); throw error; }
        if (typeof oldPath === "string" && oldPath.startsWith(session.user.id + "/") && oldPath !== path) {
            await bucket.remove([oldPath]).catch(() => {});
        }
        return updated.user;
    }
    function onAuthStateChange(callback) {
        if (!client) throw new Error("auth_not_initialized");
        return client.auth.onAuthStateChange(callback);
    }
    function isGoogleEnabled() { return googleEnabled; }
    w.MFAuth = Object.freeze({ init, getSession, signIn, signUp, signInWithGoogle, signOut,
        resetPassword, resendSignup, updatePassword, updateName, uploadAvatar, onAuthStateChange, isGoogleEnabled });
})(window);
