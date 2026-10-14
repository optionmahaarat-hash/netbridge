# ساخت APK و Setup.exe روی گیت‌هاب (قدم‌به‌قدم)

## ۱) ساخت مخزن (حتماً Private)
چون داخل پروژه کانفیگ‌های شما هست (`assets/seed_profiles.json`)، مخزن باید **خصوصی** باشد.
1. github.com ← New repository ← نام دلخواه (مثلاً `netbridge`) ← **Private** ← Create.
2. «uploading an existing file» را بزنید و **محتوای** پوشهٔ `NetBridge` را (نه خودِ پوشه) بکشید داخلش، شامل پوشه‌های مخفی `.github` و فایل `.gitignore`. (اگر مخفی‌ها دیده نمی‌شوند، در Windows: View ← Hidden items.)
   - یا با Git:  
     `git init && git add . && git commit -m init && git branch -M main && git remote add origin <آدرس مخزن> && git push -u origin main`
3. پوشه‌های `keys`، `data`، `cores` را **آپلود نکنید** (`.gitignore` خودش جلویشان را می‌گیرد).

## ۲) ساخت APK اندروید
GitHub ← تب **Actions** ← **build-android** ← **Run workflow** ← صبر (حدود ۱۰–۱۵ دقیقه).  
بعد از سبز شدن، پایین صفحهٔ اجرا در **Artifacts** این‌ها هست:
- **NetBridge-apk** ← فایل `NetBridge.apk` (به خانواده بدهید).
- **signing-key-KEEP-SAFE** ← `release.jks` (کلید امضا؛ **نگه‌داری کنید**).

### برای اینکه آپدیت‌های بعدی روی نسخهٔ قبلی نصب شوند
کلید را یک بار در Secrets بگذارید:
1. `release.jks` را دانلود کنید.
2. Windows PowerShell:  
   `[Convert]::ToBase64String([IO.File]::ReadAllBytes("release.jks")) | Set-Clipboard`
3. مخزن ← Settings ← Secrets and variables ← Actions ← New repository secret ← نام: `ANDROID_KEYSTORE_B64` ← مقدار: همان متن کپی‌شده.

## ۳) ساخت Setup.exe ویندوز (اختیاری، به‌جای ساخت روی کامپیوتر خودتان)
Actions ← **build-installer** ← Run workflow ← خروجی در Artifacts (`NetBridgeLite-Setup-*.exe`).  
(برای آپدیت امضاشدهٔ ویندوز، محتوای `keys/update_private.key` را با نام `UPDATE_PRIVATE_KEY` در Secrets بگذارید.)

## اگر خطا داد
روی اجرای قرمز کلیک کنید ← مرحله‌ای که قرمز است ← ۳۰ خط آخر لاگ را برایم بفرستید.
