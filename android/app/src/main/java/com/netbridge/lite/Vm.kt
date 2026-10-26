package com.netbridge.lite

import android.app.Application
import android.content.Intent
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import java.io.File

enum class Phase { IDLE, SEARCHING, STARTING, CONNECTED }

data class Ui(
    val phase: Phase = Phase.IDLE, val done: Int = 0, val total: Int = 0,
    val profiles: List<P> = emptyList(), val rev: Int = 0, val selected: String = "auto",
    val exit: String = "", val msg: String = "", val warn: String = "",
    val iran: Boolean = true, val lang: String = "fa", val clipNew: Int = 0, val freeAuto: Boolean = false,
    val firewall: String = "auto"
)

class Vm(app: Application) : AndroidViewModel(app) {
    private val store = Store(app)
    private val profiles = store.load()
    private var job: Job? = null
    private var clipText = ""
    private var clipSeen = ""
    val ui = MutableStateFlow(Ui(profiles = profiles.toList(), selected = store.selected, iran = store.iranDirect, lang = store.lang, freeAuto = store.freeAuto, firewall = store.firewall))

    init {
        Presets.load(app)
        if (store.freeAuto && Sources.due(store.freeLast, System.currentTimeMillis())) getFreeConfigs { ok, text -> logLine("free configs: " + if (ok) "$text new" else text) }
        viewModelScope.launch {
            VpnSvc.connected.collect { c ->
                val ph = ui.value.phase
                if (c) { set { it.copy(phase = Phase.CONNECTED, msg = "") }; fetchExit() }
                else if (ph == Phase.CONNECTED || ph == Phase.STARTING) set { it.copy(phase = Phase.IDLE, exit = "") }
            }
        }
        viewModelScope.launch {
            VpnSvc.error.collect { e -> if (e.isNotEmpty()) set { it.copy(phase = Phase.IDLE, msg = e) } }
        }
    }

    private fun set(f: (Ui) -> Ui) = ui.update(f)
    private fun refresh() = set { it.copy(profiles = profiles.toList(), rev = it.rev + 1, selected = store.selected) }
    private fun logLine(s: String) = VpnSvc.log(s)
    fun report(): String = "NetBridge ${BuildInfo.VERSION}\nservers: ${profiles.size}\n" +
        synchronized(VpnSvc.logLines) { VpnSvc.logLines.joinToString("\n") }

    // ---------- connect / disconnect ----------
    fun connect() {
        if (job?.isActive == true || ui.value.phase != Phase.IDLE) return
        if (profiles.isEmpty()) { set { it.copy(msg = "empty") }; return }
        job = viewModelScope.launch {
            val app = getApplication<Application>()
            try {
                set { it.copy(phase = Phase.SEARCHING, done = 0, total = 0, msg = "", warn = "") }
                val sel = profiles.firstOrNull { profileKey(it) == store.selected }
                val pool: List<P>
                var warn = ""
                if (sel != null) pool = listOf(sel)
                else {
                    Auto.firewall = store.firewall
                    val r = Auto.run(app, profiles.toList(), { d, t -> set { it.copy(done = d, total = t) } }, ::logLine)
                    withContext(Dispatchers.IO) { store.save(profiles) }
                    refresh()
                    if (r.winners.isEmpty()) { set { it.copy(phase = Phase.IDLE, msg = "all_dead") }; return@launch }
                    pool = r.winners.map { it.first }.take(4)
                    warn = if (r.relaxed) "warn_relaxed" else if (r.plainOnly) "warn_plain" else ""
                }
                set { it.copy(phase = Phase.STARTING, warn = warn) }
                val socks = freePort(); val http = freePort()
                val cfg = withContext(Dispatchers.IO) {
                    val j = ConfigGen.generate(pool, if (pool.size > 1) "auto" else "manual", socks, http, store.iranDirect, profiles.toList(), true)
                    File(app.filesDir, "active.json").also { it.writeText(j.toString()) }
                }
                VpnSvc.error.value = ""
                ContextCompat.startForegroundService(app, Intent(app, VpnSvc::class.java).setAction(VpnSvc.ACTION_START)
                    .putExtra("cfg", cfg.absolutePath).putExtra("socks", socks).putExtra("http", http))
                withTimeoutOrNull(15000) { VpnSvc.connected.first { it } }
                    ?: set { if (it.phase == Phase.STARTING) it.copy(phase = Phase.IDLE, msg = VpnSvc.error.value.ifEmpty { "start_fail" }) else it }
            } catch (e: CancellationException) {
                set { if (it.phase == Phase.SEARCHING || it.phase == Phase.STARTING) it.copy(phase = Phase.IDLE) else it }
                throw e
            } catch (e: Exception) {
                set { it.copy(phase = Phase.IDLE, msg = e.message ?: e.javaClass.simpleName) }
            }
        }
    }

    fun cancel() { job?.cancel(); Auto.killAll(); set { it.copy(phase = Phase.IDLE) } }

    fun disconnect() {
        val app = getApplication<Application>()
        app.startService(Intent(app, VpnSvc::class.java).setAction(VpnSvc.ACTION_STOP))
        set { it.copy(phase = Phase.IDLE, exit = "") }
    }

    private fun fetchExit() {
        viewModelScope.launch(Dispatchers.IO) {
            repeat(3) {
                try {
                    val e = Net.exitInfo(VpnSvc.httpPort)
                    set { s -> s.copy(exit = e) }; return@launch
                } catch (_: Exception) { delay(1500) }
            }
            set { it.copy(msg = "st_noinet") }
        }
    }

    // ---------- servers ----------
    fun select(key: String) { store.selected = key; refresh() }

    fun delete(key: String) {
        profiles.removeAll { profileKey(it) == key }
        if (store.selected == key) store.selected = "auto"
        store.save(profiles); refresh()
    }

    fun deleteAll() { profiles.clear(); store.subs = emptyList(); store.selected = "auto"; store.save(profiles); refresh() }

    /** -> message key + count. Accepts links, a base64 list, or a subscription URL. */
    fun addText(text: String, onDone: (String, Int) -> Unit) {
        val t = text.trim()
        if (Regex("^https?://\\S+$").matches(t) && "://" !in t.substring(8)) {
            viewModelScope.launch {
                try {
                    val (found, _) = withContext(Dispatchers.IO) {
                        Net.fetchSubscription(t, if (ui.value.phase == Phase.CONNECTED) VpnSvc.httpPort else null)
                    }
                    val n = merge(found)
                    if (found.isNotEmpty()) store.subs = (store.subs + t).distinct()   // never keep a link that gave no server
                    onDone(if (found.isEmpty()) "no_valid" else "added", n)
                } catch (e: Exception) { onDone("sub_fail", 0) }
            }
            return
        }
        val (found, _) = Parser.parseMany(t)
        if (found.isEmpty()) onDone("no_valid", 0) else { val n = merge(found); onDone(if (n == 0) "nothing_new" else "added", n) }
    }

    private fun merge(found: List<P>): Int {
        val seen = profiles.map { profileKey(it) }.toMutableSet(); var n = 0
        for (p in found) if (seen.add(profileKey(p))) { profiles.add(p); n++ }
        store.save(profiles); refresh(); return n
    }

    /** Downloads every public list, replaces each list's previous servers and adds the fresh ones.
     *  A list that fails is skipped (the others still count). onDone(ok, text): the number of new servers, or the error. */
    fun getFreeConfigs(onDone: (Boolean, String) -> Unit) {
        viewModelScope.launch {
            try {
                val proxy = if (ui.value.phase == Phase.CONNECTED) VpnSvc.httpPort else null
                var total = 0; var okLists = 0; var lastErr = "no list answered"
                for (src in Sources.ALL) {
                    try {
                        val (found, _) = withContext(Dispatchers.IO) { Sources.fetchFirst(src.mirrors, src.limit) { Net.fetchSubscription(it, proxy).first } }
                        found.forEach { it.put("group", src.group) }
                        val keep = Sources.dropGroup(profiles.toList(), src.group)
                        profiles.clear(); profiles.addAll(keep)
                        total += merge(found); okLists++
                    } catch (e: Exception) { lastErr = "${src.id}: ${e.message}" }
                }
                if (okLists == 0) { onDone(false, lastErr); return@launch }
                store.freeLast = System.currentTimeMillis()
                onDone(true, total.toString())
            } catch (e: Exception) { onDone(false, e.message ?: "error") }
        }
    }

    /** Creates the personal Worker on the user's Cloudflare account and adds its profile. onDone(ok, text): the address or the error. */
    fun deployWorker(token: String, onDone: (Boolean, String) -> Unit) {
        viewModelScope.launch {
            try {
                val p = withContext(Dispatchers.IO) {
                    val src = getApplication<Application>().assets.open("vless_worker.js").bufferedReader().use { it.readText() }
                    CfDeploy.deploy(token, src, CfDeploy.realCall(if (ui.value.phase == Phase.CONNECTED) VpnSvc.httpPort else null))
                }
                merge(listOf(p))
                onDone(true, p.s("server"))
            } catch (e: Exception) { onDone(false, e.message ?: "error") }
        }
    }

    private fun cfProxy(): Int? = if (ui.value.phase == Phase.CONNECTED) VpnSvc.httpPort else null

    /** Domains already on the user's Cloudflare account. onDone(ok, zones, error). */
    fun tgZones(token: String, onDone: (Boolean, List<Pair<String, String>>, String) -> Unit) {
        viewModelScope.launch {
            try {
                val z = withContext(Dispatchers.IO) { TgProxy.listZones(token, CfDeploy.realCall(cfProxy())) }
                onDone(true, z, "")
            } catch (e: Exception) { onDone(false, emptyList(), e.message ?: "error") }
        }
    }

    /** Creates the Telegram web-proxy Worker (+ optional custom domain) and checks it. onDone(ok, link, note); note = health result or error. */
    fun tgCreate(token: String, zone: Pair<String, String>?, label: String, onDone: (Boolean, String, String) -> Unit) {
        viewModelScope.launch {
            try {
                val port = cfProxy()
                val r = withContext(Dispatchers.IO) {
                    val src = TgProxy.fetchSource(TgProxy.httpGet(port))
                    TgProxy.deploy(token, src, zone, label, CfDeploy.realCall(port))
                }
                store.tgLink = r.link
                val h = withContext(Dispatchers.IO) {
                    var res = false to ""
                    for (i in 0 until 4) { res = TgProxy.health(r.server, port); if (res.first) break; Thread.sleep(8000) }
                    res
                }
                onDone(true, r.link, if (h.first) "ok" else h.second)
            } catch (e: Exception) { onDone(false, "", e.message ?: "error") }
        }
    }

    fun tgLastLink(): String = store.tgLink

    fun refreshSubs(onDone: (Int) -> Unit) {
        viewModelScope.launch {
            var total = 0
            for (u in store.subs) try {
                val (found, _) = withContext(Dispatchers.IO) { Net.fetchSubscription(u, if (ui.value.phase == Phase.CONNECTED) VpnSvc.httpPort else null) }
                total += merge(found).coerceAtLeast(0)
            } catch (_: Exception) { }
            onDone(total)
        }
    }

    // ---------- settings / clipboard ----------
    fun setFreeAuto(v: Boolean) { store.freeAuto = v; set { it.copy(freeAuto = v) } }
    fun setFirewall(v: String) { store.firewall = v; Auto.firewall = v; set { it.copy(firewall = v) } }
    fun setIran(v: Boolean) { store.iranDirect = v; set { it.copy(iran = v) } }
    fun setLang(v: String) { store.lang = v; set { it.copy(lang = v) } }
    fun clearMsg() = set { it.copy(msg = "") }

    fun checkClip(text: String?) {
        if (text.isNullOrBlank() || text == clipSeen || text.length > 400_000) return
        if (!Regex("(vless|vmess|trojan|ss)://", RegexOption.IGNORE_CASE).containsMatchIn(text)) { set { it.copy(clipNew = 0) }; return }
        val (found, _) = Parser.parseMany(text)
        val have = profiles.map { profileKey(it) }.toSet()
        val n = found.count { profileKey(it) !in have }
        clipText = text; set { it.copy(clipNew = n) }
    }

    /** Adds configs found in the clipboard by itself, once per copied text. Quiet when nothing is new. */
    fun autoClip(text: String?, onDone: (String, Int) -> Unit) {
        if (text.isNullOrBlank() || text == clipSeen || text.length > 400_000) return
        val t = text.trim()
        val isSubUrl = t.length < 2000 && Regex("^https?://\\S+$").matches(t) && "://" !in t.substring(t.indexOf("://") + 3)
        if (!isSubUrl && !Regex("(vless|vmess|trojan|ss)://", RegexOption.IGNORE_CASE).containsMatchIn(text)) return
        clipSeen = text
        addText(text, onDone)
    }

    fun addClip(onDone: (String, Int) -> Unit) { clipSeen = clipText; set { it.copy(clipNew = 0) }; addText(clipText, onDone) }
    fun dismissClip() { clipSeen = clipText; set { it.copy(clipNew = 0) } }
}

object BuildInfo { const val VERSION = "0.2.0" }
