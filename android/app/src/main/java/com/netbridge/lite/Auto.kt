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
 * Not ported (yet): the clean-Cloudflare-IP scan phase.
 */
object Auto {
    class Win(val p: P, val v: JSONObject, val ms: Int)
    class Result(val winners: List<Pair<P, Int>>, val relaxed: Boolean, val plainOnly: Boolean)

    private val SITES = listOf(
        Triple("YouTube", "https://www.youtube.com/generate_204", { c: Int -> c == 204 }),
        Triple("Instagram", "https://www.instagram.com/", { c: Int -> c in 200..399 }),
        Triple("Google", "https://www.google.com/generate_204", { c: Int -> c == 204 })
    )
    private val DOH = listOf("https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query", "https://9.9.9.9/dns-query")
    private val live: MutableSet<Process> = ConcurrentHashMap.newKeySet<Process>()

    private val failLogged = java.util.concurrent.atomic.AtomicInteger()
    private fun why(p: P, msg: String) {
        if (failLogged.incrementAndGet() <= 10) VpnSvc.log("FAIL " + p.s("name").take(28) + " [" + p.s("bypass") + "]: " + msg)
    }

    fun killAll() { live.toList().forEach { it.destroyForcibly() } }

    private fun dnsQuery(name: String): ByteArray {
        val b = java.io.ByteArrayOutputStream()
        b.write(byteArrayOf(0x12, 0x34, 0x01, 0x00, 0, 1, 0, 0, 0, 0, 0, 0))
        for (part in name.split('.')) { b.write(part.length); b.write(part.toByteArray()) }
        b.write(0); b.write(byteArrayOf(0, 65, 0, 1))
        return b.toByteArray()
    }

    private fun dohWorks(url: String): Boolean = try {
        val q = Base64.getUrlEncoder().withoutPadding().encodeToString(dnsQuery(ConfigGen.ECH_PUBLIC))
        val c = URL("$url?dns=$q").openConnection(java.net.Proxy.NO_PROXY) as java.net.HttpURLConnection
        c.connectTimeout = 4000; c.readTimeout = 4000
        c.setRequestProperty("Accept", "application/dns-message")
        try { c.responseCode == 200 && c.inputStream.use { it.readBytes().size > 12 } } finally { c.disconnect() }
    } catch (e: Exception) { false }

    private suspend fun reachableDoh(): List<String> = coroutineScope {
        DOH.map { u -> async(Dispatchers.IO) { u to dohWorks(u) } }.awaitAll().filter { it.second }.map { it.first }
    }

    private fun variants(p: P, doh: List<String>): List<JSONObject> {
        if (!isTls(p)) return listOf(JSONObject().put("bypass", "off"))
        val out = arrayListOf(JSONObject().put("bypass", "off"), JSONObject().put("bypass", "pattng"), JSONObject().put("bypass", "standard"))
        for (u in doh.take(2)) out.add(JSONObject().put("bypass", "ech").put("ech", "${ConfigGen.ECH_PUBLIC}+$u"))
        return out
    }

    private fun with(p: P, v: JSONObject): P {
        val q = p.copyP(); q.remove("ech")
        for (k in v.keys()) q.put(k, v.get(k))
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
        fun tail() = synchronized(xlog) { xlog.takeLast(3).joinToString(" | ") }
        try {
            withContext(Dispatchers.IO) {
                cfg.writeText(ConfigGen.generate(listOf(p), "manual", 0, port, false, all, false, "none").toString())
                proc = XrayProc.start(ctx, cfg) { xlog.add(it) }; live.add(proc!!)
            }
            val pr = proc!!
            if (!withContext(Dispatchers.IO) { waitPort(port, 4000, pr) }) { why(p, "Xray did not start: " + tail()); return -1 }
            var best: Int? = null; var ok = 0; var tries = 0; var lastErr = ""
            while (ok < 2 && tries < 4) {
                coroutineContext.ensureActive(); tries++
                try {
                    val ms = withContext(Dispatchers.IO) { Net.fetchVia(port, "http://www.gstatic.com/generate_204", 6000).second }
                    best = if (best == null) ms else minOf(best, ms); ok++
                } catch (e: CancellationException) { throw e
                } catch (e: Exception) { lastErr = e.javaClass.simpleName + ": " + (e.message ?: ""); if (isTimeout(e)) break }
            }
            if (best == null) { why(p, "no reply through server: " + lastErr + " | xray: " + tail()); return -1 }
            if (!strict) return best
            val res = coroutineScope {
                SITES.map { (_, url, accept) ->
                    async(Dispatchers.IO) {
                        try { val (c, ms) = Net.fetchVia(port, url, 10000); if (accept(c)) maxOf(ms, 1) else -1 }
                        catch (e: Exception) { -1 }
                    }
                }.awaitAll()
            }
            if (res.all { it >= 0 }) return res.sum() / res.size
            why(p, "sites " + SITES.mapIndexed { i, t -> t.first + "=" + res[i] }.joinToString(" "))
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
                        val ms = testOne(ctx, with(p, v), all, strict)
                        if (ms >= 0) { st.wins.add(Win(p, v, ms)); break }
                    }
                    st.onProgress(st.done.incrementAndGet(), items.size)
                }
            }
        }.joinAll()
    }

    suspend fun run(ctx: Context, profiles: List<P>, onProgress: (Int, Int) -> Unit, log: (String) -> Unit, want: Int = 4, workers: Int = 6): Result {
        val tls = profiles.filter { isTls(it) }.sortedBy { p -> val d = p.optInt("delay", -1); if (d >= 0) d else 10_000_000 }
        val plain = profiles.filter { !isTls(it) }
        ConfigGen.forgetDns(); failLogged.set(0)
        // geoip.dat / geosite.dat must exist BEFORE the first test Xray starts (its config has a geoip:private rule)
        try { withContext(Dispatchers.IO) { XrayProc.prepare(ctx) } } catch (e: Exception) { log("geo files: " + e) }
        val doh = if (tls.isNotEmpty()) reachableDoh() else emptyList()
        log("ECH DoH reachable: " + (if (doh.isEmpty()) "none (ECH skipped)" else doh.joinToString()))
        val all = ArrayList<Win>(); var relaxed = false; var plainOnly = false
        try {
            if (tls.isNotEmpty()) {
                log("Phase 1: ${tls.size} TLS server(s) x methods")
                val st = State(want, true, onProgress, tls.size)
                runPhase(ctx, tls.map { it to variants(it, doh) }, profiles, st, workers, true)
                all.addAll(st.wins)
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
            w.p.put("delay", w.ms); w.p.put("delay_ts", now)
        }
        val pool = all.filter { isTls(it.p) }.ifEmpty { all }
        return Result(pool.sortedBy { it.ms }.map { it.p to it.ms }, relaxed, plainOnly)
    }
}
