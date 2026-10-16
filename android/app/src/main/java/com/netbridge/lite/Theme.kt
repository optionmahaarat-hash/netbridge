package com.netbridge.lite

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.platform.LocalLayoutDirection

/** Black + champagne gold. */
object NB {
    val Bg0 = Color(0xFF07080B)
    val Bg1 = Color(0xFF0E1117)
    val Card = Color(0xFF12151D)
    val Stroke = Color(0x33D9B36C)
    val StrokeStrong = Color(0x66D9B36C)
    val Gold = Color(0xFFD9B36C)
    val GoldLight = Color(0xFFF3DDA4)
    val GoldDeep = Color(0xFFA8803A)
    val Text = Color(0xFFF4EFE6)
    val Muted = Color(0xFF8C877C)
    val Ok = Color(0xFF5BD6A0)
    val Warn = Color(0xFFE8A94A)
    val Err = Color(0xFFE5646B)
}

val LocalLang = compositionLocalOf { "fa" }

private val S: Map<String, Pair<String, String>> = mapOf(
    "tagline" to ("اتصال امن و آسان" to "Private. Effortless."),
    "connect_hint" to ("برای اتصال ضربه بزنید" to "Tap to connect"),
    "cancel_hint" to ("برای لغو ضربه بزنید" to "Tap to cancel"),
    "disc_hint" to ("برای قطع اتصال ضربه بزنید" to "Tap to disconnect"),
    "st_idle" to ("متصل نیستید" to "Not connected"),
    "st_finding" to ("در حال یافتن بهترین مسیر" to "Finding the best route"),
    "st_starting" to ("در حال برقراری اتصال" to "Establishing connection"),
    "st_ok" to ("متصل شدید" to "Connected"),
    "route" to ("مسیر" to "ROUTE"),
    "auto" to ("خودکار · سریع‌ترین" to "Auto · fastest"),
    "add" to ("＋  افزودن کانفیگ" to "＋  Add config"),
    "add_title" to ("افزودن کانفیگ" to "Add config"),
    "add_hint" to ("لینک کانفیگ یا لینک اشتراک را بچسبانید" to "Paste a config link or subscription link"),
    "paste" to ("چسباندن از کلیپ‌بورد" to "Paste from clipboard"),
    "add_btn" to ("افزودن" to "Add"),
    "servers" to ("سرورها" to "Servers"),
    "n_servers" to ("سرور" to "servers"),
    "empty" to ("هنوز سروری ندارید. لینک کانفیگ را کپی کنید و «افزودن کانفیگ» را بزنید." to "No servers yet. Copy your config link and tap “Add config”."),
    "added" to ("سرور اضافه شد" to "server(s) added"),
    "nothing_new" to ("سرور تازه‌ای پیدا نشد" to "Nothing new found"),
    "no_valid" to ("لینک معتبری پیدا نشد" to "No valid config found"),
    "sub_fail" to ("دریافت اشتراک ناموفق بود" to "Could not download the subscription"),
    "all_dead" to ("هیچ سروری جواب نداد. اینترنت را بررسی کنید یا کانفیگ جدید اضافه کنید." to "No server answered. Check your internet or add a new config."),
    "st_noinet" to ("وصل شد، ولی اینترنت پاسخ نمی‌دهد" to "Connected, but the internet does not answer"),
    "warn_relaxed" to ("هیچ سروری تست یوتیوب/اینستاگرام را پاس نکرد؛ ممکن است بعضی سایت‌ها باز نشوند" to "No server passed the YouTube/Instagram check; some sites may not open"),
    "warn_plain" to ("هشدار: فقط سرورهای بدون رمزنگاری جواب دادند" to "Warning: only unencrypted servers answered"),
    "start_fail" to ("اتصال برقرار نشد" to "Could not connect"),
    "clip_found" to ("کانفیگ در کلیپ‌بورد پیدا شد" to "config(s) found in the clipboard"),
    "clip_auto" to ("سرور از کلیپ‌بورد اضافه شد" to "server(s) added from the clipboard"),
    "clip_add" to ("افزودن" to "Add"),
    "settings" to ("تنظیمات" to "Settings"),
    "iran" to ("سایت‌های ایرانی مستقیم باز شوند" to "Open Iranian sites directly"),
    "language" to ("زبان" to "Language"),
    "refresh_subs" to ("به‌روزرسانی اشتراک‌ها" to "Refresh subscriptions"),
    "delete_all" to ("حذف همه سرورها" to "Delete all servers"),
    "confirm_del" to ("همه سرورها حذف شوند؟" to "Delete all servers?"),
    "yes" to ("بله" to "Yes"),
    "no" to ("خیر" to "No"),
    "report" to ("کپی گزارش (برای پشتیبانی)" to "Copy report (for support)"),
    "copied" to ("کپی شد" to "Copied"),
    "updated" to ("سرور به‌روز شد" to "server(s) updated"),
)

@Composable
fun t(key: String): String {
    val e = S[key] ?: return key
    return if (LocalLang.current == "fa") e.first else e.second
}

/** message from the view-model: a known key or raw text */
@Composable
fun msgText(m: String): String = if (S.containsKey(m)) t(m) else m

@Composable
fun NBTheme(lang: String, content: @Composable () -> Unit) {
    val scheme = darkColorScheme(
        primary = NB.Gold, onPrimary = NB.Bg0, background = NB.Bg0, onBackground = NB.Text,
        surface = NB.Card, onSurface = NB.Text, surfaceVariant = NB.Bg1, onSurfaceVariant = NB.Muted,
        outline = NB.Stroke, secondary = NB.GoldLight
    )
    MaterialTheme(colorScheme = scheme) {
        CompositionLocalProvider(
            LocalLayoutDirection provides (if (lang == "fa") LayoutDirection.Rtl else LayoutDirection.Ltr),
            LocalLang provides lang
        ) { content() }
    }
}
