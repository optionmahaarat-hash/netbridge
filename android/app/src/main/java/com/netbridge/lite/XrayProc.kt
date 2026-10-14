package com.netbridge.lite

import android.content.Context
import java.io.File

/** The Xray core is shipped as lib/arm64-v8a/libxray.so (a normal executable) and started as a child process. */
object XrayProc {
    fun exe(ctx: Context) = File(ctx.applicationInfo.nativeLibraryDir, "libxray.so")
    fun geoDir(ctx: Context) = File(ctx.filesDir, "geo")

    /** geoip.dat / geosite.dat from the APK -> files/geo (needed for the "Iranian sites direct" rules) */
    fun prepare(ctx: Context) {
        val d = geoDir(ctx); d.mkdirs()
        for (n in listOf("geoip.dat", "geosite.dat")) {
            val out = File(d, n)
            ctx.assets.openFd(n).use { fd ->
                if (!out.exists() || out.length() != fd.length) {
                    ctx.assets.open(n).use { i -> File(d, "$n.tmp").outputStream().use { o -> i.copyTo(o) } }
                    File(d, "$n.tmp").renameTo(out)
                }
            }
        }
    }

    fun start(ctx: Context, cfg: File, sink: ((String) -> Unit)? = null): Process {
        val pb = ProcessBuilder(exe(ctx).absolutePath, "run", "-c", cfg.absolutePath)
            .directory(ctx.filesDir).redirectErrorStream(true)
        pb.environment()["XRAY_LOCATION_ASSET"] = geoDir(ctx).absolutePath
        val p = pb.start()
        Thread {
            try { p.inputStream.bufferedReader().forEachLine { sink?.invoke(it) } } catch (_: Exception) { }
        }.apply { isDaemon = true }.start()
        return p
    }

    fun stop(p: Process?) {
        if (p == null) return
        p.destroy()
        try { if (!p.waitFor(1500, java.util.concurrent.TimeUnit.MILLISECONDS)) p.destroyForcibly() } catch (_: Exception) { p.destroyForcibly() }
    }
}
