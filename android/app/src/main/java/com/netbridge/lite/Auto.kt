package com.netbridge.lite

import android.content.Context
import kotlinx.coroutines.*
import org.json.JSONObject
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.io.File
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL
import java.util.Base64
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.coroutineContext

/**
 * The AUTO search of the Windows app: every server x every bypass method is tried in a private Xray with REAL requests
 * (YouTube, Instagram, Google); the first method that works wins and is saved into the server.
 * Phase 2 = clean-Cloudflare-IP scan (ported from app/core/ipscan.py).
 */
object Auto {
    class Win(val p: P, val v: JSONObject, val ms: Int)
    class Result(val winners: List<Pair<P, Int>>, val relaxed: Boolean, val plainOnly: Boolean)

    private val SITES = listOf(
        Triple("YouTube", "https://www.youtube.com/generate_204", { c: Int -> c == 204 }),
        Triple("Instagram", "https://www.instagram.com/", { c: Int -> c in 200..399 }),
        Triple("Google", "https://www.google.com/generate_204", { c: Int -> c == 204 })
    )
    // same list as the Windows app (names + IPs): a network that blocks the bare IPs often still lets the names through
    private val DOH = listOf(
        "https://dns.google/dns-query", "https://1.1.1.1/dns-query", "https://cloudflare-dns.com/dns-query",
        "https://8.8.8.8/dns-query", "https://dns.quad9.net/dns-query", "https://9.9.9.9/dns-query"
    )
    // used for ECH when the quick DoH check found nothing (the check can be wrong on a phone): still TRY it
    private val DOH_FALLBACK = listOf("https://8.8.8.8/dns-query", "https://1.1.1.1/dns-query")
    private val live: MutableSet<Process> = ConcurrentHashMap.newKeySet<Process>()

    private val failLogged = java.util.concurrent.atomic.AtomicInteger()
    private fun why(p: P, msg: String) {
        if (failLogged.incrementAndGet() <= 40) VpnSvc.log("FAIL " + p.s("name").take(28) + " [" + p.s("bypass") + "]: " + msg)
    }
    private fun errText(e: Throwable) = e.javaClass.simpleName + ": " + (e.message ?: "").take(120)

    fun killAll() { live.toList().forEach { it.destroyForcibly() } }

    // ---------------- Phase 2: clean Cloudflare IP scan (port of app/core/ipscan.py) ----------------
    private val CF_PORTS = setOf(443, 8443, 2053, 2083, 2087, 2096)
    private val CF_RANGES = listOf(
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
        "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"
    )

    private fun looksCloudflare(p: P) = p.s("security").lowercase() == "tls" && p.optInt("port", 0) in CF_PORTS

    // Cloudflare's published IPv6 ranges (same list as app/core/ipscan.py)
    private val CF_RANGES6 = listOf("2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32")

    private fun ipToLong(a: String) = a.split('.').fold(0L) { acc, x -> acc * 256 + x.toLong() }
    private fun longToIp(v: Long) = "${(v shr 24) and 255}.${(v shr 16) and 255}.${(v shr 8) and 255}.${v and 255}"

    /** n random IPv4s spread over Cloudflare's ranges proportionally to their size */
    private fun sampleIps4(n: Int): List<String> {
        val nets = CF_RANGES.map { r -> val (a, b) = r.split('/'); Pair(ipToLong(a), 1L shl (32 - b.toInt())) }
        val total = nets.sumOf { it.second }
        val rnd = java.util.Random()
        val out = HashSet<String>(); var tries = 0
        while (out.size < n && tries < n * 20) {
            tries++
            var x = (rnd.nextDouble() * total).toLong()
            for ((base, size) in nets) {
                if (x < size) { out.add(longToIp(base + 1 + (rnd.nextDouble() * (size - 2)).toLong())); break }
                x -= size
            }
        }
        return out.toList()
    }

    private fun big16(v: java.math.BigInteger): ByteArray {
        val b = v.toByteArray(); val out = ByteArray(16); val len = minOf(b.size, 16)
        System.arraycopy(b, b.size - len, out, 16 - len, len)
        return out
    }

    /** n random IPv6s spread over Cloudflare's IPv6 ranges proportionally to their size */
    private fun sampleIps6(n: Int): List<String> {
        val nets = CF_RANGES6.map { r ->
            val (a, b) = r.split('/')
            Pair(java.math.BigInteger(1, java.net.InetAddress.getByName(a).address), java.math.BigInteger.ONE.shiftLeft(128 - b.toInt()))
        }
        val total = nets.fold(java.math.BigInteger.ZERO) { acc, x -> acc + x.second }
        val rnd = java.util.Random()
        val out = HashSet<String>(); var tries = 0
        while (out.size < n && tries < n * 20) {
            tries++
            var x = java.math.BigInteger(total.bitLength() + 8, rnd).mod(total)
            for ((base, size) in nets) {
                if (x < size) {
                    val host = java.math.BigInteger(size.bitLength() + 8, rnd).mod(size - java.math.BigInteger.TWO) + java.math.BigInteger.ONE
                    out.add(java.net.InetAddress.getByAddress(big16(base + host)).hostAddress ?: break)
                    break
                }
                x -= size
            }
        }
        return out.toList()
    }

    /** IPv4 only, or (when the phone has an IPv6 route) half IPv4 / half IPv6: an IPv6 range is billions of times bigger, so by size alone it would crowd IPv4 out */
    private fun sampleIps(n: Int, v6: Boolean): List<String> =
        if (v6) sampleIps4(n - n / 2) + sampleIps6(n / 2) else sampleIps4(n)

    /** true if this phone has an IPv6 route to the internet (nothing is sent: a UDP connect() only asks the routing table) */
    private fun hasIpv6(): Boolean = try {
        java.net.DatagramSocket().use { s ->
            s.connect(InetSocketAddress(java.net.InetAddress.getByName("2606:4700:4700::1111"), 53)); true
        }
    } catch (e: Exception) { false }

    @Volatile private var ipv6Route = false
    private val v6Cache = ConcurrentHashMap<String, String>()

    /** first IPv6 address of a server NAME (cached; null if it has none or is already an IP) */
    private fun resolve6(host: String): String? {
        if (host.isEmpty() || isIp(host)) return null
        v6Cache[host]?.let { return it.ifEmpty { null } }
        val ip = try {
            java.net.InetAddress.getAllByName(host).filterIsInstance<java.net.Inet6Address>().firstOrNull()?.hostAddress?.substringBefore('%')
        } catch (e: Exception) { null }
        v6Cache[host] = ip ?: ""
        return ip
    }

    private val TRUST_ALL = object : javax.net.ssl.X509TrustManager {
        override fun checkClientTrusted(c: Array<java.security.cert.X509Certificate>?, a: String?) {}
        override fun checkServerTrusted(c: Array<java.security.cert.X509Certificate>?, a: String?) {}
        override fun getAcceptedIssuers(): Array<java.security.cert.X509Certificate> = arrayOf()
    }

    /** TCP + TLS (with the profile's SNI) + GET /cdn-cgi/trace. Returns ms, or null if this IP is not reachable. */
    private fun probeIp(ip: String, port: Int, sni: String, timeout: Int = 3000): Int? {
        val t0 = System.nanoTime()
        val raw = Socket()
        return try {
            raw.connect(InetSocketAddress(ip, port), timeout); raw.soTimeout = timeout
            val ctx = javax.net.ssl.SSLContext.getInstance("TLS")
            ctx.init(null, arrayOf<javax.net.ssl.TrustManager>(TRUST_ALL), null)
            val host = sni.ifEmpty { ip }
            val ss = ctx.socketFactory.createSocket(raw, host, port, true) as javax.net.ssl.SSLSocket
            ss.soTimeout = timeout
            ss.startHandshake()
            ss.outputStream.write("GET /cdn-cgi/trace HTTP/1.1\r\nHost: $host\r\nUser-Agent: NetBridge\r\nConnection: close\r\n\r\n".toByteArray())
            ss.outputStream.flush()
            val buf = java.io.ByteArrayOutputStream(); val chunk = ByteArray(2048)
            while (buf.size() < 4096) { val n = ss.inputStream.read(chunk); if (n <= 0) break; buf.write(chunk, 0, n) }
            val ms = ((System.nanoTime() - t0) / 1_000_000).toInt()
            val text = buf.toString("UTF-8")
            if (text.substringBefore("\r\n").contains(" 200") && text.contains("colo=")) ms else null
        } catch (e: Exception) { null } finally { try { raw.close() } catch (_: Exception) { } }
    }

    private suspend fun scanIps(ips: List<String>, port: Int, sni: String): List<Pair<Int, String>> = coroutineScope {
        val sem = Semaphore(60)
        ips.map { ip ->
            async(Dispatchers.IO) { sem.withPermit { val ms = probeIp(ip, port, sni) ?: probeIp(ip, port, sni); if (ms != null) ms to ip else null } }
        }.awaitAll().filterNotNull()
    }

    private fun dnsQuery(name: String): ByteArray {
        val b = java.io.ByteArrayOutputStream()
        b.write(byteArrayOf(0x12, 0x34, 0x01, 0x00, 0, 1, 0, 0, 0, 0, 0, 0))
        for (part in name.split('.')) { b.write(part.length); b.write(part.toByteArray()) }
        b.write(0); b.write(byteArrayOf(0, 65, 0, 1))
        return b.toByteArray()
    }

    /** null = works, otherwise the reason (written to the report: the old code threw it away) */
    private fun dohProblem(url: String): String? = try {
        val q = Base64.getUrlEncoder().withoutPadding().encodeToString(dnsQuery(ConfigGen.ECH_PUBLIC))
        val c = URL("$url?dns=$q").openConnection(java.net.Proxy.NO_PROXY) as java.net.HttpURLConnection
        c.connectTimeout = 4000; c.readTimeout = 4000
        c.setRequestProperty("Accept", "application/dns-message")
        c.setRequestProperty("User-Agent", "NetBridge")
        try {
            val code = c.responseCode
            if (code != 200) "HTTP $code"
            else if (c.inputStream.use { it.readBytes().size } > 12) null else "empty answer"
        } finally { c.disconnect() }
    } catch (e: Exception) { errText(e) }

    private suspend fun reachableDoh(log: (String) -> Unit): List<String> = coroutineScope {
        val res = DOH.map { u -> async(Dispatchers.IO) { u to dohProblem(u) } }.awaitAll()
        res.forEach { (u, why) -> if (why != null) log("DoH $u: $why") }
        res.filter { it.second == null }.map { it.first }
    }

    /** the method the profile already carries (saved by an earlier AUTO or imported from the Windows app) */
    private fun savedVariant(p: P): JSONObject? {
        val b = p.s("bypass")
        if (b.isEmpty() || b == "off") return null
        val v = JSONObject().put("bypass", b)
        if (p.s("ech").isNotEmpty()) v.put("ech", p.s("ech"))
        return v
    }

    private fun variants(p: P, doh: List<String>): List<JSONObject> {
        if (!isTls(p)) return listOf(JSONObject().put("bypass", "off"))
        val out = ArrayList<JSONObject>()
        savedVariant(p)?.let { out.add(it) }                       // what worked on the PC goes first
        out.add(JSONObject().put("bypass", "off"))
        for (n in Presets.autoNames()) out.add(JSONObject().put("bypass", n))     // pattng, standard + any new method of the preset file
        // ECH is ALWAYS tried: with the DoH servers that answered, or (if none did) with the two common ones
        for (u in (if (doh.isNotEmpty()) doh else DOH_FALLBACK).take(2))
            out.add(JSONObject().put("bypass", "ech").put("ech", "${ConfigGen.ECH_PUBLIC}+$u"))
        // IPv6 entry points go LAST (the name is resolved later, in the worker; no AAAA record = variant skipped)
        if (ipv6Route && p.s("address_override").isEmpty() && !isIp(p.s("server"))) {
            out.add(JSONObject().put("bypass", "off").put("ip6", true))
            Presets.autoNames().firstOrNull()?.let { out.add(JSONObject().put("bypass", it).put("ip6", true)) }
        }
        val seen = HashSet<String>()
        return out.filter { seen.add(it.toString()) }
    }

    /** plain facts about this phone's network, written once into the report */
    private fun diagnose(tls: List<P>, log: (String) -> Unit) {
        try {
            log("diag: device time " + java.util.Date() + " tz=" + java.util.TimeZone.getDefault().id)
            val seen = HashSet<String>()
            for (p in tls) {
                val host = p.s("address_override").ifEmpty { p.s("server") }
                val port = p.optInt("port", 443)
                if (host.isEmpty() || !seen.add("$host:$port")) continue
                if (seen.size > 4) break
                val t0 = System.nanoTime()
                val r = try {
                    val ip = java.net.InetAddress.getAllByName(host).filterIsInstance<java.net.Inet4Address>().firstOrNull()?.hostAddress ?: "no-ipv4"
                    try { Socket().use { it.connect(InetSocketAddress(ip, port), 3000) }; "$ip tcp-ok " + ((System.nanoTime() - t0) / 1_000_000) + "ms" }
                    catch (e: Exception) { "$ip tcp-FAIL " + errText(e) }
                } catch (e: Exception) { "dns-FAIL " + errText(e) }
                log("diag: $host:$port -> $r")
            }
        } catch (e: Exception) { log("diag failed: " + errText(e)) }
    }

    private fun with(p: P, v: JSONObject): P {
        val q = p.copyP(); q.remove("ech")
        for (k in v.keys()) { if (k != "ip6") q.put(k, v.get(k)) }
        if (v.optBoolean("ip6")) resolve6(p.s("server"))?.let { ip ->
            q.put("address_override", ip)
            if (q.s("host").isEmpty() && q.s("network") in setOf("ws", "httpupgrade", "xhttp", "splithttp")) q.put("host", p.s("server"))
        }
        return q
    }

    private fun waitPort(port: Int, ms: Long, proc: Process): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) {
            if (!proc.isAlive) return false
            try { Socket().use { it.connect(InetSocketAddress("127.0.0.1", port), 200); return true } } catch (_: Exception) { }
            Thread.sleep(100)
        }
        return false
    }

    private fun isTimeout(e: Exception) = e is java.net.SocketTimeoutException || (e.message ?: "").contains("timed out", true)

    /** one server+method in its own Xray: ms, or -1. strict = YouTube/Instagram/Google must open too. */
    private suspend fun testOne(ctx: Context, p: P, all: List<P>, strict: Boolean): Int {
        val port = freePort()
        val cfg = File(ctx.cacheDir, "t_$port.json")
        var proc: Process? = null
        val xlog = java.util.Collections.synchronizedList(ArrayList<String>())
        // only the useful lines: skip the "deprecated" warnings and the config-reading line that filled the old report
        fun tail() = synchronized(xlog) {
            xlog.filter { !it.contains("deprecated") && !it.contains("Reading config") && !it.contains("started") }
                .takeLast(3).joinToString(" | ").take(400)
        }
        try {
            withContext(Dispatchers.IO) {
                // loglevel "warning" (was "none"): the real reason ("failed to dial ...") must reach the report
                cfg.writeText(ConfigGen.generate(listOf(p), "manual", 0, port, false, all, false, "warning").toString())
                proc = XrayProc.start(ctx, cfg) { xlog.add(it) }; live.add(proc!!)
            }
            val pr = proc!!
            if (!withContext(Dispatchers.IO) { waitPort(port, 4000, pr) }) { why(p, "Xray did not start: " + tail()); return -1 }
            var best: Int? = null; var ok = 0; var tries = 0; var lastErr = ""; var timeouts = 0
            while (ok < 2 && tries < 4) {
                coroutineContext.ensureActive(); tries++
                try {
                    val ms = withContext(Dispatchers.IO) { Net.fetchVia(port, "http://www.gstatic.com/generate_204", 8000).second }
                    best = if (best == null) ms else minOf(best, ms); ok++
                } catch (e: CancellationException) { throw e
                } catch (e: Exception) {
                    lastErr = errText(e)
                    if (isTimeout(e) && ++timeouts >= 2) break        // one slow answer is not a dead server: try once more
                    if (!isTimeout(e)) delay(300)
                }
            }
            if (best == null) { why(p, "no reply through server: " + lastErr + " | xray: " + tail()); return -1 }
            if (!strict) return best
            val siteErr = java.util.concurrent.ConcurrentHashMap<String, String>()
            val res = coroutineScope {
                SITES.map { (name, url, accept) ->
                    async(Dispatchers.IO) {
                        try { val (c, ms) = Net.fetchVia(port, url, 12000); if (accept(c)) maxOf(ms, 1) else { siteErr[name] = "HTTP $c"; -1 } }
                        catch (e: Exception) { siteErr[name] = errText(e); -1 }
                    }
                }.awaitAll()
            }
            if (res.all { it >= 0 }) {
                // the ~6-packet upload limit: a small GET passes, a 50 KB request body stalls
                try { withContext(Dispatchers.IO) { Net.uploadVia(port) } }
                catch (e: CancellationException) { throw e }
                catch (e: Exception) { why(p, "upload-limited: sites opened but a 50 KB upload failed (" + errText(e) + ")"); return -1 }
                return res.sum() / res.size
            }
            why(p, "sites " + SITES.mapIndexed { i, t -> t.first + "=" + res[i] + (siteErr[t.first]?.let { " ($it)" } ?: "") }.joinToString(" ") +
                " | xray: " + tail())
            return -1
        } catch (e: CancellationException) { throw e
        } catch (e: Exception) { why(p, "exception " + e); return -1
        } finally {
            proc?.let { live.remove(it); XrayProc.stop(it) }
            cfg.delete()
        }
    }

    private class State(val want: Int, val tlsOnly: Boolean, val onProgress: (Int, Int) -> Unit, var total: Int) {
        val wins = java.util.Collections.synchronizedList(ArrayList<Win>())
        val done = java.util.concurrent.atomic.AtomicInteger()
        fun count() = synchronized(wins) { wins.count { !tlsOnly || isTls(it.p) } }
    }

    private suspend fun runPhase(ctx: Context, items: List<Pair<P, List<JSONObject>>>, all: List<P>, st: State, workers: Int, strict: Boolean) = coroutineScope {
        val sem = Semaphore(workers)
        st.done.set(0); st.total = items.size; st.onProgress(0, items.size)
        items.map { (p, vs) ->
            launch(Dispatchers.Default) {
                sem.withPermit {
                    for (v in vs) {
                        if (!isActive || st.count() >= st.want) break
                        if (v.optBoolean("ip6") && withContext(Dispatchers.IO) { resolve6(p.s("server")) } == null) continue
                        val ms = testOne(ctx, with(p, v), all, strict)
                        if (ms >= 0) { st.wins.add(Win(p, v, ms)); break }
                    }
                    st.onProgress(st.done.incrementAndGet(), items.size)
                }
            }
        }.joinAll()
    }

    /** Phase 2 racing: a group holds the SAME method on different clean IPs. Groups are tried in order; inside a group
     *  all IPs run at the same time and the fastest working one wins. */
    private suspend fun runRace(ctx: Context, items: List<Pair<P, List<List<JSONObject>>>>, all: List<P>, st: State, workers: Int) = coroutineScope {
        val sem = Semaphore(workers)
        st.done.set(0); st.total = items.size; st.onProgress(0, items.size)
        items.map { (p, groups) ->
            launch(Dispatchers.Default) {
                sem.withPermit {
                    for (g in groups) {
                        if (!isActive || st.count() >= st.want) break
                        val res = coroutineScope {
                            g.map { v -> async { v to testOne(ctx, with(p, v), all, true) } }.awaitAll()
                        }
                        val best = res.filter { it.second >= 0 }.minByOrNull { it.second }
                        if (best != null) { st.wins.add(Win(p, best.first, best.second)); break }
                    }
                    st.onProgress(st.done.incrementAndGet(), items.size)
                }
            }
        }.joinAll()
    }

    suspend fun run(ctx: Context, profiles: List<P>, onProgress: (Int, Int) -> Unit, log: (String) -> Unit, want: Int = 4, workers: Int = 6): Result {
        // servers that already carry a working method (from the PC or an earlier run) first, then the fastest known
        val tls = profiles.filter { isTls(it) }.sortedBy { p ->
            val d = p.optInt("delay", -1)
            (if (savedVariant(p) != null) 0L else 20_000_000L) + (if (d >= 0) d else 10_000_000)
        }
        val plain = profiles.filter { !isTls(it) }
        ConfigGen.forgetDns(); failLogged.set(0)
        // geoip.dat / geosite.dat must exist BEFORE the first test Xray starts (its config has a geoip:private rule)
        try { withContext(Dispatchers.IO) { XrayProc.prepare(ctx) } } catch (e: Exception) { log("geo files: " + e) }
        withContext(Dispatchers.IO) { Presets.load(ctx); Presets.autoUpdate(ctx, log) }
        log("bypass values: version ${Presets.version}" + (if (Presets.errors.isEmpty()) "" else " | skipped: " + Presets.errors.take(3).joinToString("; ")))
        val doh = if (tls.isNotEmpty()) reachableDoh(log) else emptyList()
        log("ECH DoH reachable: " + (if (doh.isEmpty()) "none (ECH is still tried with 8.8.8.8 / 1.1.1.1)" else doh.joinToString()))
        v6Cache.clear()
        ipv6Route = tls.isNotEmpty() && withContext(Dispatchers.IO) { hasIpv6() }
        log("IPv6: " + (if (ipv6Route) "route available - IPv6 entry points are tried last" else "no IPv6 route here - skipped"))
        if (tls.isNotEmpty()) withContext(Dispatchers.IO) { diagnose(tls, log) }
        val all = ArrayList<Win>(); var relaxed = false; var plainOnly = false
        try {
            if (tls.isNotEmpty()) {
                log("Phase 1: ${tls.size} TLS server(s) x methods")
                val st = State(want, true, onProgress, tls.size)
                runPhase(ctx, tls.map { it to variants(it, doh) }, profiles, st, workers, true)
                all.addAll(st.wins)
            }
            if (all.none { isTls(it.p) } && tls.isNotEmpty() && coroutineContext.isActive) {
                val cf = tls.filter { looksCloudflare(it) }
                if (cf.isNotEmpty()) {
                    log("Phase 2: no TLS server worked - scanning clean Cloudflare IPs...")
                    val port = cf[0].optInt("port", 443)
                    val sni = cf[0].s("sni").ifEmpty { cf[0].s("host") }.ifEmpty { cf[0].s("server") }
                    val found = scanIps(sampleIps(300, ipv6Route), port, sni)
                    val ips = found.sortedBy { it.first }.take(3).map { it.second }
                    log("Clean IPs found: " + (if (ips.isEmpty()) "none" else ips.joinToString()))
                    if (ips.size > 1) log("racing the best ${ips.size} IPs per method")
                    if (ips.isNotEmpty() && coroutineContext.isActive) {
                        val st = State(want, true, onProgress, 0)
                        val items = cf.take(20).map { p ->
                            val lists = ips.map { ip -> variants(p, doh).filter { !it.optBoolean("ip6") }.map { v -> JSONObject(v.toString()).put("address_override", ip) } }
                            p to (0 until (lists.minOfOrNull { it.size } ?: 0)).map { i -> lists.map { it[i] } }
                        }
                        runRace(ctx, items, profiles, st, maxOf(2, workers / 3))
                        all.addAll(st.wins)
                    }
                }
            }
            if (all.none { isTls(it.p) } && plain.isNotEmpty() && coroutineContext.isActive) {
                log("Phase 3: plain (NOT encrypted) servers")
                val st = State(3, false, onProgress, 0)
                runPhase(ctx, plain.take(40).map { it to listOf(JSONObject().put("bypass", "off")) }, profiles, st, workers, true)
                all.addAll(st.wins); plainOnly = st.wins.isNotEmpty()
            }
            if (all.isEmpty() && tls.isNotEmpty() && coroutineContext.isActive) {
                log("No server passed the YouTube/Instagram check - basic test (weaker)")
                val st = State(2, true, onProgress, 0)
                runPhase(ctx, tls.map { it to variants(it, doh) }, profiles, st, workers, false)
                all.addAll(st.wins); relaxed = st.wins.isNotEmpty()
            }
        } finally { killAll() }
        // write the winning method into each server (done here, after all threads finished)
        val now = System.currentTimeMillis() / 1000
        for (w in all) {
            w.p.put("bypass", w.v.optString("bypass", "off"))
            if (w.v.has("ech")) w.p.put("ech", w.v.getString("ech")) else w.p.remove("ech")
            if (w.v.has("address_override")) w.p.put("address_override", w.v.getString("address_override"))
            else if (w.v.optBoolean("ip6")) resolve6(w.p.s("server"))?.let { w.p.put("address_override", it) }
            w.p.put("delay", w.ms); w.p.put("delay_ts", now)
        }
        val pool = all.filter { isTls(it.p) }.ifEmpty { all }
        return Result(pool.sortedBy { it.ms }.map { it.p to it.ms }, relaxed, plainOnly)
    }
}
