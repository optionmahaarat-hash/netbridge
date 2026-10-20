package com.netbridge.lite

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Telegram web-proxy builder: token -> load my domains -> pick one + sub-domain -> Create -> link. Mirrors app/ui/tg_dialog.py. */
@Composable
fun TgProxyDialog(vm: Vm, onClose: () -> Unit) {
    var token by remember { mutableStateOf("") }
    var zones by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    var pick by remember { mutableStateOf<Int?>(null) }            // null = no domain
    var label by remember { mutableStateOf("tg") }
    var busy by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    var link by remember { mutableStateOf(vm.tgLastLink()) }
    var fresh by remember { mutableStateOf(false) }
    val clipboard = LocalClipboardManager.current
    val uri = LocalUriHandler.current
    val busyTxt = t("tg_busy"); val okTxt = t("tg_ok"); val hFail = t("tg_health_fail")
    AlertDialog(
        onDismissRequest = { if (!busy) { token = ""; onClose() } }, containerColor = NB.Card,
        title = { Text(t("tg"), color = NB.Text) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(t("tg_help"), color = NB.Muted, fontSize = 12.sp)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value = token, onValueChange = { token = it.trim() }, singleLine = true, label = { Text(t("deploy_token")) },
                    visualTransformation = PasswordVisualTransformation())
                TextButton({
                    busy = true; note = ""
                    vm.tgZones(token) { ok, z, err -> busy = false; if (ok) { zones = z; pick = if (z.isNotEmpty()) 0 else null; if (z.isEmpty()) note = "—" } else note = err }
                }, enabled = !busy && token.length >= 20) { Text(t("tg_zones"), color = NB.Gold) }
                if (zones.isNotEmpty()) {
                    Row(Modifier.fillMaxWidth().clickable { pick = null }, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        RadioButton(selected = pick == null, onClick = { pick = null }); Text(t("tg_nodomain"), color = NB.Text, fontSize = 13.sp)
                    }
                    zones.forEachIndexed { i, z ->
                        Row(Modifier.fillMaxWidth().clickable { pick = i }, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            RadioButton(selected = pick == i, onClick = { pick = i }); Text(z.second, color = NB.Text, fontSize = 13.sp)
                        }
                    }
                    if (pick != null) OutlinedTextField(value = label, onValueChange = { label = it.trim().lowercase() }, singleLine = true, label = { Text(t("tg_label")) })
                }
                if (busy) { Spacer(Modifier.height(8.dp)); Text(busyTxt, color = NB.Muted, fontSize = 12.sp) }
                if (note.isNotEmpty() && !busy) { Spacer(Modifier.height(8.dp)); Text(note, color = NB.Err, fontSize = 12.sp) }
                if (link.isNotEmpty()) {
                    Spacer(Modifier.height(10.dp))
                    Text(if (fresh) okTxt else t("tg_last"), color = NB.Text, fontSize = 13.sp)
                    Text(link, color = NB.Gold, fontSize = 11.sp)
                    Row {
                        TextButton({ clipboard.setText(AnnotatedString(link)) }) { Text(t("tg_copy"), color = NB.Gold) }
                        TextButton({ try { uri.openUri(link) } catch (_: Exception) { } }) { Text(t("tg_open"), color = NB.Gold) }
                    }
                }
            }
        },
        confirmButton = { TextButton({
            busy = true; note = ""; fresh = false
            val tk = token
            vm.tgCreate(tk, pick?.let { zones[it] }, label) { ok, l, n ->
                busy = false
                if (ok) { link = l; fresh = true; token = ""; note = if (n == "ok") "" else "$hFail $n" } else note = n
            }
        }, enabled = !busy && token.length >= 20) { Text(t("tg_create"), color = NB.Gold) } },
        dismissButton = { TextButton({ if (!busy) { token = ""; onClose() } }) { Text(t("close"), color = NB.Muted) } })
}
