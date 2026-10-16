package com.netbridge.lite

import org.json.JSONArray
import org.json.JSONObject
import java.net.InetAddress
import java.net.ServerSocket

/** A server profile is a plain JSON object (same field names as the Windows app: type, server, port, uuid, network ...). */
typealias P = JSONObject

fun P.s(k: String, d: String = ""): String = if (isNull(k)) d else optString(k, d)
fun P.copyP(): P = JSONObject(toString())

fun jarr(items: Iterable<Any?>): JSONArray = JSONArray().also { a -> items.forEach { a.put(it) } }
fun jobj(vararg kv: Pair<String, Any?>): JSONObject = JSONObject().also { o -> kv.forEach { o.put(it.first, it.second) } }

fun profileKey(p: P): String =
    listOf("type", "server", "port", "uuid", "password").joinToString("|") { p.opt(it)?.toString() ?: "" }

fun isTls(p: P): Boolean = p.s("security").lowercase() == "tls"

fun freePort(): Int = ServerSocket(0, 0, InetAddress.getByName("127.0.0.1")).use { it.localPort }

private val IPV4 = Regex("""^\d{1,3}(\.\d{1,3}){3}$""")
fun isIp(h: String) = IPV4.matches(h) || h.contains(':')


/** edgetunnel-style exit carried in the WebSocket path: "proxyip=1.2.3.4:443", "socks5=user:pass@host:1080" or "http=host:8080".
 *  Same rules as app/core/worker_exit.py: strict characters, an invalid value leaves the path alone, the profile's choice replaces any in the path. */
object WorkerExit {
    private val KEYS = listOf("proxyip", "socks5", "http")
    private val VALUE = Regex("^[A-Za-z0-9._:@\\-\\[\\]%+]{1,200}$")

    /** "key=value" or null when empty/invalid */
    fun normalize(spec: String?): String? {
        val t = (spec ?: "").trim().trimStart('/', '?', '&')
        val i = t.indexOf('=')
        if (i < 0) return null
        val key = t.substring(0, i).trim().lowercase(); val v = t.substring(i + 1)
        if (key !in KEYS || !VALUE.matches(v)) return null
        return "$key=$v"
    }

    fun apply(path: String, spec: String?): String {
        val p = path.ifEmpty { "/" }
        val s = normalize(spec) ?: return p
        val q = p.indexOf('?')
        val base0 = if (q >= 0) p.substring(0, q) else p
        val query = if (q >= 0) p.substring(q + 1) else ""
        val keep = query.split("&").filter { it.isNotEmpty() && it.substringBefore("=").lowercase() !in KEYS }
        val base = base0.replace(Regex("/(?:proxyip|socks5|http)=[^/?]*"), "").ifEmpty { "/" }
        return base + "?" + (keep + s).joinToString("&")
    }
}
