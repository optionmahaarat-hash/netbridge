package com.netbridge.lite

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Bypass values that can change WITHOUT a new APK (port of app/core/presets.py - same file, same rules).
 * Layers, later wins field by field:  built-in  ->  assets/bypass_presets.json  ->  files/bypass_presets.json (written by update()).
 * A downloaded file ends up inside the Xray config, so it is checked against an allow-list; a preset that fails is skipped
 * with a reason and the rest keep working. A broken or missing file never stops the app: the layer below is used.
 */
object Presets {
    const val DEFAULT_URL = "https://raw.githubusercontent.com/optionmahaarat-hash/netbridge/main/assets/bypass_presets.json"
    private const val FILE = "bypass_presets.json"
    private const val MAX_BYTES = 64 * 1024
    private const val MAX_PRESETS = 16
    private const val MAX_MASKS = 8

    private val RESERVED = setOf("off", "ech", "custom")
    private val FINGERPRINTS = setOf("unsafe", "chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized")
    private val MASK_NETWORKS = setOf("tcp", "udp")
    private val MASK_TYPES = setOf("fragment", "noise")
    private val NAME_RE = Regex("^[a-z][a-z0-9_]{0,23}$")
    private val CIPHER_RE = Regex("^[A-Z0-9_]+(:[A-Z0-9_]+)*$")
    private val KEY_RE = Regex("^[A-Za-z][A-Za-z0-9_]{0,31}$")
    private val PRESET_KEYS = setOf("label", "fingerprint", "cipherSuites", "finalmask", "auto")

    @Volatile var version = 1
        private set
    @Volatile var errors: List<String> = emptyList()
        private set
    @Volatile private var cur: Map<String, JSONObject> = builtin()
    @Volatile private var lastTry = 0L

    /** the values compiled into the app: the last resort (same numbers as the Windows app) */
    private fun builtin(): Map<String, JSONObject> = linkedMapOf(
        "standard" to JSONObject().put("label", "Fragment + unsafe (works on older Xray too)").put("fingerprint", "unsafe")
            .put("cipherSuites", ConfigGen.CIPHERS).put("finalmask", ConfigGen.fmStandard()).put("auto", true),
        "pattng" to JSONObject().put("label", "Video/PattNG exact (needs Xray 26.7 or newer)").put("fingerprint", "unsafe")
            .put("cipherSuites", ConfigGen.CIPHERS).put("finalmask", ConfigGen.fmPattng()).put("auto", true)
    )

    // ------------------------------------------------------------------ checks
    private fun scalar(v: Any?) = (v is Int || v is Long || v is String) && v.toString().length <= 64

    private fun checkSettings(s: Any?) {
        if (s !is JSONObject || s.length() > 12) throw IllegalArgumentException("settings must be a small object")
        for (k in s.keys()) {
            if (!KEY_RE.matches(k)) throw IllegalArgumentException("bad setting name $k")
            val v = s.get(k)
            if (v is JSONArray) {
                if (v.length() > 12 || (0 until v.length()).any { !scalar(v.get(it)) })
                    throw IllegalArgumentException("setting $k must be a short list of numbers/text")
            } else if (!scalar(v)) throw IllegalArgumentException("setting $k must be a number or text")
        }
    }

    private fun checkFinalmask(fm: Any?) {
        if (fm !is JSONObject || fm.length() == 0) throw IllegalArgumentException("finalmask must be an object like {\"tcp\": [...]}")
        for (net in fm.keys()) {
            if (net !in MASK_NETWORKS) throw IllegalArgumentException("finalmask network $net is not allowed")
            val masks = fm.get(net)
            if (masks !is JSONArray || masks.length() == 0 || masks.length() > MAX_MASKS)
                throw IllegalArgumentException("finalmask.$net must be a list of 1-$MAX_MASKS masks")
            for (i in 0 until masks.length()) {
                val m = masks.get(i)
                if (m !is JSONObject || m.keys().asSequence().any { it != "type" && it != "settings" })
                    throw IllegalArgumentException("a mask has only 'type' and 'settings'")
                if (m.optString("type") !in MASK_TYPES) throw IllegalArgumentException("mask type ${m.optString("type")} is not allowed")
                checkSettings(if (m.has("settings")) m.get("settings") else JSONObject())
            }
        }
    }

    private fun checkPreset(p: Any?): JSONObject {
        if (p !is JSONObject) throw IllegalArgumentException("a preset must be an object")
        val extra = p.keys().asSequence().filter { it !in PRESET_KEYS }.toList()
        if (extra.isNotEmpty()) throw IllegalArgumentException("unknown field: " + extra.sorted().joinToString())
        val out = JSONObject()
        if (p.has("label")) {
            val l = p.get("label")
            if (l !is String || l.isEmpty() || l.length > 80) throw IllegalArgumentException("label must be text up to 80 characters")
            out.put("label", l)
        }
        if (p.has("fingerprint")) {
            val f = p.get("fingerprint")
            if (f !is String || f !in FINGERPRINTS) throw IllegalArgumentException("fingerprint $f is not allowed")
            out.put("fingerprint", f)
        }
        if (p.has("cipherSuites")) {
            val c = p.get("cipherSuites")
            if (c !is String || c.length > 2000 || !CIPHER_RE.matches(c))
                throw IllegalArgumentException("cipherSuites must be NAMES joined by ':' (capital letters, digits, '_')")
            out.put("cipherSuites", c)
        }
        if (p.has("finalmask")) { checkFinalmask(p.get("finalmask")); out.put("finalmask", JSONObject(p.getJSONObject("finalmask").toString())) }
        if (p.has("auto")) {
            val a = p.get("auto")
            if (a !is Boolean) throw IllegalArgumentException("auto must be true or false")
            out.put("auto", a)
        }
        return out
    }

    /** -> (clean doc with only the presets that passed, 'name: reason' errors). Throws IllegalArgumentException if the file is unusable. */
    fun checkDoc(raw: JSONObject): Pair<JSONObject, List<String>> {
        val errs = ArrayList<String>()
        val v = raw.opt("version")
        val ver = when (v) { null, JSONObject.NULL -> 0; is Int -> v; is Long -> v.toInt(); else -> throw IllegalArgumentException("'version' must be a whole number") }
        if (ver < 0) throw IllegalArgumentException("'version' must be a whole number")
        val ps = raw.opt("presets")
        if (ps !is JSONObject) throw IllegalArgumentException("'presets' is missing")
        if (ps.length() > MAX_PRESETS) throw IllegalArgumentException("too many presets (max $MAX_PRESETS)")
        val clean = JSONObject()
        for (name in ps.keys()) {
            if (name in RESERVED) { errs.add("$name: this name is reserved"); continue }
            if (!NAME_RE.matches(name)) { errs.add("$name: bad name (use a-z, 0-9, _)"); continue }
            try { clean.put(name, checkPreset(ps.get(name))) } catch (e: IllegalArgumentException) { errs.add("$name: ${e.message}") }
        }
        return JSONObject().put("version", ver).put("presets", clean) to errs
    }

    // ------------------------------------------------------------------ layers
    private fun layer(text: String?, label: String, errs: MutableList<String>): JSONObject? {
        if (text == null) return null
        return try {
            val (doc, e) = checkDoc(JSONObject(text))
            e.forEach { errs.add("$label $it") }
            doc
        } catch (e: Exception) { errs.add("$label: ${e.message}"); null }
    }

    /** (Re)reads the preset files. Never throws: on any problem the built-in values stay in force. */
    fun load(ctx: Context) {
        val errs = ArrayList<String>()
        val merged = LinkedHashMap<String, JSONObject>()
        builtin().forEach { (k, v) -> merged[k] = v }
        var ver = 1
        try {
            val asset: String? = try { ctx.assets.open(FILE).use { it.readBytes().toString(Charsets.UTF_8) } } catch (_: Exception) { null }
            val f = File(ctx.filesDir, FILE)
            var user: String? = null
            if (f.exists()) {
                user = try { f.readText() } catch (_: Exception) { null }
            }
            val userDoc = layer(user, "user file", errs)
            if (user != null && userDoc == null) {            // keep a damaged file for inspection
                try { f.renameTo(File(ctx.filesDir, "$FILE.bad")) } catch (_: Exception) { }
            }
            for (doc in listOf(layer(asset, "bundled file", errs), userDoc)) {
                if (doc == null) continue
                ver = maxOf(ver, doc.optInt("version", 0))
                val ps = doc.getJSONObject("presets")
                for (name in ps.keys()) {
                    val base = merged[name]?.let { JSONObject(it.toString()) } ?: JSONObject()
                    val p = ps.getJSONObject(name)
                    for (k in p.keys()) base.put(k, p.get(k))
                    merged[name] = base
                }
            }
        } catch (e: Throwable) { errs.add("presets: ${e.message}") }
        cur = merged; version = ver; errors = errs
    }

    /** the preset for a method code ('pattng', 'standard', or one added by a file), a private copy; null if unknown */
    fun get(name: String): JSONObject? = cur[name]?.let { JSONObject(it.toString()) }

    /** method codes AUTO should try after 'off': pattng, standard, then the extras the file marks with "auto": true */
    fun autoNames(): List<String> {
        val m = cur
        val first = listOf("pattng", "standard").filter { m[it]?.optBoolean("auto", true) ?: false }
        val rest = m.filter { (n, p) -> n != "pattng" && n != "standard" && p.optBoolean("auto", false) }.keys
        return first + rest
    }

    // ------------------------------------------------------------------ updating from the internet
    /** Downloads + checks + saves when newer. Returns "updated" or "current". Throws on download/format problems. */
    fun update(ctx: Context, url: String = DEFAULT_URL, timeoutMs: Int = 6000): String {
        if (!url.lowercase().startsWith("https://")) throw IllegalStateException("the update address must start with https://")
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = timeoutMs; c.readTimeout = timeoutMs
        c.setRequestProperty("User-Agent", "NetBridge")
        val body: ByteArray = try {
            if (c.responseCode != 200) throw IllegalStateException("HTTP ${c.responseCode}")
            c.inputStream.use { s ->
                val out = java.io.ByteArrayOutputStream()
                val buf = ByteArray(4096)
                while (true) {
                    val r = s.read(buf)
                    if (r < 0) break
                    out.write(buf, 0, r)
                    if (out.size() > MAX_BYTES) throw IllegalStateException("the file is too large")
                }
                out.toByteArray()
            }
        } finally { c.disconnect() }
        return install(ctx, body)
    }

    /** Checks a downloaded file and saves it as the user's layer when its version is newer. "updated" or "current". */
    internal fun install(ctx: Context, body: ByteArray): String {
        val (doc, _) = checkDoc(JSONObject(body.toString(Charsets.UTF_8)))
        if (doc.getJSONObject("presets").length() == 0) throw IllegalStateException("the file has no usable preset")
        if (doc.getInt("version") <= version) return "current"
        val tmp = File(ctx.filesDir, "$FILE.tmp")
        tmp.writeText(doc.toString())
        if (!tmp.renameTo(File(ctx.filesDir, FILE))) { File(ctx.filesDir, FILE).delete(); tmp.renameTo(File(ctx.filesDir, FILE)) }
        load(ctx)
        return "updated"
    }

    /** Silent version for AUTO: at most once per 6 h per run of the app, short timeout, every failure is only logged. */
    fun autoUpdate(ctx: Context, log: (String) -> Unit) {
        val now = System.currentTimeMillis()
        if (lastTry != 0L && now - lastTry < 6 * 3600_000L) return
        lastTry = now
        try {
            val r = update(ctx)
            log(if (r == "updated") "bypass values updated to version $version" else "bypass values are current (version $version)")
        } catch (e: Exception) { log("bypass values: update skipped (" + e.javaClass.simpleName + ": " + (e.message ?: "").take(80) + ")") }
    }
}
