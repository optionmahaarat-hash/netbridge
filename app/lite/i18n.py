"""Two languages. Persian is the default (family app)."""
T = {
 "app": ("نت‌بریج لایت", "NetBridge Lite"),
 "connect": ("اتصال", "CONNECT"),
 "disconnect": ("قطع اتصال", "DISCONNECT"),
 "cancel": ("لغو", "CANCEL"),
 "st_idle": ("متصل نیستید", "Not connected"),
 "st_finding": ("در حال یافتن سریع‌ترین سرور… {done}/{total}", "Finding the fastest server… {done}/{total}"),
 "st_starting": ("در حال اتصال…", "Connecting…"),
 "st_ok": ("متصل شدید ✓", "Connected ✓"),
 "st_exit": ("{ip} · {country}", "{ip} · {country}"),
 "st_noinet": ("وصل شد، ولی اینترنت پاسخ نمی‌دهد. «خودکار» را امتحان کنید یا کانفیگ جدید اضافه کنید.",
               "Connected, but the internet does not answer. Try “Auto” or add a new config."),
 "server": ("سرور:", "Server:"),
 "auto": ("خودکار (سریع‌ترین)", "Auto (fastest)"),
 "add": ("＋ افزودن کانفیگ", "＋ Add config"),
 "add_clip": ("از کلیپ‌بورد", "From clipboard"),
 "add_paste": ("چسباندن لینک / اشتراک…", "Paste link / subscription…"),
 "add_file": ("از فایل…", "From file…"),
 "clip_found": ("{n} کانفیگ در کلیپ‌بورد پیدا شد", "{n} config(s) found in the clipboard"),
 "clip_add": ("افزودن", "Add"),
 "iran": ("سایت‌های ایرانی مستقیم باز شوند", "Open Iranian sites directly"),
 "sysproxy": ("تنظیم خودکار پروکسی ویندوز", "Set the Windows proxy automatically"),
 "empty": ("هنوز سروری اضافه نکرده‌اید.\nلینک کانفیگ را کپی کنید و «افزودن کانفیگ» را بزنید.",
           "No servers yet.\nCopy your config link, then press “Add config”."),
 "n_servers": ("{n} سرور", "{n} server(s)"),
 "added": ("{n} سرور اضافه شد", "{n} server(s) added"),
 "added_dup": ("{n} سرور اضافه شد ({d} تکراری)", "{n} server(s) added ({d} duplicate)"),
 "nothing_new": ("سرور تازه‌ای پیدا نشد (همه قبلاً اضافه شده‌اند)", "Nothing new (all already added)"),
 "no_valid": ("لینک معتبری پیدا نشد.", "No valid config found."),
 "sub_fail": ("دریافت اشتراک ناموفق بود. اگر آدرس فیلتر است، ابتدا با کانفیگ دیگری وصل شوید.\n\n{err}",
              "Could not download the subscription. If the address is blocked, connect with another config first.\n\n{err}"),
 "sub_updated": ("اشتراک‌ها به‌روز شد: {n} سرور", "Subscriptions updated: {n} server(s)"),
 "no_subs": ("اشتراکی ثبت نشده است.", "No subscriptions saved."),
 "all_dead": ("هیچ سروری جواب نداد.\nاینترنت را بررسی کنید یا کانفیگ جدید اضافه کنید.",
              "No server answered.\nCheck your internet or add a new config."),
 "start_fail": ("اتصال برقرار نشد:\n{err}", "Could not connect:\n{err}"),
 "no_core": ("فایل هسته (xray) پیدا نشد:\n{p}", "Core file (xray) not found:\n{p}"),
 "menu": ("⋯", "⋯"),
 "m_refresh": ("به‌روزرسانی اشتراک‌ها", "Refresh subscriptions"),
 "m_test": ("تست سرورها", "Test servers"),
 "m_del": ("حذف سرور انتخاب‌شده", "Delete selected server"),
 "m_del_all": ("حذف همه سرورها", "Delete all servers"),
 "m_update": ("بررسی به‌روزرسانی برنامه", "Check for app updates"),
 "m_lang": ("English", "فارسی"),
 "m_report": ("گزارش (برای پشتیبانی)", "Report (for support)"),
 "m_about": ("درباره", "About"),
 "pick_server": ("ابتدا یک سرور مشخص انتخاب کنید.", "Pick a specific server first."),
 "confirm_del_all": ("همه سرورها حذف شوند؟", "Delete all servers?"),
 "test_done": ("{ok} سرور از {n} سرور پاسخ داد", "{ok} of {n} servers answered"),
 "testing": ("در حال تست… {done}/{total}", "Testing… {done}/{total}"),
 "upd_new": ("نسخه {v} آماده است", "Version {v} is available"),
 "upd_btn": ("به‌روزرسانی", "Update"),
 "upd_none": ("برنامه به‌روز است ✓", "You are up to date ✓"),
 "upd_fail": ("بررسی به‌روزرسانی ناموفق بود:\n{err}", "Update check failed:\n{err}"),
 "upd_nourl": ("آدرس به‌روزرسانی تنظیم نشده است.", "Update address is not set."),
 "upd_dl": ("در حال دانلود به‌روزرسانی… {pct}٪", "Downloading update… {pct}%"),
 "upd_ask": ("نسخه {v} نصب شود؟\n\nبرنامه بسته و دوباره باز می‌شود.\n\n{notes}",
             "Install version {v}?\n\nThe app will close and reopen.\n\n{notes}"),
 "upd_frozen": ("نصب خودکار فقط در نسخه نصب‌شده ویندوز کار می‌کند.", "Automatic install only works in the installed Windows build."),
 "upd_failed_prev": ("آخرین به‌روزرسانی انجام نشد. برنامه با نسخه قبلی باز شد.", "The last update could not be installed. The previous version was kept."),
 "already_running": ("برنامه از قبل در حال اجراست.", "The app is already running."),
 "report_title": ("گزارش", "Report"),
 "copy": ("کپی", "Copy"),
 "close": ("بستن", "Close"),
 "st_tls": ("سرورها بدون TLS هستند؛ در حال جست‌وجوی پورت TLS… {done}/{total}", "Servers have no TLS; looking for a TLS port… {done}/{total}"),
 "tls_none": ("هیچ سروری جواب نداد.\nسرورهای بدون TLS پورت TLS هم ندارند؛ TLS را فقط خود سرور می‌تواند بدهد.\nکانفیگ دیگری (با TLS یا Reality) اضافه کنید.",
              "No server answered.\nThe servers without TLS offer no TLS port either; only the server itself can provide TLS.\nAdd another config (TLS or Reality)."),
 "m_tls": ("تبدیل سرورهای بدون TLS به TLS", "Convert non-TLS servers to TLS"),
 "tls_done": ("{n} سرور به TLS تبدیل شد", "{n} server(s) converted to TLS"),
 "tls_nothing": ("هیچ سرور بدون TLS که پورت TLS داشته باشد پیدا نشد.", "No non-TLS server with a working TLS port was found."),
 "tls_no_plain": ("سرور بدون TLS ندارید.", "You have no non-TLS servers."),
 "warn_relaxed": ("وصل شد، ولی هیچ سروری تست یوتیوب/اینستاگرام را پاس نکرد؛ ممکن است بعضی سایت‌ها باز نشوند. کمی بعد دوباره امتحان کنید.",
                  "Connected, but no server passed the YouTube/Instagram check; some sites may not open. Try again later."),
 "warn_plain": ("هشدار: فقط سرورهای بدون رمزنگاری جواب دادند.", "Warning: only unencrypted servers answered."),
 "ping_ms": ("{ms} ms", "{ms} ms"),
}
_lang = "fa"


def set_lang(lang):
    global _lang
    _lang = lang if lang in ("fa", "en") else "fa"


def lang():
    return _lang


def tr(key, **kw):
    fa, en = T[key]
    s = fa if _lang == "fa" else en
    return s.format(**kw) if kw else s
