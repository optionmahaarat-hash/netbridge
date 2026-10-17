# Google Script در NetBridge

راهنمای کامل داخل برنامه است (منوی Help ← Guide، تب «Google Script (رله گوگل)»).
کد اسکریپت: `assets/gscript/Code.gs` (کد اصلی خودمان، MIT). هسته: `app/core/gscript.py`.
پروتکل: برنامه JSON `{k: کلید, m: متد, u: آدرس, h: هدرها, b: بدنه base64}` را POST می‌کند؛ اسکریپت با UrlFetchApp می‌گیرد و `{s, h, b}` برمی‌گرداند.
اتصال به گوگل با SNI = www.google.com انجام می‌شود و گواهی گوگل کامل بررسی می‌شود.
محدودیت: فقط وب (۸۰ و ۴۴۳)، بدون WebSocket/UDP، کند، سهمیه روزانه گوگل، و نیاز به گواهی محلی (ca.pem) برای HTTPS.
