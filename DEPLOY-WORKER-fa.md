# ساخت Worker شخصی با یک کلیک

۱. در cloudflare.com وارد شو (حساب رایگان کافی است).
۲. My Profile ← API Tokens ← Create Token ← قالب **Edit Cloudflare Workers** ← ساخت و کپی توکن.
۳. در NetBridge دکمه «Deploy my Worker (Cloudflare)» را بزن و توکن را بچسبان.
۴. برنامه ورکر را می‌سازد، آدرس workers.dev را فعال می‌کند و پروفایل VLESS را به لیست اضافه می‌کند.

نکته‌ها: توکن ذخیره نمی‌شود. ساخت باید با اینترنت بدون فیلتر به api.cloudflare.com انجام شود (یا از اتصال فعلی NetBridge).
ورکر فقط TCP را رد می‌کند (UDP/QUIC خیر). کد ورکر: assets/worker/vless_worker.js (کد اصلی خودمان، MIT).
محدودیت رایگان کلودفلر: ۱۰۰ هزار درخواست در روز.
