package com.netbridge.lite

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL
import java.security.SecureRandom

/** Telegram "web proxy" on the user's OWN Cloudflare account (same steps as app/core/tg_proxy.py).
 *  The Worker is the open-source ToiCF/CF-Workers-TGProxy (GPL-3.0). It is NOT bundled: it is downloaded from the project's own
 *  repository when the button is pressed. Needs two secrets (SECRET = 32 hex, BOOT = random text) which are made here.
 *  The Cloudflare token is used for these calls only and never stored. */
object TgProxy {
    val SOURCES = listOf(
        "https://raw.githubusercontent.com/ToiCF/CF-Workers-TGProxy/main/telegram_webproxy.js",
        "https://cdn.jsdelivr.net/gh/ToiCF/CF-Workers-TGProxy@main/telegram_webproxy.js")
    private const val MAX_SOURCE = 2_000_000
    private val TOKEN = Regex("^[A-Za-z0-9_\\-]{20,120}$")
    private val LABEL = Regex("^[a-z0-9]([a-z0-9\\-]{0,40}[a-z0-9])?$")
    private val HOST = Regex("^(?=.{4,253}$)([a-z0-9]([a-z0-9\\-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}$")
    private val NAME = Regex("^[a-z0-9][a-z0-9\\-]{0,40}$")

    class Result(val name: String, val secret: String, val boot: String, val workersHost: String, val domain: String?, val server: String) {
        val link: String get() = link(server, secret)
    }

    private fun hex(n: Int): String { val b = ByteArray(n); SecureRandom().nextBytes(b); return b.joinToString("") { "%02x".format(it) } }
    fun genSecret() = hex(16)
    fun genBoot() = hex(24)
    fun link(server: String, secret: String) = "https://t.me/webproxy?server=$server&secret=$secret"

    /** The Worker file; `get(url)` returns the text or throws. First mirror that gives the expected file wins. */
    fun fetchSource(get: (String) -> String, urls: List<String> = SOURCES): String {
        var last = "no address tried"
        for (u in urls) {
            val text = try { get(u) } catch (e: Exception) { last = e.message ?: "error"; continue }
            if (text.length > MAX_SOURCE) { last = "file too large"; continue }
            if (!text.contains("export default") || !text.contains("SECRET") || !text.contains("BOOT")) { last = "the file is not the expected Worker"; continue }
            return text
        }
        throw CfDeploy.DeployError("could not download the Telegram proxy Worker ($last)")
    }

    fun httpGet(proxyPort: Int?): (String) -> String = { u ->
        val proxy = if (proxyPort != null && proxyPort > 0) Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", proxyPort)) else Proxy.NO_PROXY
        val c = URL(u).openConnection(proxy) as HttpURLConnection
        try {
            c.connectTimeout = 30000; c.readTimeout = 30000; c.setRequestProperty("User-Agent", "NetBridge")
            if (c.responseCode != 200) throw CfDeploy.DeployError("HTTP ${c.responseCode}")
            val raw = c.inputStream.use { it.readBytes() }
            String(raw, Charsets.UTF_8)
        } finally { c.disconnect() }
    }

    /** (zone id, name) of the domains already on the account. */
    fun listZones(token: String, call: CfCall): List<Pair<String, String>> {
        val a = call("GET", "/zones?per_page=50&status=active", token.trim(), null, "application/json") as? JSONArray ?: return emptyList()
        return (0 until a.length()).mapNotNull { val z = a.optJSONObject(it) ?: return@mapNotNull null
            val id = z.optString("id"); val n = z.optString("name"); if (id.isEmpty() || n.isEmpty()) null else id to n }
    }

    fun hostname(label0: String?, zoneName: String): String {
        val label = (label0 ?: "").trim().lowercase()
        val host = if (label.isEmpty() || label == "@") zoneName.lowercase() else {
            if (!LABEL.matches(label)) throw CfDeploy.DeployError("the sub-domain may contain only a-z, 0-9 and '-'")
            "$label.${zoneName.lowercase()}"
        }
        if (!HOST.matches(host)) throw CfDeploy.DeployError("that is not a valid domain name")
        return host
    }

    private fun json(o: JSONObject) = o.toString().toByteArray()

    fun deploy(token0: String, source: String, zone: Pair<String, String>?, label: String, call: CfCall,
               name0: String? = null, progress: (String) -> Unit = {}): Result {
        val token = token0.trim()
        if (!TOKEN.matches(token)) throw CfDeploy.DeployError("that does not look like a Cloudflare API token")
        val name = name0 ?: ("tg-" + hex(4))
        if (!NAME.matches(name)) throw CfDeploy.DeployError("worker name may contain only a-z, 0-9 and '-'")
        val host = zone?.let { hostname(label, it.second) }
        val secret = genSecret(); val boot = genBoot()
        progress("token")
        call("GET", "/user/tokens/verify", token, null, "application/json")
        val accounts = call("GET", "/accounts", token, null, "application/json") as? JSONArray
        if (accounts == null || accounts.length() == 0)
            throw CfDeploy.DeployError("the token has no access to any account (use the 'Edit Cloudflare Workers' template)")
        val acc = accounts.getJSONObject(0).getString("id")
        progress("upload")
        val (body, ctype) = CfDeploy.multipart(source, listOf(
            JSONObject().put("type", "secret_text").put("name", "SECRET").put("text", secret),
            JSONObject().put("type", "secret_text").put("name", "BOOT").put("text", boot)))
        call("PUT", "/accounts/$acc/workers/scripts/$name", token, body, ctype)
        progress("subdomain")
        val sub = CfDeploy.ensureSubdomain(call, acc, token)
        call("POST", "/accounts/$acc/workers/scripts/$name/subdomain", token,
            json(JSONObject().put("enabled", true).put("previews_enabled", false)), "application/json")
        val wh = "$name.$sub.workers.dev"
        var domain: String? = null
        if (host != null && zone != null) {
            progress("domain")
            call("PUT", "/accounts/$acc/workers/domains", token,
                json(JSONObject().put("hostname", host).put("service", name).put("zone_id", zone.first).put("environment", "production")), "application/json")
            domain = host
        }
        return Result(name, secret, boot, wh, domain, domain ?: wh)
    }

    /** (ok, text): GET https://<server>/health must answer {"ok":true}. */
    fun health(server: String, proxyPort: Int?): Pair<Boolean, String> {
        val proxy = if (proxyPort != null && proxyPort > 0) Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", proxyPort)) else Proxy.NO_PROXY
        return try {
            val c = URL("https://$server/health").openConnection(proxy) as HttpURLConnection
            try {
                c.connectTimeout = 15000; c.readTimeout = 15000; c.setRequestProperty("User-Agent", "NetBridge")
                val code = c.responseCode
                if (code != 200) return false to "HTTP $code"
                val raw = c.inputStream.use { it.readBytes() }.toString(Charsets.UTF_8).take(2000)
                try { JSONObject(raw).optBoolean("ok", false) to raw.trim().take(120) } catch (_: Exception) { false to raw.trim().take(120).ifEmpty { "empty answer" } }
            } finally { c.disconnect() }
        } catch (e: Exception) { false to (e.message ?: "error").take(120) }
    }
}
