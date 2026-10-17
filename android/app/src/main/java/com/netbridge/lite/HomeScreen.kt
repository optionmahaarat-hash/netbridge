package com.netbridge.lite

import android.widget.Toast
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

private val GoldBrush = Brush.horizontalGradient(listOf(NB.GoldDeep, NB.GoldLight, NB.GoldDeep))

// ------------------------------------------------------------------ building blocks
@Composable
fun Glass(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    val base = modifier
        .clip(shape)
        .background(Brush.verticalGradient(listOf(Color(0xFF181C26), Color(0xFF10131A))))
        .border(1.dp, Brush.verticalGradient(listOf(NB.StrokeStrong, NB.Stroke)), shape)
    Box(if (onClick != null) base.clickable(onClick = onClick) else base) { content() }
}

@Composable
fun Logo(size: Int = 30) {
    androidx.compose.foundation.Canvas(Modifier.size(size.dp)) {
        val w = this.size.width; val h = this.size.height
        val sw = w * 0.07f
        drawLine(NB.GoldLight, Offset(w * .08f, h * .72f), Offset(w * .92f, h * .72f), sw, StrokeCap.Round)
        drawLine(NB.GoldLight, Offset(w * .30f, h * .72f), Offset(w * .30f, h * .28f), sw, StrokeCap.Round)
        drawLine(NB.GoldLight, Offset(w * .70f, h * .72f), Offset(w * .70f, h * .28f), sw, StrokeCap.Round)
        val path = androidx.compose.ui.graphics.Path().apply {
            moveTo(w * .08f, h * .60f); quadraticBezierTo(w * .24f, h * .60f, w * .30f, h * .28f)
            quadraticBezierTo(w * .50f, h * .86f, w * .70f, h * .28f); quadraticBezierTo(w * .76f, h * .60f, w * .92f, h * .60f)
        }
        drawPath(path, NB.Gold, style = Stroke(sw * .8f, cap = StrokeCap.Round))
    }
}

@Composable
fun Orb(phase: Phase, onClick: () -> Unit, diameter: Dp = 262.dp) {
    val inf = rememberInfiniteTransition(label = "orb")
    val rot by inf.animateFloat(0f, 360f, infiniteRepeatable(tween(2400, easing = LinearEasing)), label = "rot")
    val pulse by inf.animateFloat(0.6f, 1f, infiniteRepeatable(tween(2000, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "pulse")
    val busy = phase == Phase.SEARCHING || phase == Phase.STARTING
    val on = phase == Phase.CONNECTED
    val icon by animateColorAsState(if (on) NB.GoldLight else if (busy) NB.Gold else NB.Muted, tween(500), label = "ic")
    Box(
        Modifier.size(diameter).clip(CircleShape)
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null, onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) {
            val c = center; val r = size.minDimension / 2
            if (on) drawCircle(Brush.radialGradient(listOf(NB.Gold.copy(alpha = .34f * pulse), Color.Transparent), c, r), r)
            else if (busy) drawCircle(Brush.radialGradient(listOf(NB.Gold.copy(alpha = .14f), Color.Transparent), c, r), r)
            // outer hairline + ticks
            drawCircle(NB.Gold.copy(alpha = if (on) .55f else .22f), r * .93f, style = Stroke(1.dp.toPx()))
            for (i in 0 until 72) {
                rotate(i * 5f, c) {
                    val len = if (i % 6 == 0) 9.dp.toPx() else 4.dp.toPx()
                    drawLine(NB.Gold.copy(alpha = if (on) .55f else .22f), Offset(c.x, c.y - r * .93f + 7.dp.toPx()),
                        Offset(c.x, c.y - r * .93f + 7.dp.toPx() + len), 1.dp.toPx())
                }
            }
            // searching arc
            if (busy) rotate(rot, c) {
                drawArc(Brush.sweepGradient(listOf(Color.Transparent, NB.GoldLight, Color.Transparent), c), 0f, 120f, false,
                    Offset(c.x - r * .84f, c.y - r * .84f), Size(r * 1.68f, r * 1.68f), style = Stroke(3.dp.toPx(), cap = StrokeCap.Round))
            }
            // inner disc
            val ir = r * .70f
            drawCircle(Brush.radialGradient(listOf(Color(0xFF222733), Color(0xFF0A0C11)), Offset(c.x, c.y - ir * .3f), ir * 1.3f), ir)
            drawCircle(Brush.sweepGradient(listOf(NB.GoldDeep, NB.GoldLight, NB.GoldDeep, NB.GoldLight, NB.GoldDeep), c), ir,
                style = Stroke(if (on) 3.dp.toPx() else 2.dp.toPx()))
            drawCircle(Color.Black.copy(alpha = .5f), ir - 5.dp.toPx(), style = Stroke(1.dp.toPx()))
            // power icon
            val pr = ir * .36f; val sw = 4.dp.toPx()
            drawArc(icon, -58f, 296f, false, Offset(c.x - pr, c.y - pr), Size(pr * 2, pr * 2), style = Stroke(sw, cap = StrokeCap.Round))
            drawLine(icon, Offset(c.x, c.y - pr * 1.12f), Offset(c.x, c.y - pr * .12f), sw, StrokeCap.Round)
        }
    }
}

@Composable
private fun StatusBlock(ui: Ui) {
    val (title, hint, col) = when (ui.phase) {
        Phase.IDLE -> Triple(t("st_idle"), t("connect_hint"), NB.Text)
        Phase.SEARCHING -> Triple(t("st_finding"), t("cancel_hint"), NB.GoldLight)
        Phase.STARTING -> Triple(t("st_starting"), t("cancel_hint"), NB.GoldLight)
        Phase.CONNECTED -> Triple(t("st_ok"), t("disc_hint"), NB.GoldLight)
    }
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
        Text(title, color = col, fontSize = 26.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        if (ui.phase == Phase.SEARCHING && ui.total > 0) {
            LinearProgressIndicator(
                progress = { ui.done.toFloat() / ui.total }, color = NB.Gold, trackColor = NB.Stroke,
                modifier = Modifier.width(180.dp).height(3.dp).clip(CircleShape)
            )
            Spacer(Modifier.height(6.dp))
            Text("${ui.done} / ${ui.total}", color = NB.Muted, fontSize = 12.sp, letterSpacing = 1.sp)
        } else if (ui.phase == Phase.CONNECTED && ui.exit.isNotEmpty()) {
            Box(Modifier.clip(CircleShape).background(NB.Gold.copy(alpha = .10f)).border(1.dp, NB.Stroke, CircleShape).padding(horizontal = 14.dp, vertical = 6.dp)) {
                Text(ui.exit, color = NB.Gold, fontSize = 13.sp, letterSpacing = .5.sp)
            }
        } else Text(hint, color = NB.Muted, fontSize = 13.sp)
        if (ui.warn.isNotEmpty()) { Spacer(Modifier.height(8.dp)); Text(msgText(ui.warn), color = NB.Warn, fontSize = 12.sp, textAlign = TextAlign.Center) }
        if (ui.msg.isNotEmpty()) { Spacer(Modifier.height(8.dp)); Text(msgText(ui.msg), color = NB.Err, fontSize = 13.sp, textAlign = TextAlign.Center) }
    }
}

// ------------------------------------------------------------------ screen
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: Vm, ui: Ui, onOrb: () -> Unit) {
    val ctx = LocalContext.current
    val clipboard = LocalClipboardManager.current
    var sheet by remember { mutableStateOf("") }          // "" | servers | add | settings
    val focused = LocalWindowInfo.current.isWindowFocused
    var clipNow by remember { mutableStateOf("") }          // read while the MAIN window has focus (a bottom sheet is a separate window and cannot read it)

    val toast = { text: String -> Toast.makeText(ctx, text, Toast.LENGTH_SHORT).show() }
    val addedTxt = t("added"); val noneTxt = t("nothing_new"); val badTxt = t("no_valid"); val subTxt = t("sub_fail")
    val clipAddedTxt = t("clip_auto"); val emptyClipTxt = t("clip_empty")
    // a copied config is added by itself when the app comes to the front (Android only lets the focused window read the clipboard)
    LaunchedEffect(focused) {
        if (!focused) return@LaunchedEffect
        delay(300)
        var tx = clipboard.getText()?.text
        if (tx == null) { delay(700); tx = clipboard.getText()?.text }
        clipNow = tx ?: ""
        vm.autoClip(tx) { k, n -> if (k == "added") toast("$n $clipAddedTxt") }
    }
    val done: (String, Int) -> Unit = { k, n ->
        toast(when (k) { "added" -> "$n $addedTxt"; "nothing_new" -> noneTxt; "sub_fail" -> subTxt; else -> badTxt })
        if (k == "added") sheet = ""
    }

    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(NB.Bg0, Color(0xFF0B0E14), NB.Bg0)))
        .drawBehind {
            drawCircle(Brush.radialGradient(listOf(NB.Gold.copy(alpha = .09f), Color.Transparent),
                Offset(size.width / 2, size.height * .30f), size.width), size.width, Offset(size.width / 2, size.height * .30f))
        }) {
        Column(Modifier.fillMaxSize().systemBarsPadding().padding(horizontal = 22.dp, vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            // top bar
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Logo(32); Spacer(Modifier.width(10.dp))
                Column {
                    Text("NETBRIDGE", color = NB.GoldLight, fontFamily = FontFamily.Serif, fontSize = 18.sp, letterSpacing = 4.sp, fontWeight = FontWeight.Medium)
                    Text(t("tagline"), color = NB.Muted, fontSize = 11.sp, letterSpacing = 1.sp)
                }
                Spacer(Modifier.weight(1f))
                Box(Modifier.size(40.dp).clip(CircleShape).border(1.dp, NB.Stroke, CircleShape).clickable { sheet = "settings" }, contentAlignment = Alignment.Center) {
                    Text("⋯", color = NB.Gold, fontSize = 22.sp)
                }
            }
            Spacer(Modifier.weight(.55f))
            Orb(ui.phase, onOrb, (LocalConfiguration.current.screenHeightDp.dp - 490.dp).coerceIn(150.dp, 262.dp))
            Spacer(Modifier.height(20.dp))
            StatusBlock(ui)
            Spacer(Modifier.weight(1f))

            // route card
            val selName = ui.profiles.firstOrNull { profileKey(it) == ui.selected }?.s("name")
            Glass(Modifier.fillMaxWidth(), onClick = { if (ui.phase == Phase.IDLE) sheet = "servers" }) {
                Row(Modifier.padding(horizontal = 20.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(t("route"), color = NB.Muted, fontSize = 10.sp, letterSpacing = 2.sp)
                        Spacer(Modifier.height(2.dp))
                        Text(selName ?: t("auto"), color = NB.Text, fontSize = 16.sp, maxLines = 1, fontWeight = FontWeight.Medium)
                    }
                    Text("${ui.profiles.size} ${t("n_servers")}", color = NB.Muted, fontSize = 12.sp)
                    Spacer(Modifier.width(10.dp))
                    Text(if (LocalLang.current == "fa") "‹" else "›", color = NB.Gold, fontSize = 24.sp)
                }
            }
            Spacer(Modifier.height(12.dp))
            // add button (gold outline)
            Box(Modifier.fillMaxWidth().height(52.dp).clip(RoundedCornerShape(18.dp))
                .border(1.dp, GoldBrush, RoundedCornerShape(18.dp))
                .clickable(enabled = ui.phase == Phase.IDLE) {
                    val tx = (clipboard.getText()?.text ?: clipNow).trim()          // read now, while this window has focus
                    if (tx.isEmpty()) toast(emptyClipTxt) else vm.addText(tx, done)
                }, contentAlignment = Alignment.Center) {
                Text(t("add"), color = NB.GoldLight, fontSize = 15.sp, fontWeight = FontWeight.Medium, letterSpacing = .5.sp)
            }
            if (ui.profiles.isEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text(t("empty"), color = NB.Muted, fontSize = 12.sp, textAlign = TextAlign.Center)
            }
            Spacer(Modifier.height(6.dp))
            Text("v${BuildInfo.VERSION}", color = NB.Muted.copy(alpha = .6f), fontSize = 10.sp)
        }
    }

    if (sheet.isNotEmpty()) {
        ModalBottomSheet(
            onDismissRequest = { sheet = "" },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = Color(0xFF0F1219), contentColor = NB.Text,
            dragHandle = { Box(Modifier.padding(top = 10.dp, bottom = 6.dp).size(40.dp, 4.dp).clip(CircleShape).background(NB.Stroke)) }
        ) {
            when (sheet) {
                "servers" -> ServersSheet(vm, ui) { sheet = "" }
                "settings" -> SettingsSheet(vm, ui, toast)
            }
        }
    }
}

@Composable
private fun SheetTitle(text: String) =
    Text(text, color = NB.GoldLight, fontFamily = FontFamily.Serif, fontSize = 20.sp, letterSpacing = 1.sp,
        modifier = Modifier.padding(start = 24.dp, end = 24.dp, bottom = 12.dp, top = 4.dp))

@Composable
private fun ServersSheet(vm: Vm, ui: Ui, close: () -> Unit) {
    Column(Modifier.fillMaxWidth().navigationBarsPadding()) {
        SheetTitle(t("servers"))
        LazyColumn(Modifier.heightIn(max = (LocalConfiguration.current.screenHeightDp * 0.6f).dp), contentPadding = PaddingValues(horizontal = 18.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item(key = "auto") { ServerRow(t("auto"), "", null, ui.selected == "auto", false, { vm.select("auto"); close() }, {}) }
            val sorted = ui.profiles.sortedBy { p -> val d = if (p.has("delay")) p.optInt("delay") else null; if (d == null) 1_000_000 else if (d < 0) 2_000_000 else d }
            items(sorted, key = { profileKey(it) }) { p ->
                val key = profileKey(p)
                ServerRow(p.s("name").ifEmpty { p.s("server") }, "${p.s("type")} · ${p.s("network").ifEmpty { "tcp" }}",
                    if (p.has("delay")) p.optInt("delay") else null, ui.selected == key, true, { vm.select(key); close() }, { vm.delete(key) })
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun ServerRow(name: String, sub: String, ping: Int?, selected: Boolean, deletable: Boolean, onPick: () -> Unit, onDelete: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(if (selected) NB.Gold.copy(alpha = .09f) else NB.Bg1)
            .border(1.dp, if (selected) NB.Gold else NB.Stroke, shape).clickable(onClick = onPick).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(name, color = NB.Text, fontSize = 14.sp, maxLines = 1, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal)
            if (sub.isNotEmpty()) Text(sub, color = NB.Muted, fontSize = 11.sp)
        }
        if (ping != null) {
            val (txt, col) = if (ping < 0) "✗" to NB.Err else "$ping ms" to (if (ping < 800) NB.Ok else NB.Warn)
            Text(txt, color = col, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 8.dp))
        }
        if (deletable) Text("✕", color = NB.Muted, fontSize = 16.sp, modifier = Modifier.clip(CircleShape).clickable(onClick = onDelete).padding(8.dp))
    }
}

@Composable
private fun SettingsSheet(vm: Vm, ui: Ui, toast: (String) -> Unit) {
    val clipboard = LocalClipboardManager.current
    var confirm by remember { mutableStateOf(false) }
    var askFree by remember { mutableStateOf(false) }
    var freeBusy by remember { mutableStateOf(false) }
    val freeOk = t("free_ok"); val freeFail = t("free_fail")
    var askToken by remember { mutableStateOf(false) }
    var token by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf("") }
    val upd = t("updated"); val cp = t("copied")
    val okTxt = t("deploy_ok"); val failTxt = t("deploy_fail")
    Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 24.dp).padding(bottom = 28.dp)) {
        SheetTitle(t("settings"))
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(t("iran"), color = NB.Text, fontSize = 14.sp, modifier = Modifier.weight(1f))
            Switch(checked = ui.iran, onCheckedChange = { vm.setIran(it) }, colors = SwitchDefaults.colors(
                checkedThumbColor = NB.Bg0, checkedTrackColor = NB.Gold, uncheckedThumbColor = NB.Muted, uncheckedTrackColor = NB.Bg1, uncheckedBorderColor = NB.Stroke))
        }
        Divider2()
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(t("language"), color = NB.Text, fontSize = 14.sp, modifier = Modifier.weight(1f))
            for ((code, label) in listOf("fa" to "فارسی", "en" to "English")) {
                val sel = ui.lang == code
                Box(Modifier.padding(start = 8.dp).clip(CircleShape).background(if (sel) NB.Gold else Color.Transparent)
                    .border(1.dp, if (sel) NB.Gold else NB.Stroke, CircleShape).clickable { vm.setLang(code) }.padding(horizontal = 16.dp, vertical = 7.dp)) {
                    Text(label, color = if (sel) NB.Bg0 else NB.Text, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
        Divider2()
        Action(t("refresh_subs"), NB.Text) { vm.refreshSubs { toast("$it $upd") } }
        Action(if (freeBusy) t("free_busy") else t("free"), NB.Gold) { if (!freeBusy) askFree = true }
        Action(if (busy) t("deploy_busy") else t("deploy"), NB.Gold) { if (!busy) askToken = true }
        Action(t("report"), NB.Text) { clipboard.setText(AnnotatedString(vm.report())); toast(cp) }
        Action(t("delete_all"), NB.Err) { confirm = true }
        Spacer(Modifier.height(10.dp))
        Text("NetBridge ${BuildInfo.VERSION}", color = NB.Muted, fontSize = 11.sp, modifier = Modifier.align(Alignment.CenterHorizontally))
    }
    if (askFree) AlertDialog(
        onDismissRequest = { askFree = false }, containerColor = NB.Card,
        title = { Text(t("free"), color = NB.Text) },
        text = { Text(t("free_warn"), color = NB.Muted, fontSize = 13.sp) },
        confirmButton = { TextButton({
            askFree = false; freeBusy = true
            vm.getFreeConfigs { ok, text -> freeBusy = false; result = if (ok) "$text $freeOk" else "$freeFail\n$text" }
        }) { Text(t("yes"), color = NB.Gold) } },
        dismissButton = { TextButton({ askFree = false }) { Text(t("no"), color = NB.Muted) } })
    if (askToken) AlertDialog(
        onDismissRequest = { askToken = false }, containerColor = NB.Card,
        title = { Text(t("deploy"), color = NB.Text) },
        text = {
            Column {
                Text(t("deploy_help"), color = NB.Muted, fontSize = 13.sp)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = token, onValueChange = { token = it.trim() }, singleLine = true, label = { Text(t("deploy_token")) },
                    visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation())
            }
        },
        confirmButton = { TextButton({
            val tk = token; token = ""; askToken = false; busy = true
            vm.deployWorker(tk) { ok, text -> busy = false; result = if (ok) "$okTxt\n$text" else "$failTxt\n$text" }
        }) { Text(t("add_btn"), color = NB.Gold) } },
        dismissButton = { TextButton({ askToken = false; token = "" }) { Text(t("no"), color = NB.Muted) } })
    if (result.isNotEmpty()) AlertDialog(
        onDismissRequest = { result = "" }, containerColor = NB.Card,
        text = { Text(result, color = NB.Text, fontSize = 14.sp) },
        confirmButton = { TextButton({ result = "" }) { Text(t("close"), color = NB.Gold) } })
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false }, containerColor = NB.Card,
        title = { Text(t("confirm_del"), color = NB.Text) },
        confirmButton = { TextButton({ vm.deleteAll(); confirm = false }) { Text(t("yes"), color = NB.Err) } },
        dismissButton = { TextButton({ confirm = false }) { Text(t("no"), color = NB.Gold) } })
}

@Composable
private fun Divider2() = Box(Modifier.fillMaxWidth().height(1.dp).background(NB.Stroke))

@Composable
private fun Action(text: String, color: Color, onClick: () -> Unit) =
    Text(text, color = color, fontSize = 14.sp, modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 14.dp))
