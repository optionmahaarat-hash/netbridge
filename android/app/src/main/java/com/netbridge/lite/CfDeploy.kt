package com.netbridge.lite

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL
import java.security.SecureRandom
import java.util.UUID

/** (method, path, token, body, contentType) -> the "result" value of Cloudflare's answer. */
typealias CfCall = (String, String, String, ByteArray?, String) -> Any?

/** One-click personal VLESS relay on the user's OWN Cloudflare account (free plan, workers.dev). Same steps as app/core/cf_deploy.py.
 *  The scoped API token is used for these calls only and is never stored. */
object CfDeploy {
    class DeployError(msg: String) : Exception(msg)

    const val API = "https://api.cloudflare.com/client/v4"
    const val COMPAT = "2025-01-01"
    private val TOKEN = Regex("^[A-Za-z0-9_\\-]{20,120}$")
    private val UUID_RE = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    private val NAME = Regex("^[a-z0-9][a-z0-9\\-]{0,40}$")

    private fun hex(n: Int): String { val b = ByteArray(n); SecureRandom().nextBytes(b); return b.joinToString("") { "%02x".format(it) } }

    fun workerSource(template: String, uuid: String): String {
        if (!UUID_RE.matches(uuid)) throw DeployError("bad UUID")
        return template.replace("__UUID__", uuid)
    }

    /** (body, content type) of the module upload: a JSON "metadata" part plus the "worker.js" module. */
    fun multipart(source: String, bindings: List<JSONObject>? = null): Pair<ByteArray, String> {
        val b = "----nb" + hex(12)
        val mj = JSONObject().put("main_module", "worker.js").put("compatibility_date", COMPAT)
        if (!bindings.isNullOrEmpty()) mj.put("bindings", JSONArray().also { a -> bindings.forEach { a.put(it) } })
        val meta = mj.toString()
        val body = "--$b\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n$meta\r\n" +
            "--$b\r\nContent-Disposition: form-data; name=\"worker.js\"; filename=\"worker.js\"\r\n" +
            "Content-Type: application/javascript+module\r\n\r\n$source\r\n--$b--\r\n"
        return body.toByteArray(Charsets.UTF_8) to "multipart/form-data; boundary=$b"
    }

    /** The account's workers.dev sub-domain. A fresh account has none and Cloudflare answers the GET with an error, so create one then. */
    fun ensureSubdomain(call: CfCall, acc: String, token: String): String {
        val cur = try { (call("GET", "/accounts/$acc/workers/subdomain", token, null, "application/json") as? JSONObject)?.optString("subdomain").orEmpty() }
                  catch (_: DeployError) { "" }
        if (cur.isNotEmpty()) return cur
        val sub = "nb-" + hex(4)
        call("PUT", "/accounts/$acc/workers/subdomain", token, JSONObject().put("subdomain", sub).toString().toByteArray(), "application/json")
        return sub
    }

    fun realCall(proxyPort: Int?): CfCall = { method, path, token, body, ctype ->
        val proxy = if (proxyPort != null && proxyPort > 0) Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", proxyPort)) else Proxy.NO_PROXY
        val c = URL(API + path).openConnection(proxy) as HttpURLConnection
        try {
            c.connectTimeout = 30000; c.readTimeout = 60000; c.requestMethod = method
            c.setRequestProperty("Authorization", "Bearer $token"); c.setRequestProperty("User-Agent", "NetBridge")
            if (body != null) { c.doOutput = true; c.setRequestProperty("Content-Type", ctype); c.outputStream.use { it.write(body) } }
            val code = c.responseCode
            val raw = (if (code >= 400) c.errorStream else c.inputStream)?.use { it.readBytes() } ?: ByteArray(0)
            parse(String(raw, Charsets.UTF_8))
        } catch (e: DeployError) { throw e }
        catch (e: Exception) { throw DeployError("cannot reach Cloudflare: ${e.message}") }
        finally { c.disconnect() }
    }

    /** The "result" of an answer, or a DeployError carrying Cloudflare's own message. */
    fun parse(text: String): Any? {
        val js = try { JSONObject(text) } catch (_: Exception) { throw DeployError("unexpected answer from Cloudflare") }
        if (!js.optBoolean("success", false)) {
            val errs = js.optJSONArray("errors") ?: JSONArray()
            val msg = (0 until errs.length()).joinToString("; ") { errs.optJSONObject(it)?.optString("message") ?: errs.optString(it) }
            throw DeployError(msg.ifEmpty { "unknown error" })
        }
        return js.opt("result").let { if (it == JSONObject.NULL) null else it }
    }

    fun deploy(token0: String, template: String, call: CfCall, name0: String? = null, uuid0: String? = null,
               progress: (String) -> Unit = {}): P {
        val token = token0.trim()
        if (!TOKEN.matches(token)) throw DeployError("that does not look like a Cloudflare API token")
        val name = name0 ?: "nb-" + hex(4)
        if (!NAME.matches(name)) throw DeployError("worker name may contain only a-z, 0-9 and '-'")
        val uuid = uuid0 ?: UUID.randomUUID().toString()
        progress("token")
        call("GET", "/user/tokens/verify", token, null, "application/json")
        val accounts = call("GET", "/accounts", token, null, "application/json") as? JSONArray
        if (accounts == null || accounts.length() == 0)
            throw DeployError("the token has no access to any account (add Account > Workers Scripts > Edit and Account Settings > Read)")
        val acc = accounts.getJSONObject(0).getString("id")
        progress("upload")
        val (body, ctype) = multipart(workerSource(template, uuid))
        call("PUT", "/accounts/$acc/workers/scripts/$name", token, body, ctype)
        progress("subdomain")
        val sub = ensureSubdomain(call, acc, token)
        call("POST", "/accounts/$acc/workers/scripts/$name/subdomain", token,
            JSONObject().put("enabled", true).put("previews_enabled", false).toString().toByteArray(), "application/json")
        val host = "$name.$sub.workers.dev"
        return jobj("type" to "vless", "name" to "Mine - $name", "server" to host, "port" to 443, "network" to "ws", "uuid" to uuid,
            "security" to "tls", "sni" to host, "host" to host, "path" to "/", "fp" to "chrome", "alpn" to "http/1.1", "group" to "My Worker")
    }
}
