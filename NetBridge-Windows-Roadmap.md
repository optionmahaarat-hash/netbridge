# NetBridge — Windows Personal Client
## Roadmap ساخت نسخه شخصی ویندوزی بر پایه قابلیت‌های PattNG

> نام پیشنهادی پروژه: **NetBridge**
>
> هدف: ساخت یک کلاینت شخصی Windows با رابط گرافیکی Python/PySide6 که قابلیت‌های موردنیاز PattNG/v2rayNG را برای استفاده شخصی ارائه کند.
>
> این پروژه برای استفاده شخصی طراحی می‌شود و هدف انتشار عمومی یا ساخت فایل اجرایی در مرحله اول نیست.

---

## 1. تصمیمات پایه

- [ ] نام پروژه نهایی: `NetBridge`
- [ ] پلتفرم هدف: Windows 10/11
- [ ] رابط کاربری: Python + PySide6
- [ ] هسته اتصال: Xray Core در مرحله اول
- [ ] معماری: GUI جدا از Core
- [ ] ذخیره پروفایل‌ها به‌صورت محلی
- [ ] اجرای برنامه با `python main.py` در زمان توسعه
- [ ] عدم تمرکز روی ساخت EXE در نسخه‌های اولیه
- [ ] نگهداری سورس PattNG به‌عنوان مرجع قابلیت‌ها و رفتارها
- [ ] رعایت مجوز و الزامات GPL برای هر بخش کدی که مستقیماً از پروژه GPL استفاده شود

---

## 2. هدف نسخه اول (MVP)

- [ ] اجرای GUI بدون نیاز به Android
- [ ] افزودن VLESS
- [ ] افزودن VMess
- [ ] افزودن Trojan
- [ ] افزودن Shadowsocks در صورت پشتیبانی Core انتخاب‌شده
- [ ] Paste کردن لینک کانفیگ
- [ ] Import از فایل
- [ ] ذخیره پروفایل
- [ ] ویرایش پروفایل
- [ ] حذف پروفایل
- [ ] فعال/غیرفعال کردن اتصال
- [ ] نمایش وضعیت اتصال
- [ ] نمایش Log
- [ ] کپی لینک کانفیگ
- [ ] تست تأخیر/دسترسی
- [ ] System Proxy ویندوز

---

## 3. ساختار پیشنهادی پروژه

```text
NetBridge/
│
├── main.py
├── requirements.txt
├── README.md
│
├── app/
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── profile_dialog.py
│   │   ├── settings_window.py
│   │   └── log_window.py
│   │
│   ├── core/
│   │   ├── xray_manager.py
│   │   ├── process_manager.py
│   │   └── config_generator.py
│   │
│   ├── protocols/
│   │   ├── vless.py
│   │   ├── vmess.py
│   │   ├── trojan.py
│   │   └── shadowsocks.py
│   │
│   ├── network/
│   │   ├── proxy.py
│   │   ├── connectivity.py
│   │   └── latency.py
│   │
│   ├── storage/
│   │   ├── profiles.py
│   │   └── settings.py
│   │
│   └── utils/
│       ├── parser.py
│       ├── validator.py
│       └── logger.py
│
├── cores/
│   └── xray/
│
├── configs/
│
├── data/
│   ├── profiles.json
│   └── settings.json
│
└── tests/
```

---

## 4. رابط گرافیکی

### پنجره اصلی

- [ ] Sidebar یا Tab برای پروفایل‌ها
- [ ] نمایش نام پروفایل
- [ ] نمایش نوع پروتکل
- [ ] نمایش وضعیت اتصال
- [ ] دکمه Connect
- [ ] دکمه Disconnect
- [ ] دکمه Add
- [ ] دکمه Edit
- [ ] دکمه Delete
- [ ] دکمه Test
- [ ] نمایش آخرین خطای اتصال
- [ ] نمایش سرعت/ترافیک در صورت امکان

### پنجره افزودن کانفیگ

- [ ] Paste Config
- [ ] Import File
- [ ] Import URL
- [ ] تشخیص خودکار نوع لینک
- [ ] Parse
- [ ] نمایش فیلدهای استخراج‌شده
- [ ] ذخیره پروفایل

### تنظیمات پیشرفته

- [ ] Address
- [ ] Port
- [ ] UUID / Password
- [ ] Network
- [ ] Security
- [ ] SNI
- [ ] Host
- [ ] Path
- [ ] Fingerprint
- [ ] ALPN
- [ ] Flow
- [ ] Cipher Suites
- [ ] Fragment
- [ ] سایر گزینه‌های قابل پشتیبانی توسط Core

---

## 5. مدیریت Xray

- [ ] قرار دادن Xray Core در پوشه `cores/xray`
- [ ] ساخت Config موقت برای هر اتصال
- [ ] Validate کردن Config قبل از اجرا
- [ ] اجرای Xray به‌صورت subprocess
- [ ] گرفتن stdout/stderr
- [ ] نمایش Log در GUI
- [ ] تشخیص Crash
- [ ] Stop صحیح Process
- [ ] جلوگیری از اجرای هم‌زمان چند Core
- [ ] پاک‌سازی Config موقت

---

## 6. پروفایل‌ها

هر پروفایل حداقل شامل:

```json
{
  "name": "My Profile",
  "type": "vless",
  "server": "...",
  "port": 443,
  "uuid": "...",
  "network": "ws",
  "security": "tls",
  "sni": "...",
  "host": "...",
  "path": "..."
}
```

- [ ] ذخیره محلی
- [ ] Backup
- [ ] Restore
- [ ] Export
- [ ] Import
- [ ] نام دلخواه
- [ ] پروفایل پیش‌فرض
- [ ] مرتب‌سازی

---

## 7. قابلیت‌های خاص PattNG

این بخش بعد از MVP پیاده‌سازی می‌شود.

- [ ] Fingerprint
- [ ] `unsafe`
- [ ] Cipher Suites
- [ ] Fragment
- [ ] TLSHello Fragment
- [ ] تنظیمات TCP
- [ ] WebSocket
- [ ] گزینه‌های TLS
- [ ] بررسی رفتار Configهای خاص PattNG
- [ ] تطبیق خروجی Config با ساختار مورد انتظار Xray

> توجه: Fragment و تنظیمات مشابه، رمزنگاری جدید ایجاد نمی‌کنند؛ آن‌ها نحوه ارسال/ساختار ترافیک را تغییر می‌دهند و رفتارشان به شبکه و تجهیزات مسیر وابسته است.

---

## 8. System Proxy

- [ ] تشخیص وضعیت Proxy ویندوز
- [ ] فعال کردن Proxy هنگام Connect
- [ ] خاموش کردن Proxy هنگام Disconnect
- [ ] Restore تنظیمات قبلی
- [ ] جلوگیری از باقی ماندن Proxy بعد از Crash
- [ ] گزینه Enable/Disable دستی

---

## 9. TUN Mode — مرحله بعد

این بخش را بعد از پایدار شدن System Proxy انجام می‌دهیم.

- [ ] بررسی نیاز به TUN
- [ ] طراحی Service/Helper جداگانه
- [ ] مدیریت دسترسی Administrator
- [ ] Routing
- [ ] DNS
- [ ] IPv4/IPv6
- [ ] Kill Switch در صورت نیاز
- [ ] تست مرورگر
- [ ] تست برنامه‌های غیرمرورگری

---

## 10. Subscription

- [ ] دریافت Subscription URL
- [ ] Parse محتوای Subscription
- [ ] تشخیص نوع کانفیگ
- [ ] ذخیره محلی
- [ ] Update دستی
- [ ] Update خودکار اختیاری
- [ ] حذف پروفایل‌های قدیمی
- [ ] جلوگیری از Duplicate

---

## 11. تست

### Unit Test

- [ ] VLESS parser
- [ ] VMess parser
- [ ] Trojan parser
- [ ] URI parser
- [ ] Config generator
- [ ] Validator

### Integration Test

- [ ] Start Xray
- [ ] Stop Xray
- [ ] اتصال موفق
- [ ] اتصال ناموفق
- [ ] Timeout
- [ ] Invalid Config
- [ ] تغییر پروفایل
- [ ] Restore Proxy

### Network Test

- [ ] Browser
- [ ] DNS
- [ ] HTTPS
- [ ] WebSocket
- [ ] TLS
- [ ] IPv4
- [ ] IPv6

---

## 12. امنیت و حریم خصوصی

- [ ] UUID/Password در Log نمایش داده نشود
- [ ] امکان Mask کردن Secrets
- [ ] فایل پروفایل با دسترسی مناسب ذخیره شود
- [ ] اطلاعات حساس در Exceptionها چاپ نشود
- [ ] Core فقط با Config تولیدشده برنامه اجرا شود
- [ ] دانلود Core فقط از منبع مورد اعتماد انجام شود
- [ ] Subscriptionهای ناشناس به‌صورت کورکورانه اجرا نشوند

---

## 13. ظاهر برنامه

پیشنهاد اولیه:

```text
┌──────────────────────────────────────────┐
│ NetBridge                         ⚙      │
├──────────────┬───────────────────────────┤
│ Profiles     │  My Profile               │
│              │                           │
│ ● Server 01  │  Status: Connected       │
│ ○ Server 02  │  Protocol: VLESS         │
│ ○ Server 03  │  Server: example.com     │
│              │                           │
│ + Add        │  [ CONNECT ]              │
│              │  [ TEST ]                 │
│              │                           │
│              │  Traffic / Logs           │
└──────────────┴───────────────────────────┘
```

---

## 14. فناوری پیشنهادی

### GUI

```text
Python
PySide6
```

### Backend

```text
Xray Core
Python subprocess
```

### Storage

```text
JSON
```

در صورت بزرگ شدن پروژه:

```text
SQLite
```

---

## 15. ترتیب اجرای واقعی پروژه

### Phase 1 — Skeleton

- [ ] ایجاد پروژه
- [ ] نصب Python
- [ ] نصب PySide6
- [ ] ساخت Main Window
- [ ] ساخت ساختار پوشه‌ها
- [ ] Logger

### Phase 2 — Profiles

- [ ] Profile Model
- [ ] JSON Storage
- [ ] Add
- [ ] Edit
- [ ] Delete
- [ ] Import
- [ ] Export

### Phase 3 — Core

- [ ] اضافه کردن Xray Core
- [ ] Config Generator
- [ ] Process Manager
- [ ] Start
- [ ] Stop
- [ ] Logs

### Phase 4 — Connection

- [ ] VLESS
- [ ] VMess
- [ ] Trojan
- [ ] System Proxy
- [ ] Connectivity Test

### Phase 5 — Advanced

- [ ] TLS
- [ ] WebSocket
- [ ] Fingerprint
- [ ] unsafe
- [ ] Cipher Suites
- [ ] Fragment

### Phase 6 — Subscription

- [ ] URL
- [ ] Parser
- [ ] Update
- [ ] Profile management

### Phase 7 — TUN

- [ ] Architecture
- [ ] Windows helper
- [ ] Routing
- [ ] DNS
- [ ] Tests

### Phase 8 — Polish

- [ ] Dark Mode
- [ ] Persian UI
- [ ] English UI
- [ ] Tray
- [ ] Auto Start
- [ ] Error handling
- [ ] Backup/Restore

---

## 16. Definition of Done برای نسخه شخصی

نسخه اول زمانی قابل استفاده محسوب می‌شود که:

- [ ] برنامه با `python main.py` اجرا شود
- [ ] کانفیگ VLESS وارد شود
- [ ] کانفیگ Parse شود
- [ ] Xray Config معتبر ساخته شود
- [ ] Xray اجرا شود
- [ ] اتصال برقرار شود
- [ ] System Proxy فعال شود
- [ ] مرورگر از اتصال استفاده کند
- [ ] Disconnect درست انجام شود
- [ ] Proxy به حالت قبلی برگردد
- [ ] Log خطاها قابل مشاهده باشد
- [ ] پروفایل‌ها بعد از بستن برنامه باقی بمانند

---

## 17. نسخه‌بندی پیشنهادی

```text
NetBridge v0.1
GUI + Profiles

NetBridge v0.2
Xray + VLESS

NetBridge v0.3
VMess + Trojan + System Proxy

NetBridge v0.4
TLS + WebSocket + Advanced settings

NetBridge v0.5
Fingerprint + unsafe + Cipher Suites + Fragment

NetBridge v0.6
Subscription

NetBridge v0.7
TUN

NetBridge v1.0
Personal Stable Release
```

---

## 18. اصل مهم پروژه

> ابتدا قابلیت اتصال پایدار، سپس قابلیت‌های پیشرفته.

قرار نیست همه امکانات PattNG را در اولین نسخه وارد کنیم. هر مرحله باید قابل اجرا و تست باشد تا اگر مشکلی پیش آمد دقیقاً بدانیم مشکل از GUI، Parser، Config یا Core است.

---

## 19. اولین Milestone

**هدف اولین مرحله:**

```text
Python
   ↓
PySide6 GUI
   ↓
Add VLESS
   ↓
Parse
   ↓
Generate Xray Config
   ↓
Run Xray
   ↓
System Proxy
   ↓
Browser Test
```

بعد از موفقیت این زنجیره، سراغ قابلیت‌های خاص PattNG می‌رویم.
