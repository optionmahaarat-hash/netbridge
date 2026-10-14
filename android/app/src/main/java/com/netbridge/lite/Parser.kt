package com.netbridge.lite

import java.net.URLDecoder
import java.util.Base64

/** share links (vless / vmess / trojan / ss) and subscriptions -> profiles. Port of the Windows app's parsers. */
object Parser {
    private val SS_METHODS = setOf(
        "aes-128-gcm", "aes-256-gcm", "chacha20-poly1305", "chacha20-ietf-poly1305",
        "xchacha20-poly1305", "xchacha20-ietf-poly1305",
        "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305"
    )
    private val UUID_RE = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    private fun unq(s: String) = try { URLDecoder.decode(s.replace("+", "%2B"), "UTF-8") } catch (e: Exception) { s }
    private fun qdec(s: String) = try { URLDecoder.decode(s, "UTF-8") } catch (e: Exception) { s }

    fun b64(s: String): String {
        val t = s.trim().replace('-', '+').replace('_', '/').filter { !it.isWhitespace() }
        val padded = t + "=".repeat((4 - t.length % 4) % 4)
        return String(Base64.getDecoder().decode(padded), Charsets.UTF_8)
    }

    private class U(val scheme: String, val user: String, val host: String, val port: Int, val q: Map<String, String>, val frag: String)

    private fun split(text: String): U {
        val t = text.trim()
        val scheme = t.substringBefore("://").lowercase()
        var rest = t.substringAfter("://")
        val frag = if ('#' in rest) rest.substringAfter('#') else ""
        rest = rest.substringBefore('#')
        val query = if ('?' in rest) rest.substringAfter('?') else ""
        rest = rest.substringBefore('?')
        val auth = rest.substringBefore('/')
        val user = if ('@' in auth) auth.substringBeforeLast('@') else ""
        val hp = auth.substringAfterLast('@')
        val host: String
        var port = -1
        if (hp.startsWith("[")) {
            host = hp.substring(1, hp.indexOf(']').coerceAtLeast(1))
            port = hp.substringAfter("]:", "").toIntOrNull() ?: -1
        } else if (':' in hp) {
            host = hp.substringBeforeLast(':'); port = hp.substringAfterLast(':').toIntOrNull() ?: -1
        } else host = hp
        val q = LinkedHashMap<String, String>()
        for (kv in query.split('&')) {
            if (kv.isEmpty()) continue
            val k = qdec(kv.substringBefore('=')); val v = qdec(kv.substringAfter('=', ""))
            if (k !in q) q[k] = v
        }
        return U(scheme, user, host, port, q, frag)
    }

    private fun extra(q: Map<String, String>, p: P) {
        for ((src, dst) in listOf("cs" to "cs", "fm" to "fm", "pbk" to "pbk", "sid" to "sid", "spx" to "spx",
            "serviceName" to "service_name", "pcs" to "pcs", "ech" to "ech", "mode" to "xmode")) {
            q[src]?.takeIf { it.isNotEmpty() }?.let { p.put(dst, it) }
        }
        if (listOf("insecure", "allowInsecure", "allow_insecure").any { q[it] == "1" }) p.put("insecure", true)
        if (p.s("cs").isNotEmpty() || p.s("fm").isNotEmpty()) p.put("bypass", "custom")
    }

    private fun name(u: U) = if (u.frag.isNotEmpty()) unq(u.frag) else "${u.host}:${u.port}"

    private fun vless(t: String): P {
        val u = split(t)
        val id = unq(u.user)
        require(UUID_RE.matches(id)) { "Invalid VLESS UUID" }
        val q = u.q
        val p = jobj(
            "name" to name(u), "type" to "vless", "server" to u.host, "port" to u.port, "uuid" to id,
            "network" to (q["type"] ?: "tcp"), "security" to (q["security"] ?: ""), "sni" to (q["sni"] ?: ""),
            "host" to (q["host"] ?: ""), "path" to (q["path"] ?: ""), "fp" to (q["fp"] ?: ""),
            "alpn" to (q["alpn"] ?: ""), "flow" to (q["flow"] ?: "")
        )
        extra(q, p); return p
    }

    private fun trojan(t: String): P {
        val u = split(t)
        val q = u.q
        val p = jobj(
            "name" to name(u), "type" to "trojan", "server" to u.host, "port" to (if (u.port > 0) u.port else 443),
            "password" to unq(u.user), "network" to (q["type"] ?: "tcp"), "security" to (q["security"] ?: "tls"),
            "sni" to (q["sni"] ?: ""), "host" to (q["host"] ?: ""), "path" to (q["path"] ?: ""), "fp" to (q["fp"] ?: "")
        )
        extra(q, p); return p
    }

    private fun vmess(t: String): P {
        val d = org.json.JSONObject(b64(t.trim().substring("vmess://".length)))
        val net = d.optString("net", "tcp").ifEmpty { "tcp" }
        val p = jobj(
            "name" to d.optString("ps", "").ifEmpty { "${d.optString("add")}:${d.opt("port")}" },
            "type" to "vmess", "server" to d.optString("add", "").trim(),
            "port" to (d.opt("port")?.toString()?.trim()?.toIntOrNull() ?: 0),
            "uuid" to d.optString("id", ""), "network" to net, "security" to d.optString("tls", ""),
            "sni" to d.optString("sni", ""), "host" to d.optString("host", ""), "path" to d.optString("path", ""),
            "fp" to d.optString("fp", ""), "alpn" to d.optString("alpn", "")
        )
        if (net == "grpc") p.put("service_name", d.optString("path", ""))
        else if ((net == "xhttp" || net == "splithttp") && d.optString("mode").isNotEmpty()) p.put("xmode", d.optString("mode"))
        return p
    }

    private fun fixSs(method: String, password: String): Pair<String, String> {
        if (method in setOf("none", "plain", "")) {
            try {
                val txt = b64(password)
                val m = txt.substringBefore(':'); val pw = txt.substringAfter(':', "")
                if (pw.isNotEmpty() && m in SS_METHODS) return m to pw
            } catch (_: Exception) { }
        }
        return method to password
    }

    private fun ss(t: String): P {
        val u = split(t)
        if (u.user.isEmpty() && u.host.isNotEmpty()) {            // legacy: everything inside the base64 part
            try {
                val legacy = b64(unq(u.host))
                val cred = legacy.substringBeforeLast('@'); val hostport = legacy.substringAfterLast('@')
                val host = hostport.substringBeforeLast(':'); val port = hostport.substringAfterLast(':')
                val method = cred.substringBefore(':'); val password = cred.substringAfter(':', "")
                if (host.isNotEmpty() && port.all { it.isDigit() } && port.isNotEmpty() && password.isNotEmpty()) {
                    val (m, pw) = fixSs(method, password)
                    return jobj("name" to (if (u.frag.isNotEmpty()) unq(u.frag) else "$host:$port"), "type" to "shadowsocks",
                        "server" to host.trim('[', ']'), "port" to port.toInt(), "method" to m, "password" to pw)
                }
            } catch (_: Exception) { }
        }
        var user = unq(u.user)
        if (':' !in user) user = try { b64(user) } catch (e: Exception) { user }
        require(':' in user) { "Invalid Shadowsocks credentials" }
        val (m, pw) = fixSs(user.substringBefore(':'), user.substringAfter(':'))
        return jobj("name" to name(u), "type" to "shadowsocks", "server" to u.host,
            "port" to (if (u.port > 0) u.port else 8388), "method" to m, "password" to pw)
    }

    fun parseOne(text: String): P {
        val t = text.trim()
        return when {
            t.startsWith("vless://", true) -> vless(t)
            t.startsWith("vmess://", true) -> vmess(t)
            t.startsWith("trojan://", true) -> trojan(t)
            t.startsWith("ss://", true) -> ss(t)
            else -> throw IllegalArgumentException("Unsupported config URI")
        }
    }

    fun valid(p: P): Boolean {
        if (p.s("name").isEmpty() || p.s("server").isEmpty()) return false
        val port = p.optInt("port", 0)
        if (port !in 1..65535) return false
        if (p.s("type") !in setOf("vless", "vmess", "trojan", "shadowsocks")) return false
        if (p.s("server").trim() in setOf("0.0.0.0", "127.0.0.1", "localhost")) return false
        if (p.s("type") == "shadowsocks" && p.s("method") !in SS_METHODS) return false
        return true
    }

    /** -> (valid profiles, number of lines that could not be read) */
    fun parseMany(text: String): Pair<List<P>, Int> {
        var lines = text.replace("\r", "").split("\n").map { it.trim() }.filter { it.isNotEmpty() && !it.startsWith("#") }
        if (lines.isNotEmpty() && lines.none { "://" in it }) {         // base64 subscription body
            try {
                val d = b64(lines.joinToString(""))
                if ("://" in d) lines = d.lines().map { it.trim() }.filter { it.isNotEmpty() && !it.startsWith("#") }
            } catch (_: Exception) { }
        }
        val out = ArrayList<P>(); var bad = 0
        for (l in lines) {
            try { val p = parseOne(l); if (valid(p)) out.add(p) else bad++ } catch (e: Exception) { bad++ }
        }
        return out to bad
    }
}
