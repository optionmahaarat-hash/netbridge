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
