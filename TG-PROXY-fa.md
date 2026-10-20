# پروکسی تلگرام در NetBridge

ساخت یک وب‌پروکسی تلگرام روی حساب کلودفلر خودت (Tools ← Telegram proxy).

## پیش‌نیاز
1. حساب رایگان کلودفلر و توکن با قالب **Edit Cloudflare Workers** (شامل Zone Read).
2. (توصیه‌شده) یک دامنه تمیز که مال خودت باشد، مثلاً دامنه رایگان از my.dnshe.com. در کلودفلر Add a site بزن و nameserverهای دامنه را به دو nameserver کلودفلر تغییر بده تا وضعیت Active شود.
3. آدرس workers.dev اغلب فیلتر است؛ بدون دامنه ممکن است لینک کار نکند.

## مراحل
Telegram proxy ← توکن ← Load my domains ← دامنه و ساب‌دامین (پیش‌فرض tg) ← Create the proxy. برنامه Worker را دانلود و با SECRET و BOOT تصادفی مستقر می‌کند، دامنه را وصل و `/health` را بررسی می‌کند و لینک `https://t.me/webproxy?server=...&secret=...` را می‌دهد.

## مجوز
Worker از ToiCF/CF-Workers-TGProxy (GPL-3.0) است و در NetBridge قرار نگرفته؛ هر بار هنگام ساخت دانلود می‌شود.

## حریم خصوصی
توکن کلودفلر ذخیره نمی‌شود. فقط لینک و رمزها در data/tg_proxy.json ماندگار است.

## هنوز تست نشده
روی شبکه واقعی آزموده نشده است.
