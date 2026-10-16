package com.netbridge.lite

import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL

object Net {
    const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"

    private fun open(url: String, proxyPort: Int?, timeoutMs: Int): HttpURLConnection {
        val proxy = if (proxyPort != null && proxyPort > 0) Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", proxyPort)) else Proxy.NO_PROXY
        val c = URL(url).openConnection(proxy) as HttpURLConnection
        c.connectTimeout = timeoutMs; c.readTimeout = timeoutMs
        c.instanceFollowRedirects = false
        c.setRequestProperty("User-Agent", UA); c.setRequestProperty("Accept-Language", "en")
        return c
    }

    /** (status, ms) of a real request through the local HTTP proxy of a running Xray. Reads some body so a stalled page is noticed. */
    fun fetchVia(proxyPort: Int, url: String, timeoutMs: Int, read: Int = 20000): Pair<Int, Int> {
        val c = open(url, proxyPort, timeoutMs)
        val t = System.currentTimeMillis()
        try {
            val code = c.responseCode
            val st = if (code >= 400) c.errorStream else c.inputStream
            st?.use { s -> val buf = ByteArray(4096); var n = 0; while (n < read) { val r = s.read(buf); if (r < 0) break; n += r } }
            return code to (System.currentTimeMillis() - t).toInt()
        } finally { c.disconnect() }
    }

    const val UPLOAD_URL = "https://speed.cloudflare.com/__up"

    /** POSTs [size] bytes through the local proxy. Returns ms once the server answered (any HTTP status: the body got
     *  through). Throws on stall/timeout - that is the "upload-limited" channel (~6 upstream packets). */
    fun uploadVia(proxyPort: Int, url: String = UPLOAD_URL, size: Int = 50_000, timeoutMs: Int = 10000): Int {
        val c = open(url, proxyPort, timeoutMs)
        val t = System.currentTimeMillis()
        try {
            c.requestMethod = "POST"; c.doOutput = true
            c.setFixedLengthStreamingMode(size)
            c.setRequestProperty("Content-Type", "application/octet-stream")
            c.outputStream.use { it.write(ByteArray(size)) }
            c.responseCode
            return (System.currentTimeMillis() - t).toInt()
        } finally { c.disconnect() }
    }

    fun getText(url: String, proxyPort: Int? = null, timeoutMs: Int = 20000, maxBytes: Int = 10 * 1024 * 1024): String {
        val c = open(url, proxyPort, timeoutMs)
        c.instanceFollowRedirects = true
        c.setRequestProperty("User-Agent", "NetBridge")
        try {
            val out = java.io.ByteArrayOutputStream(); val buf = ByteArray(8192)
            c.inputStream.use { s ->
                while (true) {
                    val r = s.read(buf); if (r < 0) break
                    out.write(buf, 0, r)
                    if (out.size() > maxBytes) throw IllegalStateException("subscription is larger than 10 MB - refused")
                }
            }
            return out.toString("UTF-8")
        } finally { c.disconnect() }
    }

    fun fetchSubscription(url: String, proxyPort: Int? = null): Pair<List<P>, Int> {
        var raw = getText(url.trim(), proxyPort).trim()
        if ("://" !in raw) try { raw = Parser.b64(raw) } catch (_: Exception) { }
        return Parser.parseMany(raw)
    }

    /** what the outside world sees through the tunnel: "IP · Country" */
    fun exitInfo(proxyPort: Int): String {
        val j = org.json.JSONObject(getText("http://ip-api.com/json/?fields=query,country", proxyPort, 10000))
        return "${j.optString("query")} · ${j.optString("country")}"
    }
}
