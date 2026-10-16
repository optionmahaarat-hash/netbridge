package com.netbridge.lite

import org.json.JSONArray
import org.json.JSONObject
import java.net.Inet4Address
import java.net.InetAddress
import java.util.concurrent.ConcurrentHashMap

/** Port of config_generator.py + bypass.py + routing.py. Needs Xray >= 26.7 (same core as the Windows app). */
object ConfigGen {
    const val CIPHERS =
        "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:" +
        "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:" +
        "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:" +
        "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256:TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256:" +
        "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA:TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA:" +
        "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256:TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256"
    const val ECH_PUBLIC = "cloudflare-ech.com"
    const val ECH_DEFAULT = "cloudflare-ech.com+https://1.1.1.1/dns-query"

    fun fmPattng() = JSONObject(
        """{"tcp":[{"type":"fragment","settings":{"packets":"tlshello","lengths":["0","104","1"],"delays":["0"],"maxSplit":"0"}},
        {"type":"fragment","settings":{"packets":"1-1","lengths":["114","1"],"delays":["1"],"maxSplit":"11"}}]}"""
    )
    fun fmStandard() = JSONObject(
        """{"tcp":[{"type":"fragment","settings":{"packets":"tlshello","length":"10-30","delay":"10-20","maxSplit":"0"}}]}"""
    )

    private fun echValue(v: String): String =
        if (v.trim().lowercase() in setOf("1", "true", "yes", "on", "auto")) ECH_DEFAULT else v.trim()

    // ---- the phone has no usable system DNS inside Xray's Go resolver: resolve the server name here, keep SNI/Host
    private val dnsCache = ConcurrentHashMap<String, String>()
    private fun resolve4(host: String): String? {
        dnsCache[host]?.let { return it.ifEmpty { null } }
        val ip = try {
            InetAddress.getAllByName(host).filterIsInstance<Inet4Address>().firstOrNull()?.hostAddress
        } catch (e: Exception) { null }
        dnsCache[host] = ip ?: ""
        return ip
    }
    fun forgetDns() = dnsCache.clear()

    private fun prep(p: P): P {
        val host = p.s("server")
        if (p.s("address_override").isNotEmpty() || isIp(host)) return p
        val ip = resolve4(host) ?: return p
        val q = p.copyP()
        q.put("address_override", ip)
        if (q.s("host").isEmpty() && q.s("network") in setOf("ws", "httpupgrade", "xhttp", "splithttp")) q.put("host", host)
        return q
    }

    private fun addr(p: P) = p.s("address_override").trim().ifEmpty { p.s("server") }

    private fun certPolicy(t: JSONObject, p: P) {
        if (p.s("pcs").isNotEmpty()) t.put("pinnedPeerCertSha256", p.s("pcs").replace(":", "").trim().lowercase())
        else if (p.optBoolean("insecure", false))
            throw IllegalStateException("Self-signed certificate that is not pinned (Xray 26.7 removed allowInsecure)")
    }

    private fun stream(p: P): JSONObject {
        val network = p.s("network").ifEmpty { "tcp" }
        val security = p.s("security")
        val s = JSONObject().put("network", network)
        if (security.isNotEmpty()) s.put("security", security)
        val path = WorkerExit.apply(p.s("path").ifEmpty { "/" }, p.s("worker_exit"))
        if (network == "ws") {
            val ws = JSONObject().put("path", path)
            if (p.s("host").isNotEmpty()) ws.put("headers", JSONObject().put("Host", p.s("host")))
            if (p.optInt("early_data", 0) != 0) {
                ws.put("maxEarlyData", p.optInt("early_data"))
                ws.put("earlyDataHeaderName", p.s("early_data_header").ifEmpty { "Sec-WebSocket-Protocol" })
            }
            s.put("wsSettings", ws)
        }
        if (security == "tls") {
            val t = JSONObject()
            val sni = p.s("sni").ifEmpty { if (p.s("address_override").isNotEmpty()) p.s("server") else "" }
            if (sni.isNotEmpty()) t.put("serverName", sni)
            if (p.s("fp").isNotEmpty()) t.put("fingerprint", p.s("fp"))
            if (p.s("alpn").isNotEmpty()) t.put("alpn", jarr(p.s("alpn").split(",").map { it.trim() }.filter { it.isNotEmpty() }))
            certPolicy(t, p)
            s.put("tlsSettings", t)
        } else if (security == "reality") {
            val r = jobj("serverName" to p.s("sni"), "fingerprint" to p.s("fp").ifEmpty { "chrome" },
                "publicKey" to p.s("pbk"), "shortId" to p.s("sid"))
            if (p.s("spx").isNotEmpty()) r.put("spiderX", p.s("spx"))
            s.put("realitySettings", r)
        }
        when (network) {
            "grpc" -> s.put("grpcSettings", JSONObject().put("serviceName", p.s("service_name")))
            "httpupgrade" -> {
                val h = JSONObject().put("path", path)
                if (p.s("host").isNotEmpty()) h.put("host", p.s("host"))
                s.put("httpupgradeSettings", h)
            }
            "xhttp", "splithttp" -> {
                s.put("network", "xhttp")
                val x = JSONObject().put("path", path)
                if (p.s("host").isNotEmpty()) x.put("host", p.s("host"))
                if (p.s("xmode").isNotEmpty()) x.put("mode", p.s("xmode"))
                s.put("xhttpSettings", x)
            }
        }
        return applyBypass(p, s)
    }

    private fun loadJson(v: String): JSONObject = JSONObject(v)

    private fun applyBypass(p: P, stream: JSONObject): JSONObject {
        val mode = p.s("bypass").ifEmpty { "off" }
        val tls = stream.optJSONObject("tlsSettings")
        if (mode == "off") {
            if (p.s("fm").isNotEmpty()) stream.put("finalmask", loadJson(p.s("fm")))
            if (tls != null && p.s("cs").isNotEmpty()) tls.put("cipherSuites", p.s("cs"))
            if (tls != null && p.s("ech").isNotEmpty()) tls.put("echConfigList", echValue(p.s("ech")))
            return stream
        }
        if (stream.optString("security") != "tls" || tls == null) throw IllegalStateException("Bypass needs a TLS config")
        tls.put("fingerprint", if (mode == "custom") p.s("fp").ifEmpty { "unsafe" } else "unsafe")
        if (mode == "ech") {
            tls.put("fingerprint", p.s("fp").ifEmpty { "chrome" })
            tls.put("echConfigList", echValue(p.s("ech").ifEmpty { "1" }))
            return stream
        }
        if (mode == "custom") {
            if (p.s("cs").isNotEmpty()) tls.put("cipherSuites", p.s("cs").trim().replace("\n", "").replace(" ", ""))
            if (p.s("fm").isNotEmpty()) stream.put("finalmask", loadJson(p.s("fm")))
        } else {
            // standard / pattng / any method added by the updatable preset file (see Presets.kt)
            val pr = Presets.get(mode) ?: throw IllegalStateException("Unknown bypass mode: $mode")
            tls.put("fingerprint", pr.optString("fingerprint", "unsafe"))
            val cs = pr.optString("cipherSuites", "")
            if (cs.isNotEmpty()) tls.put("cipherSuites", cs)
            pr.optJSONObject("finalmask")?.let { stream.put("finalmask", it) }
        }
        if (p.s("ech").isNotEmpty()) tls.put("echConfigList", echValue(p.s("ech")))
        return stream
    }

    private fun outbound(p0: P): JSONObject {
        val p = prep(p0)
        val port = p.optInt("port")
        val o: JSONObject = when (p.s("type")) {
            "vless" -> {
                val user = jobj("id" to p.s("uuid"), "encryption" to "none")
                if (p.s("flow").isNotEmpty()) user.put("flow", p.s("flow"))
                jobj("protocol" to "vless", "settings" to jobj("vnext" to jarr(listOf(
                    jobj("address" to addr(p), "port" to port, "users" to jarr(listOf(user)))))),
                    "streamSettings" to stream(p))
            }
            "vmess" -> jobj("protocol" to "vmess", "settings" to jobj("vnext" to jarr(listOf(
                jobj("address" to addr(p), "port" to port,
                    "users" to jarr(listOf(jobj("id" to p.s("uuid"), "alterId" to 0, "security" to "auto"))))))),
                "streamSettings" to stream(p))
            "trojan" -> jobj("protocol" to "trojan", "settings" to jobj("servers" to jarr(listOf(
                jobj("address" to addr(p), "port" to port, "password" to p.s("password"))))),
                "streamSettings" to stream(p))
            "shadowsocks" -> jobj("protocol" to "shadowsocks", "settings" to jobj("servers" to jarr(listOf(
                jobj("address" to addr(p), "port" to port, "method" to p.s("method"), "password" to p.s("password"))))))
            else -> throw IllegalStateException("Unsupported protocol")
        }
        val ss = o.optJSONObject("streamSettings") ?: JSONObject().also { o.put("streamSettings", it) }
        val so = ss.optJSONObject("sockopt") ?: JSONObject().also { ss.put("sockopt", it) }
        if (!addr(p).contains(':')) so.put("domainStrategy", "UseIPv4")     // a name is resolved to IPv4; an IPv6 literal is used as it is
        return o
    }

    private fun chainHop(p: P, all: List<P>?): P? {
        val key = p.s("chain_key")
        if (key.isEmpty() || all == null) return null
        return all.firstOrNull { profileKey(it) == key && profileKey(it) != profileKey(p) }
    }

    /** tun=true: config for the VPN (socks+http inbound, DNS handling, QUIC blocked). tun=false: tiny test config. */
    fun generate(
        profiles: List<P>, mode: String = "manual", socksPort: Int = 0, httpPort: Int = 0,
        iran: Boolean = false, all: List<P>? = null, tun: Boolean = false, loglevel: String = "warning"
    ): JSONObject {
        require(profiles.isNotEmpty()) { "No profiles" }
        val use = if (mode != "auto") profiles.take(1) else profiles
        val outs = JSONArray(); val hops = ArrayList<JSONObject>()
        use.forEachIndexed { i, p ->
            val o = outbound(p); o.put("tag", "p$i")
            val hop = chainHop(p, all)
            if (hop != null) {
                val h = outbound(hop); h.put("tag", "hop$i")
                o.getJSONObject("streamSettings").getJSONObject("sockopt").put("dialerProxy", "hop$i")
                hops.add(h)
            }
            outs.put(o)
        }
        hops.forEach { outs.put(it) }
        outs.put(jobj("protocol" to "freedom", "tag" to "direct", "settings" to jobj("domainStrategy" to "UseIPv4")))
        outs.put(jobj("protocol" to "blackhole", "tag" to "block"))
        if (tun) outs.put(jobj("protocol" to "dns", "tag" to "dns-out"))

        val auto = mode == "auto" && use.size > 1
        val rules = JSONArray()
        if (tun) {
            // QUIC (udp/443) cannot go through most servers: block it so apps fall back to TCP at once
            rules.put(jobj("type" to "field", "network" to "udp", "port" to "443", "outboundTag" to "block"))
            // names asked by apps are resolved by Xray itself (through the tunnel), not by the local network
            rules.put(jobj("type" to "field", "inboundTag" to jarr(listOf("socks-in", "http-in")), "port" to "53", "outboundTag" to "dns-out"))
        }
        rules.put(jobj("type" to "field", "ip" to jarr(listOf("geoip:private")), "outboundTag" to "direct"))
        if (iran) {
            rules.put(jobj("type" to "field", "domain" to jarr(listOf("geosite:category-ir", "regexp:\\.ir$")), "outboundTag" to "direct"))
            rules.put(jobj("type" to "field", "ip" to jarr(listOf("geoip:ir")), "outboundTag" to "direct"))
        }
        val routing = jobj("domainStrategy" to "AsIs", "rules" to rules)
        val cfg = JSONObject().put("log", JSONObject().put("loglevel", loglevel))
        if (tun) cfg.put("dns", jobj("servers" to jarr(listOf("https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query")),
            "queryStrategy" to "UseIPv4"))
        if (auto) {
            val sel = use.indices.map { "p$it" }
            routing.put("balancers", jarr(listOf(jobj("tag" to "auto", "selector" to jarr(sel),
                "strategy" to jobj("type" to "leastPing"), "fallbackTag" to "p0"))))
            rules.put(jobj("type" to "field", "network" to "tcp,udp", "balancerTag" to "auto"))
            cfg.put("observatory", jobj("subjectSelector" to jarr(sel), "probeInterval" to "30s",
                "probeUrl" to "https://www.gstatic.com/generate_204"))
        }
        cfg.put("routing", routing)
        // test configs behave exactly like the Windows app (routeOnly = true); only the real VPN overrides the destination
        val sniff = jobj("enabled" to true, "destOverride" to jarr(listOf("http", "tls")), "routeOnly" to !tun)
        val inb = JSONArray()
        if (socksPort > 0) inb.put(jobj("tag" to "socks-in", "listen" to "127.0.0.1", "port" to socksPort, "protocol" to "socks",
            "settings" to jobj("udp" to true), "sniffing" to sniff))
        if (httpPort > 0) inb.put(jobj("tag" to "http-in", "listen" to "127.0.0.1", "port" to httpPort, "protocol" to "http",
            "settings" to JSONObject(), "sniffing" to sniff))
        cfg.put("inbounds", inb)
        cfg.put("outbounds", outs)
        return cfg
    }
}
