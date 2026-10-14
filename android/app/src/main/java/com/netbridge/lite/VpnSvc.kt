package com.netbridge.lite

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.graphics.drawable.Icon
import android.net.VpnService
import android.os.ParcelFileDescriptor
import hev.htproxy.TProxyService
import kotlinx.coroutines.flow.MutableStateFlow
import java.io.File

/** The VPN: Xray (socks + http inbound on localhost) + hev-socks5-tunnel that feeds the phone's traffic into it. */
class VpnSvc : VpnService() {
    companion object {
        const val ACTION_START = "nb.start"
        const val ACTION_STOP = "nb.stop"
        val connected = MutableStateFlow(false)
        val error = MutableStateFlow("")
        @Volatile var httpPort = 0
        val logLines = ArrayList<String>()
        fun log(s: String) { synchronized(logLines) { logLines.add(s); if (logLines.size > 300) logLines.removeAt(0) } }
    }

    private var tun: ParcelFileDescriptor? = null
    private var xray: Process? = null
    private var up = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { shutdown(); stopSelf() }
            ACTION_START -> {
                try { startForeground(1, notification()) } catch (_: Exception) { }
                val cfg = intent.getStringExtra("cfg") ?: ""; val socks = intent.getIntExtra("socks", 0); val http = intent.getIntExtra("http", 0)
                Thread { startAll(cfg, socks, http) }.start()          // starting Xray waits ~1 s: not on the main thread
            }
        }
        return START_NOT_STICKY
    }

    private fun notification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("nb", "NetBridge", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, VpnSvc::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, "nb").setSmallIcon(R.drawable.ic_stat).setContentTitle("NetBridge")
            .setContentText(if (Store(this).lang == "fa") "متصل است" else "Connected")
            .setContentIntent(open).setOngoing(true)
            .addAction(Notification.Action.Builder(Icon.createWithResource(this, R.drawable.ic_stat),
                if (Store(this).lang == "fa") "قطع" else "Disconnect", stop).build()).build()
    }

    private fun startAll(cfgPath: String, socks: Int, http: Int) {
        shutdown()
        error.value = ""
        try {
            startForeground(1, notification())
            XrayProc.prepare(this)
            val proc = XrayProc.start(this, File(cfgPath)) { log(it) }
            xray = proc
            Thread.sleep(1200)
            if (!proc.isAlive) throw IllegalStateException("Xray stopped right after start: " + synchronized(logLines) { logLines.takeLast(3).joinToString(" | ") })

            val b = Builder().setSession("NetBridge").setMtu(1500)
                .addAddress("26.26.26.1", 30).addRoute("0.0.0.0", 0).addDnsServer("1.1.1.1")
            try { b.addDisallowedApplication(packageName) } catch (_: Exception) { }   // Xray's own connections must NOT enter the VPN
            val fd = b.establish() ?: throw IllegalStateException("VPN permission was not granted")
            tun = fd

            val yml = File(filesDir, "hev.yml")
            yml.writeText(
                "tunnel:\n  mtu: 1500\n  ipv4: 26.26.26.2\n" +
                "socks5:\n  port: $socks\n  address: 127.0.0.1\n  udp: 'udp'\n" +
                "misc:\n  log-level: warn\n"
            )
            TProxyService.TProxyStartService(yml.absolutePath, fd.fd)
            httpPort = http; up = true
            connected.value = true
            Thread {                                   // if Xray dies by itself, drop the VPN and tell the app
                try { proc.waitFor() } catch (_: Exception) { }
                if (up && xray === proc) { error.value = "Xray stopped: " + synchronized(logLines) { logLines.takeLast(3).joinToString(" | ") }; shutdown(); stopSelf() }
            }.apply { isDaemon = true }.start()
        } catch (e: Throwable) {
            error.value = e.message ?: e.javaClass.simpleName
            shutdown(); stopSelf()
        }
    }

    private fun shutdown() {
        val was = up
        up = false
        try { if (was) TProxyService.TProxyStopService() } catch (_: Throwable) { }
        try { tun?.close() } catch (_: Exception) { }
        tun = null
        val x = xray; xray = null
        XrayProc.stop(x)
        connected.value = false
        try { stopForeground(STOP_FOREGROUND_REMOVE) } catch (_: Exception) { }
    }

    override fun onRevoke() { shutdown(); stopSelf() }
    override fun onDestroy() { shutdown(); super.onDestroy() }
}
