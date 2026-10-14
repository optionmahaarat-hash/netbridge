package com.netbridge.lite

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue

class MainActivity : ComponentActivity() {
    private val vm: Vm by viewModels()
    private var askedNotif = false

    private val vpnReq = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (it.resultCode == RESULT_OK) vm.connect()
    }
    private val notifReq = registerForActivityResult(ActivityResultContracts.RequestPermission()) { startVpnFlow() }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT)
        )
        super.onCreate(savedInstanceState)
        setContent {
            val ui by vm.ui.collectAsState()
            NBTheme(ui.lang) { HomeScreen(vm, ui, ::onOrb) }
        }
    }

    private fun onOrb() {
        when (vm.ui.value.phase) {
            Phase.IDLE -> begin()
            Phase.SEARCHING -> vm.cancel()
            Phase.STARTING -> { vm.cancel(); vm.disconnect() }
            Phase.CONNECTED -> vm.disconnect()
        }
    }

    private fun begin() {
        if (Build.VERSION.SDK_INT >= 33 && !askedNotif &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            askedNotif = true
            notifReq.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else startVpnFlow()
    }

    private fun startVpnFlow() {
        val i = VpnService.prepare(this)
        if (i != null) vpnReq.launch(i) else vm.connect()
    }
}
