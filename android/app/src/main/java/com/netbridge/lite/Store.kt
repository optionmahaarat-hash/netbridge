package com.netbridge.lite

import android.content.Context
import org.json.JSONArray
import java.io.File

/** Server list (files/profiles.json) + a few settings. The first run starts with the servers bundled in the APK. */
class Store(private val ctx: Context) {
    private val file = File(ctx.filesDir, "profiles.json")
    private val sp = ctx.getSharedPreferences("nb", Context.MODE_PRIVATE)

    var lang: String
        get() = sp.getString("lang", "fa") ?: "fa"
        set(v) { sp.edit().putString("lang", v).apply() }
    var iranDirect: Boolean
        get() = sp.getBoolean("iran", true)
        set(v) { sp.edit().putBoolean("iran", v).apply() }
    var selected: String
        get() = sp.getString("selected", "auto") ?: "auto"
        set(v) { sp.edit().putString("selected", v).apply() }
    var subs: List<String>
        get() = try { val a = JSONArray(sp.getString("subs", "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
        set(v) { sp.edit().putString("subs", jarr(v).toString()).apply() }

    private fun read(f: File): MutableList<P> = try {
        val a = JSONArray(f.readText()); (0 until a.length()).map { a.getJSONObject(it) }.filter { Parser.valid(it) }.distinctBy { profileKey(it) }.toMutableList()
    } catch (e: Exception) { mutableListOf() }

    fun load(): MutableList<P> {
        if (!file.exists()) {                                       // first run: bundled servers (no stale speeds)
            val seed = try {
                val a = JSONArray(ctx.assets.open("seed_profiles.json").bufferedReader().readText())
                (0 until a.length()).map { a.getJSONObject(it) }.filter { Parser.valid(it) }
            } catch (e: Exception) { emptyList() }
            save(seed)
        }
        return read(file)
    }

    fun save(list: List<P>) {
        val tmp = File(file.path + ".tmp")
        tmp.writeText(jarr(list).toString())
        tmp.renameTo(file)
    }
}
