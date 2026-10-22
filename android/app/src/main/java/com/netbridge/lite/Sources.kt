package com.netbridge.lite

/** Public config lists ("Get free configs"). Same rules as app/core/sources.py: first mirror with usable servers wins,
 *  the group's old servers are replaced by the fresh list, at most [MAX] servers. */
object Sources {
    /** One public list: its mirrors (first with usable servers wins), the group its servers get, and how many to keep. */
    class Source(val id: String, val group: String, val limit: Int, val mirrors: List<String>)

    /** Same three lists as assets/config_sources.json on Windows. Free configs belong to others: no banking over them. */
    val ALL = listOf(
        Source("patterniha", "Free: patterniha", 300, listOf(
            "https://raw.githubusercontent.com/patterniha/Free-Configs/main/configs.txt",
            "https://cdn.jsdelivr.net/gh/patterniha/Free-Configs@main/configs.txt")),
        Source("kobabi", "Free: kobabi", 80, listOf(
            "https://raw.githubusercontent.com/liketolivefree/kobabi/main/sub.txt",
            "https://cdn.jsdelivr.net/gh/liketolivefree/kobabi@main/sub.txt")),
        Source("alirewa", "Free: Alirewa", 100, listOf(
            "https://raw.githubusercontent.com/Alirewa/V2ray-Configs/main/sub1.txt",
            "https://cdn.jsdelivr.net/gh/Alirewa/V2ray-Configs@main/sub1.txt")),
    )
    const val PAGE = "https://github.com/patterniha/Free-Configs"

    class SourceError(msg: String) : Exception(msg)

    /** (servers, mirror used). [fetch] returns the servers of one address (replaceable for tests). */
    fun fetchFirst(mirrors: List<String>, limit: Int, fetch: (String) -> List<P>): Pair<List<P>, String> {
        var last = "no mirror answered"
        for (u in mirrors) {
            try {
                val found = fetch(u)
                if (found.isNotEmpty()) return found.take(limit) to u
                last = "$u: the list has no usable servers"
            } catch (e: Exception) { last = "$u: ${e.message}" }
        }
        throw SourceError(last)
    }

    /** True when the list was never fetched, or the last fetch is at least [hours] old (a clock set backwards also counts as due). */
    fun due(lastMs: Long, nowMs: Long, hours: Int = 24): Boolean = lastMs <= 0L || nowMs < lastMs || nowMs - lastMs >= hours * 3_600_000L

    fun dropGroup(profiles: List<P>, group: String): List<P> = profiles.filter { it.s("group") != group }
}
