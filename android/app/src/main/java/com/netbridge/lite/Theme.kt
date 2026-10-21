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
    "clip_empty" to ("کلیپ‌بورد خالی است؛ اول کانفیگ را کپی کنید" to "Clipboard is empty - copy a config first"),
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
    "free" to ("دریافت کانفیگ رایگان (عمومی)" to "Get free configs (public)"),
    "free_auto" to ("به‌روزرسانی روزانه کانفیگ رایگان (هنگام باز شدن)" to "Refresh free configs daily (when the app opens)"),
    "free_busy" to ("در حال دریافت..." to "Downloading..."),
    "free_ok" to ("سرور تازه اضافه شد. حالا روی «خودکار» وصل شوید تا بهترین پیدا شود." to "new server(s) added. Now connect on Auto to find the best one."),
    "free_fail" to ("دریافت ناموفق بود:" to "Could not download:"),
    "free_warn" to ("این سرورها مال دیگران است و ترافیک شما از آن‌ها رد می‌شود؛ برای بانک و حساب‌های شخصی استفاده نکنید. ادامه؟" to "These servers belong to other people and your traffic passes through them - do not use them for banking or private accounts. Continue?"),
    "deploy" to ("ساخت Worker شخصی (Cloudflare)" to "Deploy my Worker (Cloudflare)"),
    "deploy_help" to ("یک رله خصوصی روی حساب رایگان کلودفلر خودتان ساخته می‌شود.\n۱) در cloudflare.com وارد شوید.\n۲) My Profile ← API Tokens ← Create Token ← قالب «Edit Cloudflare Workers».\n۳) توکن را اینجا بچسبانید (ذخیره نمی‌شود).\nبرای ساخت، اینترنت بدون فیلتر لازم است." to
        "Creates a private relay on YOUR free Cloudflare account.\n1) Sign in at cloudflare.com.\n2) My Profile > API Tokens > Create Token > 'Edit Cloudflare Workers' template.\n3) Paste the token here (it is not saved).\nNeeds an unfiltered connection while creating."),
    "deploy_token" to ("توکن API" to "API token"),
    "deploy_busy" to ("در حال ساخت... چند ثانیه صبر کنید" to "Creating... wait a few seconds"),
    "deploy_ok" to ("ساخته و اضافه شد. ممکن است یک دقیقه طول بکشد تا جواب دهد:" to "Created and added. It may take a minute to start answering:"),
    "deploy_fail" to ("ساخت ناموفق بود:" to "Could not create it:"),
    "fw" to ("فایروال اپراتور" to "Operator firewall"),
    "fw_auto" to ("نامعلوم" to "Unknown"),
    "fw_mci" to ("همراه اول (ECH اول)" to "MCI (ECH first)"),
    "fw_irancell" to ("ایرانسل (Fragment اول)" to "Irancell (Fragment first)"),
    "fw_help" to ("سیم‌کارت همراه اول ممکن است فایروال ایرانسل داشته باشد و برعکس. اگر یکی جواب نداد، دیگری را امتحان کنید." to "A MCI SIM can sit behind the Irancell firewall and the other way round. If one does not work, try the other."),
    "tg" to ("پروکسی تلگرام (Worker شخصی)" to "Telegram proxy (my Worker)"),
    "tg_help" to ("یک پروکسی وب تلگرام روی حساب رایگان کلودفلر خودتان ساخته می‌شود (Worker متن‌باز ToiCF؛ همراه برنامه نیست و هنگام ساخت دانلود می‌شود).\nتوکن: همان قالب «Edit Cloudflare Workers» با Zone Resources = All zones.\nنکته: آدرس workers.dev در بعضی شبکه‌ها فیلتر است؛ با یک دامنهٔ اصلی روی کلودفلر (مثل example.com) جواب می‌دهد. دامنهٔ فرعی مجاز نیست.\nتوکن ذخیره نمی‌شود؛ بعد از کار آن را در کلودفلر حذف کنید." to
        "Creates a Telegram web proxy on YOUR free Cloudflare account (open-source ToiCF Worker; not bundled, downloaded when you press Create).\nToken: the 'Edit Cloudflare Workers' template with Zone Resources = All zones.\nNote: workers.dev is filtered on some networks; a ROOT domain on Cloudflare (like example.com) works. Sub-domains are not accepted as zones.\nThe token is never saved; delete it in Cloudflare afterwards."),
    "tg_zones" to ("بارگیری دامنه‌های من" to "Load my domains"),
    "tg_nodomain" to ("بدون دامنه (فقط workers.dev)" to "No domain (workers.dev only)"),
    "tg_label" to ("دامنهٔ فرعی" to "Sub-domain"),
    "tg_create" to ("ساخت" to "Create"),
    "tg_busy" to ("در حال ساخت و بررسی... ممکن است نیم دقیقه طول بکشد" to "Creating and checking... may take half a minute"),
    "tg_ok" to ("ساخته شد. لینک را در تلگرام باز کنید:" to "Created. Open this link in Telegram:"),
    "tg_health_fail" to ("هنوز جواب نمی‌دهد (کمی بعد دوباره امتحان کنید؛ اگر آدرس workers.dev است شاید شبکهٔ شما آن را می‌بندد):" to "Not answering yet (try again in a minute; if it is a workers.dev address your network may block it):"),
    "tg_open" to ("باز کردن" to "Open"),
    "tg_copy" to ("کپی لینک" to "Copy link"),
    "tg_last" to ("آخرین لینک:" to "Last link:"),
    "close" to ("بستن" to "Close"),
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
