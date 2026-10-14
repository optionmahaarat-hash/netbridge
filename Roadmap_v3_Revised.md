# نقشه‌راه اصلاح‌شده — Options Scalping Decision Assistant
## Roadmap v3.0 (اصلاح‌شده بر پایه‌ی Audit واقعی کد + محدودیت‌های دیتای TSETMC)

> این نسخه جایگزینِ کاملِ v2.0 است. تفاوت اصلی با نسخه‌ی قبلی:
> ۱) هرچیزی که از قبل در کد ساخته شده، ✅ علامت خورده و دیگر «کار جدید» نیست.
> ۲) هرچیزی که با دیتای واقعیِ TSETMC (فقط صفِ برترِ bid/ask، بدون aggressor-side
>    صریح، بدون order-book چندسطحی) غیرقابل‌ساخت بود، حذف یا به نسخه‌ی واقع‌بینانه
>    تبدیل شده — با علامت ⚠️ REVISED.
> ۳) اولویت اجرا (بخش ۴۷) کاملاً بازچیده شده: چیزی که واقعاً کم است اول می‌آید.
> ۴) اصلاحیه‌ی ۱۴۰۴/۰۶/۲۳: بعد از Audit یک ستاپِ واقعی (ذوب)، ۵ گپِ
>    باقی‌مانده که تا این لحظه در هیچ نسخه‌ای مدل نشده بودند اضافه شد —
>    بخش‌های ۵۱ تا ۵۵ و PHASE D جدید. مهم‌ترینش: Position Sizing کلاً
>    غایب بود، نه فقط wireنشده.

هدف نهایی بدون تغییر: تبدیل اپ به یک **Decision Support System (DSS)** که یکی از
حالت‌های استاندارد را پیشنهاد می‌دهد، ولی هرگز خودکار معامله نمی‌کند.

---

# 0. اصول طراحی (بدون تغییر)

- [x] تصمیم‌یار است، نه معامله‌گر خودکار
- [x] هیچ سیگنال منفردی مجوز ورود نباشد
- [x] اول «کیفیت داده» بررسی شود، بعد تحلیل — `data_health.py`
- [x] اول جهت بازار پایه تعیین شود، سپس قرارداد انتخاب شود
- [x] هر تصمیم با دلیل قابل مشاهده ثبت شود — `signal_journal.py`, `audit_trail`
- [x] سیستم در وضعیت نامطمئن باید `WAIT` بدهد — `conflict_detector.py`
- [x] امکان Override دستی وجود داشته باشد
- [x] تمام تصمیم‌ها برای Replay/Backtest ذخیره شوند
- [x] Late Entry و Liquidity Risk مانع ورود شوند — بازبینی نشون داد هر دو
      صراحتاً advisory-only مستند شده بودند (خلافِ همین اصل). گیتِ نهایی به
      `decision_fusion.py` اضافه شد (نه `entry_trigger.py` — آن‌جا late_entry
      و liquidity اصلاً در دسترس نیستند): وقتی stage=ENTER ولی late_entry
      خیلی‌دیر/دیگه‌دیره یا liquidity کم/هیچ باشه، خروجیِ نهایی به ARMED
      برمی‌گرده + دلیلِ صریح در blockers

---

# 1. معماری کلان — وضعیت واقعی

نمودار قبلی درست است، ولی امروز همه‌ی این مراحل **داخل یک لوپ واحد**
(`option_worker_loop` / `stock_worker_loop` در `main.py`) به‌ترتیب اجرا می‌شوند،
نه به‌صورت ماژول‌های مجزا. کارکردی درست، ولی قابلیت تست/جایگزینیِ هر لایه به‌تنهایی
پایین است.

```text
LIVE MARKET DATA (TSETMC polling — data_feed.py)
        |
DATA QUALITY GATE (data_health.py) ✅
        |
NORMALIZATION (data_feed.py) ✅
        |
Feature Engine (indicators.py, multi_timeframe.py) ✅
        |
Microstructure «صفِ برتر» (best_limits.py, trade_classifier.py) ✅ نسخه‌ی واقعی
        |
Momentum / Price Structure (indicators.py, support_resistance.py, false_breakout.py) ✅
        |
Options Analytics (option_greeks.py, oi_engine.py, moneyness.py) ✅
        |
Signal Score (signal_score.py) + Condition Weights ✅
        |
Conflict Check (conflict_detector.py) ✅
        |
❌ DECISION FUSION ENGINE ← تنها حلقه‌ی گمشده‌ی واقعی
        |
Entry Trigger (entry_trigger.py) ✅ → Position Manager (main.py) ✅
        |
Journal / Replay / Calibration ✅
```

**کار جدید واقعی:** فقط ساختنِ لایه‌ی Decision Fusion به‌عنوان یک ماژول مجزا
(`decision_fusion.py`) که ورودی‌هایش از لایه‌های بالا می‌آید و روی همان لوپ سوار
می‌شود — نه بازنویسیِ کل معماری.

---

# 2. وضعیت‌های استاندارد تصمیم (Unified Enum)

این بخش هدفِ اصلیِ Decision Fusion Engine است. باید یک enum واحد این حالت‌ها را
جایگزین دو مجموعه‌ی موازیِ فعلی (`BUY/SELL/WAIT` سهم + `WATCH/ARMED/ENTER/HOLD`
قرارداد) کند:

- [x] `NO_DATA`
- [x] `DATA_UNRELIABLE`
- [x] `NO_TRADE`
- [x] `WAIT`
- [x] `WATCH_CALL` / `WATCH_PUT`
- [x] `ARMED_CALL` / `ARMED_PUT`
- [x] `ENTER_CALL` / `ENTER_PUT`
- [x] `HOLD` / `REDUCE` / `EXIT` / `EMERGENCY_EXIT`

قانون مهم بدون تغییر: `BUY/SELL` به‌تنهایی خروجی نهایی نیست؛ خروجی نهایی شامل
`ACTION / DIRECTION / CONTRACT / ENTRY ZONE / INVALIDATION / TP1 / TP2 / TIME
STOP / CONFIDENCE / SCALP SCORE / REASONS / BLOCKERS` است — دقیقاً همان چیزی که
بخش ۵۰ می‌خواهد و امروز پخش در چند endpoint است.

---

# 3. Data Layer

## 3.1 داده بازار پایه — ✅ کامل (`data_feed.py`, `indicators.py`)
Last/Bid/Ask/Spread/Tick/VWAP/OHLC/RVOL/ATR همگی موجودند.

## 3.2 داده آپشن — ✅ کامل (`option_greeks.py`, chain state)

## 3.3 Order Book — ⚠️ REVISED (این بخش در v2.0 غیرواقعی بود)

TSETMC عمومی فقط `BestLimits` را منتشر می‌کند: **صفِ برترِ خرید/فروش** به همراه
حجم و تعداد سفارش در همان صف — نه Level 2 تا Level 5. بنابراین:

- ~~Level 1 تا Level 5~~ → فقط **صفِ برتر (Best Bid/Ask + Depth + Order Count)**
- [x] Bid/Ask depth (صفِ برتر) — `best_limits.py`
- [x] Weighted imbalance (تقریبی، تک‌سطحی) — `best_limits.order_book_imbalance`
- [x] Imbalance change در طول زمان (مشتقِ همین سری) — بازبینی نشون داد این
      دقیقاً همون OBI slope‌ایه که در بخشِ ۵.۱ پایین‌تر (`best_limits.queue_dynamics`
      → `obi_slope`) قبلاً ساخته و به main.py/فرانت وصل شده بود؛ این چک‌باکس
      صرفاً هم‌زمان با اون به‌روزرسانی نشده بود — کارِ تازه‌ای لازم نبود
- ~~Queue growth/collapse per level~~ → ~~Refill detection~~ → ~~Pull/cancel detection~~
  **حذف شد** — این‌ها نیاز به عمق چندسطحی دارند که این فید ندارد.

## 3.4 Data Quality — ✅ کامل (`data_health.py`)

---

# 4. Time-Series / Feature Engine

فیچرهای چندبازه‌ای از قبل روی بازه‌های ۱۰ثانیه تا ۳دقیقه در
`indicators.RollingMomentum` وجود دارند.

⚠️ REVISED: بازه‌های ۵ثانیه/۱۰ثانیه در v2.0 فرض شده بودند بدون بررسیِ فرکانسِ
واقعیِ polling سرور. **قبل از افزودن فیچر روی این بازه‌ها، باید فرکانس واقعی
دریافتِ تیک از TSETMC اندازه‌گیری شود** (احتمالاً هر چند ثانیه، نه هر ثانیه).
اگر فرکانس واقعی کندتر از بازه باشد، آن بازه فقط نویز تولید می‌کند و باید حذف شود.

- [x] Return / Velocity / Acceleration — موجود
- [x] VWAP distance / EMA distance / ATR normalized — موجود
- [x] Breakout distance / Pullback depth به‌عنوان فیچرهای صریحِ نام‌گذاری‌شده —
      منطقشان از قبل پراکنده بود (level/last_price در `false_breakout.py`،
      extreme_price/level در `pullback_engine.py`)، فقط یک‌جا با یک اسمِ ثابت
      جمع نشده بود. الان: `false_breakout.info()` یک فیلدِ تازه‌ی
      `breakout_distance_pct` داره (چقدر قیمتِ الان از سطحِ شکسته‌شده،
      به‌درصد، فراتر رفته)، و `pullback_engine.info()` یک فیلدِ تازه‌ی
      `pullback_depth_pct` داره (چقدر از دورترینِ حرکتِ بعدِ شکست
      (extreme_price) به سمتِ سطح برگشته، به‌درصدِ کلِ فاصله‌ی extreme↔level).
      چون main.py هر دو dict رو مستقیم از `.info()` پاس می‌ده (بدونِ
      map/whitelist)، این فیلدها خودکار به API/فرانت هم رسیدن — سیم‌کشیِ
      اضافه لازم نبود.

---

# 5. Microstructure Engine — ⚠️ REVISED کامل

## 5.1 Order Book Imbalance (نسخه‌ی واقعی)

```text
OBI = (WeightedBid - WeightedAsk) / (WeightedBid + WeightedAsk)
```
فقط روی **صفِ برتر**، نه ۵ سطح. ✅ موجود در `best_limits.py`.

- [x] OBI صفِ برتر
- [x] OBI slope (تغییرات OBI در طول زمان) — `best_limits.queue_dynamics`
      (یک تاریخچه‌ی module-level سبک، فقط یک اسنپ‌شاتِ قبلی به ازای هر
      ins_code؛ شیب = تغییرِ OBI بر ثانیه بینِ دو snapshotِ متوالی). به
      main.py وصل شده (`obi_slope_by_ins` → `contract["obi_slope"]` +
      `signal.obi_slope`)؛ وقتی برخلافِ جهتِ سیگنال به‌سرعت در حالِ
      چرخیدنه، یک هشدارِ advisory-only به reasons اضافه می‌شه
      (`OPTION_OBI_SLOPE_ALERT`، دقیقاً هم‌الگوی خودِ Imbalance). ردیفِ
      نمایشی در فرانت (`renderOptionOffsetsRow`).
- ~~OBI Level 5~~ **حذف شد** (داده وجود ندارد)

## 5.2 Order Book Velocity — ⚠️ REVISED — ✅ کامل
- [x] ~~Bid/Ask growth per level~~ → «تغییرات صفِ برتر بین دو snapshot»
      (`queue_velocity` — تغییرِ (bid_qty-ask_qty) بر ثانیه) —
      `best_limits.queue_dynamics`
- [x] Queue acceleration روی همین صفِ برتر — `best_limits.queue_dynamics`
      (مشتقِ دوم؛ نیاز به سومین اسنپ‌شاتِ متوالی داره، پس بعدِ هر ریست/
      وقفه، اولین مقدارِ معتبرش None می‌مونه). `contract["queue_acceleration"]`
      + `signal.queue_acceleration`، صرفاً نمایشی (advisory-only).
      dt خیلی کوچیک (<۱ثانیه) نادیده گرفته می‌شه بدونِ جابه‌جاییِ baseline،
      dt خیلی بزرگ (>۱۲۰ثانیه، مثلِ یک وقفه‌ی فید) باعثِ ریستِ بی‌صدای
      baseline می‌شه — دقیقاً هم‌روحِ stale-price guardِ `data_feed.py`.
- ~~Queue collapse per level~~ **حذف شد**

## 5.3 Trade Flow — ⚠️ REVISED (تخمینی، نه واقعی)
TSETMC جهتِ خریدار/فروشنده‌ی معامله را اعلام نمی‌کند. آنچه ساخته شده
(`trade_classifier.py`) یک **تخمین با قاعده‌ی کلاسیک Lee & Ready (1991)** است
(Quote Rule + Tick Rule)، نه سیگنال مستقیم اکسچنج.

- [x] Aggressive buy/sell volume (تخمینی) — `trade_classifier.py`
- [x] Buy/Sell ratio, Cumulative delta — موجود
- [x] **الزامی:** در خروجیِ UI و «WHY» صریحاً برچسب بخورد که این تخمینی است
      (مثلاً «~Aggressive Buy (est.)») تا کاربر با داده‌ی رسمی اشتباه نگیرد.
      خروجیِ `trade_classifier.snapshot()` هم فیلدِ `is_estimated: true`
      داره؛ متنِ reasons («تخمینی») و بجِ فرانت (`~XX٪ (تخمینی)`) هر دو
      صریحاً این رو نشون می‌دن.

## 5.4 Liquidity — ✅ کامل (`data_health.py`, `_liquidity_tier` در `main.py`)

---

# 6. Momentum Engine — ✅ عمدتاً کامل

- [x] بازه‌های ۱۰s–۳m، Acceleration — `indicators.RollingMomentum`
- [x] False Breakout (شاملِ منطق Exhaustion) — `false_breakout.py`
- [x] Momentum Burst / Exhaustion / Flip به‌عنوان **detectorهای صریح و نام‌گذاری‌شده**
      — فیلدِ تازه‌ی `RollingMomentum.state` (بعد از هر `update()` محاسبه
      می‌شه): BURST (شتابِ قوی هم‌جهت با حرکتِ ۱۰ثانیه‌ی اخیر)، EXHAUSTION
      (روندِ ۳دقیقه‌ای هنوز همون جهته ولی شتاب برخلافش افتاده)، FLIP
      (بازدهِ ۱۰ثانیه‌ی اخیر برخلافِ جهتِ روندِ ۳دقیقه‌ای)، NORMAL/UNKNOWN.
      کاملاً advisory-only (فقط یک خطِ reasons در `decision_engine.py`،
      بدونِ اثر روی action/conditions_met/confidence) — دقیقاً هم‌الگو با
      بقیه‌ی این بخش؛ منطقِ زیربنایی همون returns_pct/acceleration_pct بود
      که از قبل موجود بود

---

# 7. Price Structure Engine — ✅ کامل
VWAP/EMA/Bollinger/ATR (`indicators.py`)، Support/Resistance فرکتال ویلیامز
(`support_resistance.py`)، Breakout/Retest/Failed Breakout/Pullback/Rejection
(`false_breakout.py` + `condition_weights.py`).

---

# 8. Multi-Timeframe Engine — ✅ کامل (`multi_timeframe.py`)
Trend alignment/conflict/MTF confidence همه موجودند.

---

# 9. Divergence Engine — ✅ کامل
Price/OBV و Price/Momentum در `indicators.RollingDivergence`؛ Price/OI و
Price/IV در `divergence_engine.py` (مخصوص آپشن).

---

# 10. Breakout Intelligence — ✅ کامل (`false_breakout.py`)

---

# 11. Options Intelligence Engine — ✅ کامل
Contract Quality Score، Black-Scholes + IV solver + Greeks sanity checks
(`option_greeks.py`)، IV Intelligence (`/api/iv_history`).

---

# 12. OI Intelligence — ✅ کامل (`oi_engine.py`)
OI/OI change/Volume-OI ratio/Call-Put Wall/Max Pain-as-context موجودند.

---

# 13. Contract Selector — ✅ کامل (Phase C)
- [x] Rank/Filter illiquid/Filter excessive-spread — `main._compute_best_contracts`
- [x] تطبیق دقیق وزن‌ها با فرمول پیشنهادی — بازبینی شد؛ تصمیمِ عمدی: Liquidity
      و Spread در یک زیرمعیارِ واحد (۲۵ امتیاز، نه ۲۰+۱۵ی جدا) ادغام مانده‌اند
      چون در این پروژه Spread صرفاً اندازه‌گیریِ لحظه‌ایِ همان نقدشوندگی است، نه
      بُعدِ مستقل — دلیلِ کامل در docstring بالای `contract_quality.py`.
- [x] نمایش «۲ گزینه‌ی جایگزین + دلیل انتخاب» — `_pick_contracts_for_decision`
      (main.py) حالا تا ۲ جایگزین برمی‌گردونه؛ `decision_fusion.compute`
      فیلدِ `alternatives` (لیست از `{label, reason}`) رو می‌سازه —
      `_alt_reason`/`_alternatives_list` در `decision_fusion.py`. دلیلِ هر
      جایگزین از مقایسه‌ی همون signal_score/quality_scoreای که برای
      رتبه‌بندی استفاده می‌شه ساخته می‌شه (بدونِ محاسبه‌ی تازه). نمایش در
      فرانت: `.fusion-alt` (چندخطی، هر جایگزین با دلیلش).

---

# 14. Scalp Score Engine — ✅ کامل (`signal_score.py`) (Phase C)
- [x] Score نهایی ۰ تا ۱۰۰ با breakdown
- [x] تطبیق دقیق interpretation bands (۰-۳۹/۴۰-۵۴/۵۵-۶۹/۷۰-۷۹/۸۰-۸۹/۹۰-۱۰۰) با
      آستانه‌های فعلی کد — بازبینی شد: `NO_TRADE_MAX=39, WEAK_MAX=54,
      WATCH_MAX=69, GOOD_MAX=79, STRONG_MAX=89` در `signal_score.py` از
      قبل دقیقاً همین باندها بودند؛ چیزی تغییر نکرد، فقط تأیید شد.

---

# 15-17. Entry / Late Entry / Pullback

- [x] Entry Trigger (WATCH→ARMED→ENTER) — `entry_trigger.py`
- [x] Entry Zone/Target/Stop — `price_offsets.py`
- [x] خروجی صریح Late Entry با پنج سطحِ `GOOD_ENTRY/ACCEPTABLE/LATE/
      VERY_LATE/NO_ENTRY` — `late_entry.py` (دو محورِ مستقل: فاصله‌ی
      قیمتی نسبت به پهنای باندِ بولینگر + زمانِ سپری‌شده از تأییدِ
      سیگنال؛ بدترینِ این دو محور تعیین‌کننده‌ست). به هر دو لوپِ
      سهم/آپشن در `main.py` وصل شده (فیلدِ `late_entry` + یادداشتِ
      `reasons`)، بجِ رنگی در فرانت (`lateEntryBadge`).
- [x] Pullback Engine مجزا با «re-entry zone» صریح — `pullback_engine.py`
      (`PullbackTracker`، از وضعیت/سطحِ `false_breakout.py` تغذیه
      می‌شه، بدونِ داده‌ی تازه). به `indicators.SymbolIndicators` وصل
      شده (`ind.pbk`، هم روی سهمِ پایه هم روی هر قراردادِ آپشن خودکار)؛
      متنِ reasons در `decision_engine.py` ساخته می‌شه؛ endpoint جدید
      `/api/pullback/{symbol}`؛ بجِ رنگی در فرانت (`pullbackBadge`).

---

# 18-21. Risk / Dynamic Stop / Profit Management / Early Exit — ✅ عمدتاً کامل
- [x] Risk Engine پیش از معامله (`risk_engine.py`)
- [x] Dynamic SL/TP با Regime (`dynamic_risk.py`)
- [x] Break-even (`breakeven.py`)
- [x] Early Exit با Momentum/OBI reversal (`main._check_position_exit`)
- [x] تأیید صریح که IV collapse و Spread explosion هم به‌عنوان دلیل Early Exit
      در `_check_position_exit` لحاظ شده‌اند — بررسی نشون داد IV collapse از
      اول موجود بود، ولی Spread explosion نه: `spread_pct` در
      entry_snapshot/context جمع‌آوری می‌شد ولی هیچ‌وقت مصرف نمی‌شد.
      سیگنالِ پنجمِ تازه (`SPREAD_EXPLOSION_PCT_MIN`) به `early_exit.evaluate`
      اضافه شد — هیچ Gateِ جدیدی لازم نبود، `_check_position_exit` از قبل
      همون context رو کامل پاس می‌داد.

---

# 22. Market Regime Engine — ✅ کامل (`regime_engine.py`، رفعِ گپِ wiring)

`market_pulse.py` یک گیجِ تجمعیِ Bullish/Bearish/Neutral روی ۱۱ نماد داره
(بخشِ جدا، دست‌نخورده). enum کاملِ ۸حالته زیر (TRENDING_UP/DOWN, RANGE,
HIGH/LOW_VOLATILITY, BREAKOUT, EXHAUSTION, UNCERTAIN) از قبل ساخته شده بود؛
فقط به main.py وصل نشده بود (`main_py_changes.diff` بدونِ اعمال مونده بود
در آپلودِ قبلی) — الان اعمال شد: `/api/regime/{symbol}` +
`decision_fusion.py` مستقیماً از `regime_engine.compute(ind)` استفاده می‌کنه.

- [x] Trending Up / Trending Down
- [x] Range
- [x] High Volatility / Low Volatility
- [x] Breakout Regime
- [x] Exhaustion
- [x] Uncertain

---

# 23. Decision Fusion Engine — ✅ کامل (`decision_fusion.py`)

مهم‌ترین بخشِ کل رودمپ. **همه‌ی ورودی‌هایش از قبل موجودند** (بخش‌های ۵ تا ۲۲) —
فقط در یک ماژول جدید `decision_fusion.py` ترکیب شدند (بدونِ محاسبه/Gateِ تازه).

ورودی: Direction, Momentum, Microstructure (صفِ برتر), Volume, Price Structure,
MTF, Option Quality, IV, Risk, Market Regime (بخش ۲۲)

خروجی: enum بخش ۲ + قالب دقیق بخش ۵۰ (یک شیءِ JSON واحد، سرو شده از
`GET /api/decision/{symbol}`)

- [x] تابع فیوژن که این ۱۰ ورودی را می‌گیرد (`decision_fusion.compute`، ۲۱ تست واحد)
- [x] endpoint واحد `/api/decision/{symbol}`
- [x] یک پنل واحد در فرانت که دقیقاً همین شیء را نمایش دهد (نه پخش در چند پنل) — `.fusion-panel` در `frontend/index.html`

**صداقت — چند تصمیمِ طراحیِ این پیاده‌سازی که سندِ رودمپ صریح تعریف نکرده
بود** (جزئیاتِ کامل در docstring خودِ `decision_fusion.py`): CONFIDENCE فعلاً
یک نسخه‌ی ساده‌شده است، نه ۵ مؤلفه‌ی مجزای بخشِ ۲۸ (هنوز کارِ باقی‌مانده)؛
TP2 با یک ضریبِ heuristicِ ثابت از TP1 گسترش داده می‌شه (هیچ TP2ِ مستقلی
در main.py محاسبه نمی‌شد)؛ REDUCE یک تقریبِ heuristic است چون
partial-exit/position-sizing اصلاً در پروژه مدل نشده؛ ALTERNATIVE فعلاً
فقط ۱ گزینه‌ی جایگزین نشون می‌ده، نه ۲تا که بخشِ ۱۶ پیشنهاد می‌ده.

---

# 24. WAIT Intelligence — ✅ کامل
- [x] تفکیک «شواهد ناکافی» از «تضاد واقعی» — `conflict_detector.py`
- [x] فرمت خروجیِ ساختاریافته («X ولی Y و Z») — فیلدِ تازه‌ی `explanation`
      در خروجیِ `decision_fusion.compute` (`_build_explanation`/`_join_fa`
      در `decision_fusion.py`)؛ وقتی conflict_detail موجوده از aligned/
      opposed factors استفاده می‌کنه («X در جهتِ سیگنال است ولی Y خلافِ
      آن»)، وگرنه از reasons/blockers می‌سازه. در `.fusion-explanation`ِ
      فرانت نمایش داده می‌شه. تست: ۴ سناریوی تازه در
      `tests/test_decision_fusion.py`.

---

# 25-26. Watchlist / Opportunity Scanner — ✅ کامل
`/api/watchlist`, `opportunity_scanner.py`, `/api/opportunity_scanner` +
پنل‌های مربوطه در فرانت‌اند.

---

# 27-28. Conflict Engine / Confidence Engine — ✅ کامل (Phase C)
- [x] Conflict Engine — کامل (`conflict_detector.py`)
- [x] Confidence به‌عنوان بُعدِ کاملاً مجزا از Score (Agreement + Data quality +
      Signal persistence + Regime stability + Historical performance) —
      ماژولِ تازه‌ی `confidence_engine.py` این ۵ مؤلفه را مجزا محاسبه می‌کند
      (هرکدام از داده‌ای که جای دیگری از پروژه از قبل محاسبه شده: خودِ
      signal_score_breakdown، data_health، entry_stage، regime_engine،
      signal_journal.get_stats — نه محاسبه‌ی تازه). خروجیِ
      `decision_fusion.compute` حالا `confidence_score`/`confidence_breakdown`
      دارد؛ `scalp_score` کاملاً مستقل مانده (فقط signal_score خودِ قرارداد،
      بدونِ آمیختن با confidence). نمایش در فرانت: `.fusion-conf-breakdown`.

---

# 29. Explainability — ✅ کامل
- [x] Reasons list در چند endpoint موجود
- [x] Score breakdown با علامتِ +/~/- به همراه Trigger/Invalidation در یک
      قالب واحد — فیلدهای تازه‌ی `score_breakdown` (برچسبِ +/~/- روی همون
      `signal_score_breakdown` موجود، نه محاسبه‌ی تازه) و `trigger` (اولین
      `entry_stage_reasons`) در کنارِ `invalidation`/`tp1`/`tp2`ِ از‌قبل‌
      موجود، همگی در یک خروجیِ `/api/decision/{symbol}` — `decision_fusion.py`
      (`_signed_score_breakdown`). نمایش در `.fusion-breakdown`/`.fusion-trigger`
      فرانت.

---

# 30. Alert Engine — ✅ عمدتاً کامل
Telegram (`telegram_notifier.py`) و Email (`email_notifier.py`) با آستانه‌ی
confidence/score قابل‌تنظیم از env vars.
- [x] تفکیک صریح انواع Alert — هر پیام حالا تگِ نوعِ خودش رو داره:
      `[ورود]` (BUY/SELL تأییدشده، با یک خطِ اضافیِ `[ورودِ دیرهنگام]`
      وقتی late_entry.py سطحِ غیرِ GOOD_ENTRY تشخیص بده)، `[Setup]`
      (الگوهای setup_library.py)، `[شکستِ جعلی]`/`[شکستِ تأییدشده]`
      (رویدادهای false_breakout.py — قبلاً اصلاً پوش نمی‌شدن، فقط در UI
      نشون داده می‌شدن؛ حالا با دیبانسِ per-symbol/per-contract پوش هم
      می‌شن، فقط در لحظه‌ی *رزولوشن*، نه در حالتِ pending).
      WATCH/ARMED عمداً پوش نمی‌شن (دلیلِ صداقت: این‌ها خیلی مکررن،
      entry_trigger.py صراحتاً برای نمایشِ UI طراحی شده نه پوش؛ پوش‌کردنشون
      فقط اسپمه). MOMENTUM BURST هنوز یک detectorِ نام‌گذاری‌شده و مجزا
      نیست (نگاه کن به بخشِ ۶ بالا) — وقتی اون ساخته بشه، تگِ Alertِ
      مخصوصِ خودش هم اضافه می‌شه.

---

# 31. Position Monitor — ✅ کامل
Entry/Current/P&L/Time in trade/HOLD-REDUCE-EXIT در `main.py`
(`_position_context`, `_check_position_exit`, `/api/positions`).
- [x] MFE/MAE per-position به‌صورت صریح ذخیره شود — `mfe_pct`/`mae_pct` روی
      خودِ dict پوزیشن، هر چرخه در `_positions_check_cycle()` به‌روز می‌شن
      (بهترین/بدترینِ pnl_pctِ دیده‌شده از لحظه‌ی ورود)، بعد از
      `exit_triggered` منجمد می‌مونن (چون فقط پوزیشنِ status=="open"
      پردازش می‌شه)، و در `/api/positions` هم دیده می‌شن.

---

# 32. Trade Journal — ✅ کامل (`signal_journal.py`)

---

# 33. Replay Engine — ⚠️ REVISED
- [x] Tick/Signal/Decision replay بر پایه‌ی resample کندلی — `history_feed.py`,
      `/api/replay/{symbol}`
- ~~Order-book replay~~ **حذف شد** — چون فقط صفِ برترِ لحظه‌ای ذخیره می‌شود، نه
  تاریخچه‌ی کامل عمق بازار؛ replay دقیق order-book امکان‌پذیر نیست مگر صفِ برتر
  هم در هر تیک لاگ شود (این خودش یک آیتم جداست، نه بخشی از replay فعلی).

---

# 34. Backtest اختصاصی اسکالپ — ⚠️ REVISED

نسخه‌ی فعلی (`backtest.py`) کندل‌محور است (resample به ۶۰ ثانیه) و همان موتور
تصمیمِ زنده را روی تاریخچه اجرا می‌کند — این خودش ارزشمند و «تقلبی» نیست.

- ~~Event-driven تیک‌به‌تیک با شبیه‌سازیِ Partial fills/Queue position/Rejected
  orders~~ **غیرواقعی برای این پروژه** — چون دیتای سطحِ سفارش (order-level) از
  TSETMC در دسترس نیست تا چنین شبیه‌سازیِ دقیقی را معتبر کند. به‌جایش:
- [x] Spread/Slippage تقریبی — تا حدی در `contract_stress.py`/`risk_engine.py`
- [x] Fees (کارمزد واقعیِ بورس ایران) در محاسبه‌ی Net P/L لحاظ شود — بررسی
      شد: `backtest.py` از قبل `FEE_ROUNDTRIP_PCT_DEFAULT` رو در
      `net_return_pct` لحاظ می‌کرد. چیزی که واقعاً کم بود:
      `signal_journal.py` (رکوردِ *زنده*، نه بک‌تست) فقط `move_pct` خام
      داشت. حالا یک `net_move_pct` تازه (فقط برای `contract_type="stock"`،
      با همون ثابتِ هزینه‌ی `backtest.STOCK_TOTAL_COST_PCT_DEFAULT` —
      تعریفِ یک‌جا، نه کپی) به `resolve()` اضافه شد؛ کاملاً
      informational — وضعیتِ WIN/LOSS/NOISE هنوز فقط از `move_pct` خام
      تعیین می‌شه (همون چیزی که `condition_weights` برای یادگیری
      می‌خونه). `performance_report.build_report()` هم یک فیلدِ تازه‌ی
      `overall_net_stock` (میانگینِ net_move_pct روی سهم) داره.

---

# 35. معیارهای ارزیابی — ✅ کامل (`performance_report.py`, `backtest.py`)
Win Rate/Expectancy/Setup-specific expectancy موجودند؛ Sharpe/Sortino/Max
Drawdown — بررسی شد: Max Drawdown از قبل در `backtest._compute_stats`
بود؛ Sharpe/Sortino واقعاً محاسبه نمی‌شدند. حالا `_per_trade_sharpe_sortino()`
اضافه شده و در خروجیِ `run_backtest` به‌صورتِ `sharpe_ratio_per_trade` /
`sortino_ratio_per_trade` در دسترسه. **صداقت:** این نسخه‌ی «به‌ازای هر
معامله» است، نه سالانه‌شده (به‌دلیلِ طولِ عمرِ نامنظمِ معاملاتِ اسکالپ —
جزئیاتِ کامل در docstring خودِ تابع).

---

# 36. Setup Analytics — ✅ کامل
تفکیک بر اساس Regime/Time of day (`time_of_day.py`) از قبل موجود بود.
تفکیک بر اساس نوعِ Entry (Momentum/Breakout/Retest/Pullback/Reversal) و
Moneyness (ATM/ITM/OTM) تکمیل شد:
- [x] `entry_classifier.py` (ماژولِ جدید) — نوعِ ورود رو از رویِ
      شواهدِ *از-قبل-محاسبه‌شده*‌ی `setup_library.py`/`pullback_engine.py`/
      `false_breakout.py` تعیین می‌کنه (اولویتِ Retest > Breakout >
      Reversal > Pullback > Momentum > نامشخص).
- [x] `signal_journal.py` — دو ستونِ `entry_type`/`moneyness` (با
      مهاجرتِ خودکارِ دیتابیسِ قدیمی).
- [x] `main.py` — سیم‌کشیِ هر دو محلِ `record_signal` (سهم و قرارداد).
- [x] `performance_report.py` — دو breakdownِ جدید `by_entry_type` و
      `by_moneyness` (دومی فقط رویِ آپشن‌ها).

---

# 37-38. Calibration / Walk Forward — ✅ کامل
`calibration.py` + `/api/backtest/{symbol}/walk_forward`.

---

# 39. ML — ✅ کامل
`condition_weights.py` از قبل یک نسخه‌ی سبک و شفاف («online weight update»، نه
ML واقعی) دارد که دقیقاً روحِ همین بخش را رعایت می‌کند: «رأی، نه حاکم مطلق».

- [x] Logistic Regression baseline روی Journal، فقط بعد از ≥۲۰۰ نمونه‌ی
      resolved (`ml_baseline.py`، `MIN_SAMPLES_REQUIRED=200`)
- [x] Out-of-sample validation (بخشِ ۵۶) — split زمانیِ ۸۰/۲۰
- [x] Drift detection — `drift_detection.py` + `/api/ml/drift`

---

# 40. معماری نرم‌افزار — پیشنهاد سبک، نه بازنویسیِ کامل
پوشه‌بندیِ ایده‌آلِ v2.0 (`data/`, `features/`, `engines/`, ...) نیاز به مهاجرتِ
پرهزینه از ساختار فعلی (فایل‌های flat در `backend/`) دارد بدون سود عملیِ فوری.
**پیشنهاد:** فقط فایل‌های جدید (`decision_fusion.py`, `regime_engine.py`) به
همین ساختار flat فعلی اضافه شوند؛ ری‌فکتور کامل پوشه‌بندی را به بعد از تکمیل
Decision Fusion Engine موکول کنیم.

---

# 41. داشبورد اصلی — 🟡 نسبی
پنل‌های Market Pulse، Watchlist، Position، Scanner از قبل در `frontend/index.html`
هستند.
- [x] «پنل ۳ — Current Decision» به‌صورت یک پنل بزرگ و واحد که خروجیِ Decision
      Fusion Engine را دقیقاً مطابق قالب بخش ۵۰ نشان دهد — `.fusion-panel`،
      بالای پنلِ جزئیاتِ هر نماد در `frontend/index.html`

---

# 42-43. Human-in-the-loop / حالت‌های کاری
- [x] Decision-only (سیستم هرگز سفارش ارسال نمی‌کند)
- [x] Kill Switch دستی + خودکار (`kill_switch.py`)
- [x] Flag صریح SAFE/PAPER/LIVE-ASSIST/LIVE در کد — ماژولِ تازه‌ی
      `run_mode.py` (`RunMode` enum + `GET /api/system/run_mode`).
      خوندن از env var `DECISION_ASSISTANT_MODE`، پیش‌فرض SAFE.
      `is_order_execution_allowed()` همیشه False برمی‌گردونه — LIVE
      عمداً هرگز باعثِ ارسالِ سفارشِ خودکار نمی‌شه (نگاه کن به
      docstring خودِ فایل برای دلیلِ کامل). **صداقت درباره‌ی سیم‌کشی:**
      `is_alerting_allowed()` هنوز داخلِ `telegram_notifier`/
      `email_notifier` قلاب نشده تا رفتارِ تست‌شده‌ی فعلیِ Alertها (که
      فقط به ENABLED=وجودِ کلیدهای env بستگی داره) تغییر نکنه؛ این تابع
      یک هوکِ آماده برای فعال‌سازیِ صریح در آینده‌ست.

---

# 44. تست‌های ضروری — ✅ کامل
۶۲ فایل تست در `backend/tests/` (۸۷۲ تست، همه پاس)، پوشش گسترده — شاملِ
`test_backtest.py`، `test_run_mode.py`، `test_session_export.py`،
`test_queue_status.py` (همه تازه).

---

# اضافه‌ی خارج از نقشه — Market Context Filter (صف خرید/فروشِ سهم)
درخواستِ مستقیمِ کاربر (بعد از STEP 34): برای هر نماد، وضعیتِ صفِ
خرید/فروش رو نشون بده — اگه صفِ خریده، «احتمالِ عرضه»؛ اگه صفِ فروشه،
«احتمالِ جمع‌شدن». پیاده‌سازی:
- [x] `queue_status.py` (تازه) — تشخیصِ `BUY_QUEUE`/`SELL_QUEUE` از
      روی `best_limits` (یک‌طرفه‌بودنِ صف) + قیمتِ روی سقف/کفِ امروز؛
      و `assess_pressure()` — امتیازِ هیورستیکِ ۵-۹۵ بر اساسِ (۱) حضورِ
      مستقیمِ طرفِ مقابلِ صف (مهم‌ترین شاهد)، (۲) شیبِ صف
      (`best_limits.queue_dynamics`، از قبل موجود بود ولی فقط برای
      آپشن استفاده می‌شد)، (۳) زمینه‌ی `market_pulse` کلی. صراحتاً
      هیورستیک، نه احتمالِ آماریِ کالیبره‌شده.
- [x] main.py worker_loop — یک fetch همزمانِ `best_limits` برای خودِ
      ۱۱ سهم (نه فقط قراردادهای آپشن) + `payload["queue_status"]`.
      advisory-only، هیچ اثری روی raw_action/confidence.
- [x] فرانت‌اند — بج کوچیک رویِ کارتِ هر نماد (`renderCards`) وقتی
      صف فعاله، با دقیقه‌های صف + امتیازِ فشار.
- [x] تست: `test_queue_status.py` (۱۶ تست).

---

# اضافه‌ی جدید — گپ‌های واقعیِ اسکالپر (بر پایه‌ی بحثِ ذوب، ۱۴۰۴/۰۶/۲۳)
پنج موردی که بعد از بررسیِ عملیِ یک ستاپِ واقعی (ذوب، RSI≈93، چند روزِ
متوالیِ صفِ خرید) مشخص شد یا کلاً مدل نشده، یا زیرساختش هست ولی یک
لایه‌ی ناقصه. برخلافِ بخش‌های ۱ تا ۴۶، این‌ها **کارِ جدیدِ واقعی**اند،
نه wiringِ چیزی که از قبل ساخته شده بود.

## 51. Position Sizing Engine — ✅ کامل
- [x] `position_sizing.py` (جدید) — `set_settings(capital, risk_pct)` /
      `compute(entry_price, invalidation_price, contract_size, ...)` با
      فرمولِ fixed-fractional (`qty = floor(risk_amount / per_contract_risk)`).
      وقتی سرمایه ثبت نشده یا entry/invalidation در دسترس نباشه، خروجی
      `{"suggested_qty": None, "reason": "..."}` — نه یک عددِ گمراه‌کننده.
      تنظیماتِ کاربر در `last_state.json` ماندگاره. تست: `test_position_sizing.py`.
- [x] فیلدِ `suggested_size` در خروجیِ `/api/decision/{symbol}` (در
      `decision_fusion.compute`، از میانگینِ entry_zone تا invalidation).
- [x] `GET`/`POST /api/settings/position_sizing` برای ثبت/خواندنِ سرمایه/٪ریسک.
- [x] فرانت‌اند — دکمه‌ی «💰 سرمایه/ریسک» در تولبار (مودالِ سرمایه/٪ریسک) +
      سلولِ «سایزِ پیشنهادی» در پنلِ فیوژن، کنارِ Entry Zone.
- [x] صداقتِ مستندشده در docstringِ ماژول: فرمول تک‌پوزیشنیه، جمعِ ریسکِ
      چند پوزیشنِ هم‌زمان کنترل نمی‌شه (فازِ بعدی).

## 52. Queue Streak + RSI Extremity — ✅ کامل
- [x] **صداقت:** برخلافِ فرضِ اولیه‌ی این بخش، `indicators.py` هیچ RSI‌ای
      نداشت — `RollingRSI` (Wilder، period=14، O(1) per tick) از صفر
      اضافه شد و به `SymbolIndicators` وصل شد. تست: `test_rsi.py`.
- [x] شمارنده‌ی روزانه‌ی persist‌شده در `queue_status.py`
      (`record_daily_streak`/`get_streak`) — بر پایه‌ی تاریخِ میلادیِ
      روزِ سرور با تحملِ فاصله‌ی تا ۳ روزِ تقویمی (برای تعطیلاتِ آخرِ
      هفته)؛ صراحتاً *نه* تقویمِ معاملاتیِ رسمی — نگاه کن به یادداشتِ
      بالای `_MAX_GAP_DAYS` در کد.
- [x] وزنِ اضافه در `assess_pressure()` برای هر دو (استریک ≥۴ روز، RSI
      اشباعِ خرید/فروش ≥۸۵/≤۱۵) — با سقفِ امتیازِ کم، هم‌راستا با
      یادداشتِ صداقتِ اصلیِ رودمپ. تست: `test_queue_status.py`.

## 53. Execution Lag Transparency — ✅ کامل
- [x] فیلدهای `data_age_seconds`/`data_age_threshold_seconds` همیشه در
      خروجیِ `/api/decision/{symbol}` (از `underlying.age_seconds` موجود،
      نه فراخوانیِ جداگانه‌ی latency_monitor).
- [x] گیتِ WAIT: اگه `data_age_seconds` از ۱۵ ثانیه رد بشه، `decision_fusion.py`
      سیگنالِ تازه صادر نمی‌کنه (WAIT با دلیلِ صریح در blockers) — رتبه‌ش
      زیرِ Kill Switch (که NO_TRADE می‌ده) و بالای بقیه‌ی منطقِ اکشنه.
      مدیریتِ پوزیشنِ بازِ موجود از این گیت مستثناست. تست: `test_decision_fusion.py`.
- [x] بجِ صریح «⏱ N ث» کنارِ خطِ وضعیت در پنلِ فیوژن، با رنگِ قرمز وقتی
      از آستانه رد شده.
- [x] «حالتِ سریع» با `CONFIRM_CYCLES=1` به‌جای ۳ — تنظیمِ سراسریِ
      رانتایمِ بک‌اند (نه ثابتِ کدی)، از طریقِ `GET`/`POST /api/settings/fast_mode`،
      با ماندگاری در `last_state.json`. فرانت‌اند: دکمه‌ی «🚀 حالت سریع» در
      تولبار با تأییدِ صریح قبل از روشن‌کردن + بنرِ هشدارِ دائمی وقتی
      فعاله (نه فقط رنگِ دکمه). تست: `test_fast_mode.py`.

## 54. Real Fill Tracking — ✅ کامل
- [x] ستون‌های `actual_fill_price`/`actual_fill_time` در `signal_journal.py`
      (با مهاجرتِ خودکارِ دیتابیسِ قدیمی) + `record_fill(entry_id, price, time)`.
- [x] `get_slippage_calibration()` — مقایسه‌ی لغزشِ واقعیِ میانگین با
      `backtest.SLIPPAGE_COST_PCT_DEFAULT`؛ فقط بعد از ≥۲۰ فیلِ ثبت‌شده
      «قابل‌اتکا» می‌شه و فقط *هشدار* می‌ده (هیچ عددی خودکار عوض نمی‌شه).
      تست: `test_signal_journal.py`.
- [x] `POST /api/journal/fill` + `GET /api/journal/slippage_calibration`.
- [x] فرانت‌اند — پنلِ «ثبتِ فیلِ واقعی» در تبِ «عملکرد»: آخرین ۱۵ سیگنالِ
      Journal با ورودیِ قیمتِ فیل + خلاصه‌ی کالیبراسیونِ لغزش.

## 55. Order Flow Proxy — ✅ کامل
- [x] `tick_up_ratio`/`tick_window` در `trade_classifier.AggressiveVolumeTracker`
      (نسبتِ تیک‌های صعودی روی آخرین ۲۰ تیکِ *دارای تغییرِ قیمت*، خالصِ
      Tick Rule — مجزا از طبقه‌بندیِ buy/sell موجود که Quote Rule هم داره).
      خودکار در فیلدِ `aggressive_volume` موجود serialize می‌شه، بدونِ
      wiringِ اضافه. تست: `test_trade_classifier.py`.

---

# 45. Performance — ✅ کامل
- [x] Incremental indicators O(1) per tick — طراحیِ صریح در `indicators.py`
- [x] اندازه‌گیریِ صریحِ latency (از رسیدنِ تیک تا تولیدِ تصمیم) —
      `latency_monitor.py` (جدید). دو source جدا (`stock`/`option`)، هرکدوم
      با آستانه‌ی هشدارِ خودش؛ آمارِ چرخانِ اخیر (avg/p95/max) + شمارنده‌ی
      lifetime + شمارنده‌ی breach. قلاب‌شده در `main.py` بلافاصله بعدِ
      `evaluate()` در هر دو حلقه (سهم و آپشن). endpoint: `GET
      /api/system/latency`.

---

# 46. امنیت و پایداری — ✅ کامل
- [x] Credentials از env vars (`telegram_notifier.py`, `email_notifier.py`)
- [x] Logging + Audit log
- [x] Automatic reconnect / Feed watchdog به‌صورت ماژولِ صریح —
      `feed_watchdog.py` (جدید). بررسیِ عمیق‌تر نشون داد که پاسخ «نه» بود:
      per-symbol backoff در `data_feed.py` و `kill_switch.evaluate_auto`
      (اکثریتِ نمادها) هیچ‌کدوم واقعاً یک سشنِ *تازه* نمی‌سازن روی قطعیِ
      کاملِ فید. حالا: اگه از هیچ نمادی برای `OUTAGE_SECONDS` (۹۰ثانیه)
      هیچ تیکی نیاد، `TSETMCFeed.force_reconnect()` صدا زده می‌شه (سشنِ
      aiohttp بسته می‌شه + backoffِ همه‌ی نمادها ریست می‌شه)، با یک
      کول‌داون (۶۰ثانیه) ضدِ حلقه‌ی reconnectِ دیوانه‌وار. قلاب‌شده بعدِ هر
      سه‌تا `feed.get_ticks()` در `worker_loop` (فازِ OPEN/PRE_OPEN/Kill-
      Switch). endpoint: `GET /api/system/feed_health`.

---

# 47. فازبندی اجرای پروژه — بازچینیِ کامل بر اساس Audit

## ✅ قبلاً انجام شده (فازهای ۱ تا ۴ و بخش زیادی از ۶ تا ۹ رودمپ اصلی)
Data Quality, Normalization, Feature Engine, Microstructure (نسخه‌ی صفِ برتر),
Momentum, Price Structure, MTF, Divergence, Breakout, Options Intelligence,
OI, Contract Selector (نسبی), Risk/Position, Scanner/Watchlist, Journal,
Replay/Backtest (کندل‌محور), Calibration, Walk-forward.

## PHASE A — Regime + Fusion (اولویت اول، تنها گپ هسته‌ای) — ✅ کامل
- [x] Market Regime Engine (بخش ۲۲)
- [x] Decision Fusion Engine + endpoint واحد (بخش ۲ + ۲۳)
- [x] پنل «Current Decision» یکپارچه در فرانت (بخش ۴۱)
- [x] فرمت استاندارد WAIT/Explainability (بخش ۲۴ + ۲۹)

## PHASE B — پرداخت‌های کوچکِ باقی‌مانده — ✅ کامل
- [x] Late Entry پنج‌سطحی، Pullback Engine مجزا (بخش ۱۵-۱۷)
- [x] برچسبِ صریحِ «تخمینی» روی Trade Flow + تفکیکِ انواع Alert (بخش‌های ۵.۳، ۳۰)
- [x] OBI slope, Queue acceleration روی صفِ برتر (بخش ۵)
- [x] Latency measurement (بخش ۴۵) — `latency_monitor.py`
- [x] بررسی/تکمیل Feed watchdog (بخش ۴۶) — `feed_watchdog.py`

## PHASE C — عمق تحلیلی — ✅ کامل
- [x] تطبیق دقیق وزن‌های Contract Selector و Scalp Score bands با فرمول‌های رودمپ
      (بخش‌های ۱۳، ۱۴) — بازبینی و تصمیم‌گیریِ صریح، + «۲ گزینه‌ی جایگزین»
- [x] Setup Analytics کامل بر اساس نوع Entry/Moneyness (بخش ۳۶)
- [x] تفکیک صریح Confidence از Score (بخش ۲۸) — `confidence_engine.py`

## PHASE D — گپ‌های واقعیِ اسکالپر — ✅ کامل
- [x] Position Sizing Engine (بخش ۵۱)
- [x] Queue Streak + RSI Extremity (بخش ۵۲) — `queue_status.py`
- [x] Execution Lag Transparency + گیتِ WAIT (بخش ۵۳)
- [x] Real Fill Tracking (بخش ۵۴)
- [x] Order Flow Proxy (بخش ۵۵)
  <!-- این چک‌لیست قبلاً به‌روز نشده بود؛ خودِ کدِ این ۵ بخش و
       docstringهاشون «✅ کامل» هستن، طبقِ بازبینیِ ۱۳۹۷/۰۶ تأیید شد. -->

## PHASE E — یادگیری — ✅ کامل
- [x] ML baseline روی Journal (بخش ۳۹) — `ml_baseline.py`
- [x] Out-of-sample validation (بخش ۵۶) — split زمانیِ ۸۰/۲۰ در `ml_baseline.train()`
- [x] Drift detection (بخش ۳۹) — `drift_detection.py` + `/api/ml/drift`

## PHASE F — تقویت‌های الهام‌گرفته از دوره‌ی «Algorithmic Trading with
## Python» (freeCodeCamp، Nick McCollum) — ✅ کامل
> این دو مورد از بینِ کلِ محتوای دوره، تنها تکنیک‌هایی بودن که واقعاً به
> این اپ (اسکالپینگِ آپشن، نه Portfolio/Index/Value Investing) می‌خوردن؛
> بقیه‌ی دوره (Equal-Weight S&P 500، Quantitative Value Screener با
> P/E-P/B، Batch API با IEX Cloud) کاملاً خارج از دامنه‌ی این اپه و عمداً
> اضافه نشد. یک دوره‌ی دومِ ۲۲ساعته هم بررسی شد (فایلِ
> `Algorithmic_Trading_Complete_Course...`) و چیزِ جدیدِ قابل‌استفاده‌ای
> نداشت — محتواش عمدتاً پایه‌های numpy/pandas و همون اندیکاتورهای رایج
> (RSI/MACD/VWAP) بود که این اپ همین الان نسخه‌ی پیشرفته‌ترشون رو داره.
- [x] Out-of-sample validation برای ml_baseline (بخش ۵۶، بالا) —
      الهام از تأکیدِ دوره روی این‌که هر مدلی بدونِ Held-out Test
      می‌تونه گمراه‌کننده باشه.
- [x] Momentum Quality / Steadiness Score (بخش ۵۷) — `multi_timeframe.py`
      تابعِ `compute_momentum_quality()` + فیلدِ `mtf_momentum_quality`
      در Verdict. الهام از مفهومِ «High Quality Momentum» دوره (حرکتِ
      پیوسته بهتر از یک جهشِ آخرِ لحظه‌ست، حتی با بازدهِ یکسان) — این‌جا
      با نرخِ تغییرِ به‌ازای دقیقه روی ۶ بازه‌ی زمانیِ موجود (به‌جای
      بازدهِ چندماهه‌ی سهام) پیاده‌سازی شد. کاملاً advisory — نه Gate،
      فقط یک خطِ احتیاطی موقعِ SPIKE.
- [x] پنلِ فرانت‌اندِ ML Advisory + Drift Detection (تبِ Performance) —
      قبلاً این دو تا فقط API بودن، هیچ‌جا نمایش داده نمی‌شدن.
- [x] تکمیلِ Formula Registry (بخشِ ۴۱ سندِ ۱، `REGISTRY_VERSION` از
      ۱.۰ به ۱.۱) — سه موردِ باقی‌مانده‌ای که خودِ فایل صراحتاً «هنوز
      کاتالوگ نشده» علامت زده بود (OI Pressure Map/Max Pain، Contract
      Quality، Setup Library) اضافه شدن.

## PHASE G — Continuation Breakout Setup (از ویدیوی «۳ استراتژیِ
## اسکالپ» کاربر) — ✅ کامل، با یک بخشِ صریحاً ⚠️ REVISED

کاربر یک ویدیوی آموزشیِ اسکالپینگِ سهامِ آمریکایی (Order Flow/Tape
Reading محور) داد و پرسید چه بخشی برای آپشن‌های بورسِ تهران قابل‌پیاده‌سازی
و مفیده. ویدیو سه Setup معرفی می‌کنه:

- [x] **Mean Reversion** — از قبل، از STEP 33 (Setup Library) پیاده بود؛
      کارِ اضافه‌ای لازم نداشت.
- [x] **Continuation Scalp → «ادامه‌ی شکست» (Continuation Breakout)،
      Setupِ نهمِ Setup Library** — تازه اضافه شد. منطق: وقتی
      `false_breakout.py` یک شکست رو بعد از پنجره‌ی تأیید «تأییدشده»
      (`confirmed_breakout_up/down`) اعلام می‌کنه (نه رد شده)، و جهتش
      هم‌راستا با action هست، یک setupِ نام‌دار ثبت می‌شه. اگه هم‌زمان
      `aggressive_volume` (Quote/Tick Rule از `trade_classifier.py`)
      هم هم‌جهت و قوی باشه → `strength: "strong"` (نزدیک‌ترین معادلِ
      این پروژه به «تأییدِ تیپ» که ویدیو روش تأکید می‌کنه)، وگرنه
      `strength: "plain"`. هیچ اندیکاتورِ تازه‌ای ساخته نشد — فقط
      دو ماژولِ از‌قبل‌موجود ترکیب شدن (هم‌الگو با بقیه‌ی Setup Library).
      هم برای سهمِ پایه هم برای هر قراردادِ آپشن خودکار فعاله. ۱۲ تستِ
      واحدِ جدید در `test_setup_library.py`. نشانِ فرانت‌اند: 🚀 (+💪
      وقتی strong).
- [ ] **⚠️ REVISED — «Making the Spread» (بازارسازی):** عمداً پیاده
      نشد. این Setup نیازمندِ گذاشتنِ هم‌زمانِ سفارشِ خرید/فروشِ لیمیت و
      مدیریتِ فعالِ صفِ اولویته — یعنی *اجرای معامله*، نه *سیگنال‌دهی*؛
      با تعریفِ این اپ («دستیارِ تصمیم»، نه ربات‌معامله‌گر) در تضاده.
      همچنین: تأییدِ دقیقِ ویدیو برای هر دو Setupِ دیگه هم («آیا سفارشِ
      بزرگ رفرش شد یا واقعاً خورد؟») نیازمندِ Level 2 لحظه‌ای است که
      TSETMC عمومی منتشر نمی‌کنه (همون محدودیتِ بخشِ ۳.۳/۵.۳ بالا) —
      `aggressive_volume`/`false_breakout` نزدیک‌ترین معادل‌های
      ساختنی‌ان، نه جایگزینِ دقیق. اگه در آینده یک فیدِ Level 2 واقعی
      (یا مشابه) به پروژه وصل بشه، می‌شه این دو مورد رو بازنگری کرد.

## PHASE H — Ichimoku (چندین تایم‌فریم + چندین استراتژی) — ✅ کامل (هسته)، ⚠️ REVISED (بک‌فیلِ اینتردی)

درخواستِ مستقیمِ کاربر، بعد از بررسیِ یک آموزشِ ایچیموکو (فایلِ `2.txt`،
استراتژیِ Kumo Pullback روی ۳۰دقیقه): «انواع تایم‌فریم و استراتژی‌های
ایچیموکو رو داشته باشم». معماری: یک هسته‌ی محاسباتیِ کاملاً مستقل از
تایم‌فریم (`ichimoku.py`) + یک لایه‌ی استراتژی‌های مشترک
(`ichimoku_strategies.py`) که هم روی کندلِ روزانه هم روی کندلِ اینتردی
یکسان کار می‌کنن — فقط منبعِ کندل فرق می‌کنه.

- [x] **`ichimoku.py`** — Tenkan/Kijun/Senkou A/B (خام + جابه‌جاشده)/
      Chikou، روی هر لیستِ `Candle` عمومی. `IchimokuSnapshot` صراحتاً
      `ready_current_cloud=False` می‌مونه با کمتر از ۷۸ کندل (۵۲ برای
      Senkou B + ۲۶ جابه‌جایی) — بدونِ حدس. `cloud_edge_series()` برای
      سنجشِ «تختیِ» لبه.
- [x] **`candlestick_patterns.py`** — تشخیصِ Bullish/Bearish Engulfing
      (بر پایه‌ی بدنه، نه سایه — هم‌راستا با توصیفِ آموزشِ کاربر).
- [x] **`ichimoku_strategies.py`** — نُه استراتژیِ ایچیموکو، همه
      timeframe-agnostic: TK Cross (+ `strength` بر اساسِ جایگاهِ قیمت
      نسبتِ به ابر)، Kijun Cross (+ تأییدِ ابرِ آینده)، Kumo Breakout
      (+ `reversal`: شکستِ ابرِ خلافِ‌رنگ در برابرِ هم‌رنگ)، Kumo Twist
      (چرخشِ *پیش‌بینی‌شده*‌ی رنگِ ابر، چون Senkou ذاتاً رو به جلو
      پروژکت می‌شه)، Chikou Confirmation، Kumo Pullback (پیاده‌سازیِ
      دقیقِ استراتژیِ آموزشِ کاربر: پولبک به لبه‌ی تختِ ابر + چرخشِ هر دو
      خط + تأییدِ Engulfing)، دو واگراییِ STEP 50 — Cloud/Price
      Divergence و Kijun/SenkouB Convergence (هر دو روی
      `ichimoku.find_fractal_pivots`، فرکتالِ ویلیامز هم‌الگو با
      `support_resistance.py`) — و TK Double Cross ازِ STEP 51 (کراسِ
      دوگانه در یک پنجره‌ی کوتاه، معامله در جهتِ کراسِ دوم) —
      + `suggest_stop_target` (حداقل ۱:۳، هم‌الگو با price_offsets.py).
- [x] **`ichimoku_daily.py`** — «گروهِ ۱» (تقریباً رایگان): از همون
      `history_feed.get_daily_history` که `support_resistance.py` هم
      مصرف می‌کنه، بدونِ داده‌ی جدید. کش/رفرش یک‌بار در روز، هم‌الگو با
      support_resistance.py. لوک‌بک ۱۵۰ روزِ تقویمی (حاشیه‌ی امن برای
      ۷۸ کندلِ لازم، با احتسابِ تعطیلات).
- [x] **`bar_aggregator.py`** — کندل‌سازِ زنده‌ی streaming (تیک→OHLCV)
      برای تایم‌فریم‌های اینتردی (۳۰m و ۱h پیش‌فرض، `INTRADAY_TIMEFRAMES`
      قابلِ‌گسترش). به `indicators.SymbolIndicators` وصل شد
      (`ichimoku_bars`، آپدیت‌شونده در همون `update()` که همه‌ی
      اندیکاتورهای دیگه ازش تغذیه می‌شن) — یعنی هم روی سهمِ پایه هم روی
      هر قراردادِ آپشن به‌طور خودکار فعاله، بدونِ تغییر در main.py.
- [x] **`ichimoku_intraday.py`** — لایه‌ی نازکِ روی `bar_aggregator`،
      همون هسته/استراتژی‌های بالا رو صدا می‌زنه.
- [x] **۲۸ تستِ واحدِ جدید** (`test_ichimoku.py`,
      `test_candlestick_patterns.py`, `test_ichimoku_strategies.py`,
      `test_bar_aggregator.py`, `test_ichimoku_daily.py` + ۲ تستِ
      اضافه در `test_indicators.py`) — همه سبز، بدونِ شکستنِ ۱۰۳۴
      تستِ قبلی.
- [x] **STEP 49** (بازبینیِ ۲۱ فایلِ آموزشیِ اضافه‌ی کاربر): TK Cross
      و Kumo Breakout قوی‌تر شدن (`strength`/`reversal`)، استراتژیِ
      جدیدِ Kijun Cross اضافه شد، و `setup_library.classify_ichimoku`
      عمومی شد تا هر شش استراتژیِ آن‌موقع رو به‌عنوانِ Setup نشون بده
      (قبلش فقط Kumo Pullback دیده می‌شد).
- [x] **STEP 50** (بازبینیِ ۱۵ فایلِ آموزشیِ دومِ کاربر): دو واگراییِ
      خطوطِ ایچیموکو اضافه شد — Cloud/Price Divergence و
      Kijun/SenkouB Convergence — با زیرساختِ پیوت‌یابیِ مشترکِ جدید
      (`ichimoku.find_fractal_pivots`/`cloud_edge_at`/`tenkan_at`/
      `kijun_at`). بقیه‌ی این دو دسته فایل (تکرارِ کوالیتی‌لاینِ
      بیگ‌جی‌موکو، ترفندهای سشنِ فارکس/طلا، اندیکاتورهای شخصیِ
      بدون‌فرمول، «واگراییِ ابرِ کوچیک/بزرگ»، «دایورجنس‌کراس») عمداً
      پیاده نشدن — دلیلِ هرکدوم در docstringِ بالای
      `ichimoku_strategies.py` و در حافظه‌ی چت هست.
- [x] **STEP 51** (اولویتِ بعدیِ بک‌لاگ): `tk_double_cross` — دو TK
      Cross در `TK_DOUBLE_CROSS_WINDOW` (۱۲) کندلِ اخیر، در جهتِ مخالفِ
      هم، که کراسِ دوم دقیقاً همین کندلِ زنده‌ی الان باشه — طبقِ فایلِ
      ۲۰ی کاربر، کراسِ اول معمولاً فیک‌اوته و باید در جهتِ کراسِ دوم
      معامله کرد. `setup_library.classify_ichimoku` حالا نُه استراتژی
      رو نشون می‌ده.
- [x] **STEP 52** (اولین موردِ بک‌لاگِ ایچیموکو): `kijun_flat_range` —
      کیجونسنِ تخت (۸ کندل، `flatness_pct` ≤ ۰٫۳٪) + فاصله‌ی قیمت از
      کیجون ≥ ۱٪ → سیگنالِ *بازگشت به میانگین* به سمتِ کیجون
      (`target` = کیجون؛ حد ضرر عمداً پیشنهاد نمی‌شه). ⚠️ فایلِ
      آموزشیِ مبدأِ این آیتم در این نشست در دسترس نبود؛ منطق از مفهومِ
      استانداردِ Flat Kijun-sen پیاده شد و هر سه آستانه هیورستیکه.
      `setup_library.classify_ichimoku` حالا ده استراتژی رو نشون می‌ده.
      همراهِ این استپ یک باگِ واقعیِ قدیمی هم بسته شد:
      `execution_quality.compute({})` به‌جای نمره‌ی خنثی `None` برمی‌گردوند
      (`if not contract` دیکشنریِ خالی رو «بدونِ قرارداد» می‌گرفت؛ حالا
      `is None`) — تنها تستِ شکسته‌ی سوییت.
- [x] **STEP 53** (دومین موردِ بک‌لاگ): `cloud_thickness` — ضخامتِ ابر
      به‌عنوانِ قدرتِ حمایت/مقاومت. ضخامتِ ابرِ همین‌الان (٪ از میانه‌ی
      ابر) با ۳۰ کندلِ قبلیِ *همون نماد/تایم‌فریم* مقایسه می‌شه (صدکِ
      میانی، mid-rank) → `level` = thin/normal/thick. استراتژیِ مستقل
      نیست؛ به‌عنوانِ فیلدِ `cloud_thickness` به خروجیِ `kumo_pullback` و
      `kumo_breakout` در `classify_all` الصاق می‌شه و در note‌ی Setup
      (`setup_library`) نمایش داده می‌شه — سیگنالی رو حذف/ایجاد نمی‌کنه.
      `None` (بدونِ حدس) اگه ابرِ الان آماده نیست یا کمتر از ۱۰ نمونه‌ی
      قبلی داریم. حین تست یک باگِ واقعی پیدا و همون‌جا بسته شد: صدکِ اولیه
      با «≤» در بازارِ تخت (همه‌ی ضخامت‌ها صفر) اشتباهاً `thick` می‌داد؛
      حالا mid-rank است و می‌شه `normal`. ⚠️ آستانه‌های صدک (۷۵/۲۵) و
      پنجره هیورستیکن؛ فایلِ آموزشیِ مبدأ در دسترس نبود؛ «ضخیم=قوی‌تر»
      روی دیتای TSETMC بک‌تست نشده.
- [x] **STEP 54** (دو موردِ بک‌لاگ در یک تابع): `kumo_fib_pullback` —
      «فیبوی پولبکِ کراسِ کمو» + «اعتبارِ هدف با گذرِ زمان (کراسِ کمو)».
      آخرین شکستِ ابر تا ۲۰ کندلِ اخیر پیدا می‌شه (همون منطقِ
      `kumo_breakout` روی هر اندیسِ تاریخی)؛ اگه قیمت به ناحیه‌ی
      ۳۸٫۲٪–۶۱٫۸٪ِ حرکتِ پس از شکست (±۰٫۰۵) پولبک زده، کندلِ آخر هم‌جهتِ
      شکست بسته، و قیمت هنوز آن‌سوی لبه‌ی ابره → سیگنال با
      `retracement_pct`/`nearest_fib`، اهدافِ retest و اکستنشنِ ۱٫۶۱۸،
      حد ضرر پشتِ لبه‌ی ابر و `rr_retest` (عمداً به R:R دلخواه
      دست‌کاری نمی‌شه — ممکنه نزدیکِ ۱:۱ باشه). «اعتبارِ هدف با گذرِ زمان»
      به‌شکلِ **انقضا** پیاده شد: `age_candles` در خروجی و بعد از ۲۰ کندل
      سیگنالی داده نمی‌شه. ⚠️ این تفسیرِ من از دو آیتمه — فایلِ مبدأ در
      دسترس نبود؛ همه‌ی پارامترها هیورستیک/فیبوناچیِ استاندارد و روی
      TSETMC بک‌تست نشده. `setup_library` حالا یازده استراتژی رو نشون
      می‌ده (فرانت‌اند بدونِ تغییر).
- [x] **STEP 55** (سه موردِ بک‌لاگ + یک ستاپِ ترکیبی) — ⚠️ **هر سه تفسیرِ
      من از یک اسمِ کوتاه‌اند، نه کدنویسیِ قاعده‌ی دقیقِ ویدیوها**
      (فایل‌های مبدأ در دسترس نبود؛ اعتماد پایین‌تر از بقیه‌ی PHASE H،
      فقط advisory، بدونِ بک‌تست روی TSETMC):
      - `cci_series` (CCI(۲۰) کلاسیک) + `cloud_position` (above/below/inside).
      - `stuck_cloud_cci` («ابرِ جامونده+CCI»): ≥۵ کندلِ پیاپیِ قبلی داخلِ
        ابر + عبورِ CCI از ±۱۰۰ در همین کندل.
      - `hidden_divergence` (روی CCI و پیوت‌های فرکتال): کفِ بالاترِ
        قیمت + کفِ پایین‌ترِ CCI → BUY؛ سقفِ پایین‌تر + سقفِ بالاتر → SELL؛
        پیوتِ دوم حداکثر ۸ کندلِ قبل و ≥۳ کندل از اولی.
      - `kijun_liquidity_zone` («ناحیه‌ی نقدینگیِ تنکان‌ترن+کیجون‌فلت»):
        کیجونِ تخت + لمسِ ناحیه در ۳ کندلِ اخیر + چرخشِ تنکان در همین
        کندل؛ با `kijun_flat_range` (فاصله‌گرفتن و بازگشت) فرق داره.
      - «اسکلپِ مولتی‌تایم‌فریم با واگراییِ مخفی»: در
        `setup_library.classify_ichimoku` ساخته می‌شه
        (`ichimoku_mtf_hidden_divergence`) — واگراییِ مخفیِ یک تایم‌فریم
        + هم‌جهت‌بودنِ *همه‌ی* تایم‌فریم‌های بالاترِ آماده (BUY: قیمت بالای
        ابر، SELL: پایینِ ابر). برای این، `classify_all` یک کلیدِ غیرِ
        استراتژیِ `context` هم برمی‌گردونه (`{"cloud_position": ...}`)؛
        هیچ مصرف‌کننده‌ای روی مقادیرِ dict حلقه نمی‌زنه (بررسی شد).
      `setup_library` حالا چهارده استراتژی (+ستاپِ MTF) رو نشون می‌ده.
- [x] **STEP 56** (فایلِ ۱ کاربر — «کاملِ‌ترین استراتژیِ ایچیموکو»):
      `classic_confluence` — یک ستاپِ *ترکیبی* جدید (نه یک تکه/آیتمِ
      مستقل مثلِ بقیه‌ی STEP‌های PHASE H) که چهار شرطِ کلاسیکِ ورودِ
      ایچیموکو رو هم‌زمان روی همون کندلِ آخر چک می‌کنه: (۱) بسته‌شدنِ
      قیمت بیرونِ ابرِ همین‌الان، (۲) رنگِ ابرِ همین‌الان هم‌جهت، (۳)
      تنکان بالا/پایینِ کیجون، (۴) لاگینگ‌اسپن (چیکو) از ابرِ
      هم‌موقعیتش رد شده — تابعِ کمکیِ جدیدِ `_chikou_vs_cloud`
      (`ich.cloud_edge_at`)، که **با `chikou_confirmation`ِ موجود فرق
      داره**: اون یکی close رو با close۲۶‌دوره‌قبل مقایسه می‌کنه، این
      یکی چیکو رو با خودِ *ابرِ* هم‌موقعیتش. کاندلِ ورود = اولین کندلی
      که هر چهارتا هم‌زمان برقرارن (کندلِ قبل چک می‌شه که هر چهارتا
      برقرار نبوده، وگرنه هر کندلِ بعدی هم دوباره سیگنال می‌داد). حد
      ضرر = پشتِ ابر، هدف = ۲ برابرِ ریسک (`CLASSIC_CONFLUENCE_MIN_RR`،
      عینِ گفته‌ی ویدیو: «two times your risk» — نه ۱:۳ِ `kumo_pullback`).
      نکته‌ی خروجِ ویدیو («لاگینگ‌اسپن از قیمت رد شد → خارج شو») پیاده
      نشد چون از نظرِ ریاضی دقیقاً همون `chikou_confirmation`ِ موجوده،
      فقط با اسمِ دیگه — کدِ تکراری اضافه نشد.
      ⚠️ صداقت: چهار شرط و R:R دقیقاً از رویِ ویدیو استخراج شدن؛ فقط
      منطقِ «کندلِ ورود = اولین باری که همه‌شون هم‌زمان برقرارن» انتخابِ
      این پیاده‌سازیه (ویدیو این رو با چشم، از رویِ چارت، پیدا می‌کنه).
      روی داده‌ی واقعیِ TSETMC بک‌تست نشده. تستِ ساختگی روی رمپِ تمیزِ
      صعودی/نزولی تأیید کرد که سیگنال دقیقاً یک‌بار (روی اولین کندلِ
      واجدِ شرایط) فعال می‌شه و روی کندل‌های بعدی که شرایط هنوز برقرارن
      دیگه تکرار نمی‌شه. `classify_ichimoku`/`_ICHIMOKU_STRATEGY_LABELS`
      و `classify_all` بدونِ تغییرِ منطق فقط با یک کلیدِ جدید وصل شدن
      (دقیقاً طبقِ طراحیِ اکستنشن‌پذیرِ PHASE H-1). فرانت‌اند بدونِ
      تغییر (همون `setupsBadge()`ی عمومی). `setup_library` حالا
      پانزده استراتژی (+ستاپِ MTF) رو نشون می‌ده.
- [ ] **باقی‌ماندهٔ بک‌لاگِ ایچیموکو — هنوز عمداً پیاده نشده:**
      واگراییِ ابرِ کوچیک/بزرگ (قاعده‌ی عددی نداره)، دایورجنس‌کراس
      (stateful — نیازِ به بازطراحی).

- [x] **STEP 57 (گزارشِ باگِ کاربر — «۱۱ نماد صفِ فروش بودن ولی نبض
      می‌گفت تقاضا غالب»):** `market_pulse.py` کاملاً بازنویسی شد.
      علتِ باگ یک اشتباهِ علامت نبود، چهار عیبِ مستقلِ طراحیِ شاهد بود:
      (۱) حجمِ خامِ کال/پوت جهت نداره — هر معامله یک خریدار و یک
      فروشنده داره، حجمِ بالای کال فقط یعنی فعالیت، نه تقاضا؛ چون بازارِ
      پوتِ ایران نحیفه این جزء ساختاراً روی ‎+۹۹ قفل بود (وزنِ ۲۵٪).
      (۲) رشدِ خامِ OIِ کال هم جهت نداره — رشدِ OI هم‌زمان با افتِ قیمتِ
      کال یعنی فروشِ تعهدی (نزولی)، نه Build-upِ صعودی؛ منطقِ درستش از
      قبل در `oi_engine._classify` بود ولی market_pulse ازش استفاده
      نمی‌کرد. (۳) صفِ خرید/فروشِ خودِ نمادها (`queue_status.py`)
      صریح‌ترین شاهدِ موجود بود و اصلاً خونده نمی‌شد. (۴)
      `order_book_imbalance`ِ خودِ سهم در main.py محاسبه می‌شد ولی در
      payload گذاشته نمی‌شد، پس نبض فقط دفترِ نازکِ آپشن‌ها رو می‌دید.
      رفعش: شش جزءِ جدید با وزنِ ۳۰/۲۲/۱۸/۱۵/۸/۷ (صف → دفترِ سهم →
      breadth → جهتِ واقعیِ OI → سهمِ پوت نسبت به نُرمِ خودش → دفترِ
      آپشن)، + یک **گاردِ سختِ صف** که مستقل از جمعِ وزنی امتیاز رو
      کلمپ می‌کنه اگه ≥۵۰٪/۸۰٪ نمادها در یک صف قفل باشن (تضمینِ صریح
      که دیگه خلافِ چیزی که رویِ تابلو دیده می‌شه نگه، حتی اگه یک وزنِ
      دیگه بعداً خراب بشه)، + `score_ex_queue` که به
      `queue_status.assess_pressure` داده می‌شه (نه `score`) تا صف به
      خودش رأی نده. نُرمِ سهمِ پوت (`_put_share_baseline`) حالا در
      `last_state.json` ماندگار می‌شه (`market_pulse.export_state`/
      `load_state`، وصل‌شده در `main.py`) — وگرنه بعدِ هر ری‌استارت ۲۰
      چرخه خاموش بود.
      ⚠️ صداقتِ مهم — **چرا این روی دیتای تاریخیِ TSETMC قابل بک‌تست
      نیست:** `backtest.py`/`history_replay.py` فقط ریزمعاملات (تیکِ
      قیمت/حجم، از `Trade/GetTradeIntraDay`) رو دارن، نه اسنپ‌شاتِ
      تاریخیِ دفترِ سفارش (bid/ask) و نه تاریخچه‌ی OIِ زنجیره‌ی آپشن —
      این پروژه هیچ‌وقت این دو رو ذخیره نکرده (نه فقط «هنوز تست نشده»؛
      اصلاً دیتاش موجود نیست). پس جزءهای `queue`/`underlying_book`/
      `oi_trend` این ماژول ساختاراً قابلِ بک‌تستِ تاریخی نیستن؛ فقط با
      سناریوهای دستی (نگاه کن به `tests/test_market_pulse.py`،
      به‌خصوص `test_eleven_sell_queues_must_never_report_demand` —
      رگرسیونِ دقیقِ همین باگ) و بعداً با پاسخِ زنده‌ی TSETMC قابل
      اعتبارسنجی‌ان. وزن‌های ۳۰/۲۲/۱۸/۱۵/۸/۷ انتخابِ مهندسی‌ان، نه
      کالیبره‌شده با دیتای واقعی.
      **فایل‌های تغییریافته:** `backend/market_pulse.py` (بازنویسیِ
      کامل)، `backend/main.py` (اتصالِ `order_book_imbalance` به
      payload + `score_ex_queue` به `assess_pressure` + ماندگاریِ
      state)، `backend/tests/test_market_pulse.py` (بازنویسیِ کامل).
      **⚠️ یادآوریِ آپدیت — این پاراگراف را قبل از جایگزینیِ هر نسخه‌ی
      قدیمی‌ترِ این سه فایل بخوان:** اگه نسخه‌ی جدیدی از این پروژه
      (از منبعِ دیگه/بک‌آپِ قدیمی/چت دیگه) جایگزینِ این‌ها بشه، منطقِ
      بالا (شش‌جزئی + گاردِ صف) از بین می‌ره و باگِ گزارش‌شده برمی‌گرده
      — بدونِ خطا، بدونِ هشدار، فقط دوباره وارونه. قبل از overwrite:
      (۱) این سه فایل رو جدا نگه دار/دیف بگیر، (۲) اگه نسخه‌ی جدید
      واقعاً market_pulse رو تغییر داده، بگو STEP بعدی (۵۸+) چیه و
      همین‌جا اضافه کن — این بلاک هرگز پاک/overwrite نشه، فقط STEPِ
      جدید زیرش اضافه بشه.

- [x] **STEP 58 (Price Action کلاسیک — پارتِ ۱، ۲، ۷ از ۸):** کاربر
      هشت ویدیوی آموزشیِ «Price Action» رو بررسی و خلاصه کرد
      (`P1.zip` — Thrust/Runway، Pin Bar+روند، Inside/Outside،
      MTF-تأیید، Doji+S/R، Harami+breakout، Wave-context، W/H&S).
      تأییدِ مهم: هر ۸ الگو فقط روی OHLC کار می‌کنن (نه order book/
      Level 2/aggressor-side) — پس محدودیتِ همیشگیِ TSETMC مانعِ
      هیچ‌کدوم نیست. این STEP فقط سه موردِ کاملاً بدونِ‌ابهام رو پیاده
      کرد؛ ۵ موردِ باقی در بک‌لاگِ زیر برای STEPهای بعدی موندن.
      (۱) **ماژولِ جدیدِ `price_action_patterns.py`** — `thrust_label`
      (کندلِ جاری بالاتر از high/پایین‌تر از lowِ کندلِ قبل بسته شده)
      + Runway (`scan_runway`/`pending_runway`: شکستِ محدوده‌ی ۵روزه
      با تأییدِ نگه‌داشتنِ ۵روزِ بعد — منطقِ pending/confirmed دقیقاً
      هم‌الگو با `false_breakout.FalseBreakoutTracker` ولی روی کندلِ
      روزانه). کش/رفرشِ روزی‌یک‌بار، ساختارِ کدش عیناً کپیِ
      `support_resistance.py` (refresh/refresh_all/get/needs_refresh).
      (۲) **`candlestick_patterns.py`** — `is_inside_bar`/
      `inside_outside_label` اضافه شد. Outside عمداً یک تابعِ جدا
      نگرفت چون طبقِ خودِ ویدیو دقیقاً همون Engulfingِ موجوده (بدنه‌
      محور)؛ Inside برخلافِ Engulfing بر پایه‌ی high/low کامل تعریف
      می‌شه (کندلِ جاری کاملاً داخلِ رنجِ کندلِ قبل).
      (۳) **`support_resistance.py` — Role Reversal:** گپی که خودِ
      داکیومنتِ این فایل از قبل صراحتاً اعتراف کرده بود
      («این فلیپِ نقش رو به‌طورِ صریح مدل نمی‌کنه») حالا پر شد:
      `_track_role_flip` هر چرخه طرفِ هر zone (بالای/پایینِ قیمتِ
      لحظه) رو با چرخه‌ی قبل مقایسه می‌کنه و رویدادِ `role_flip` رو در
      خروجیِ `nearest_levels` برمی‌گردونه (تا `FLIP_EVENT_VISIBLE_SECONDS`
      بعدش هم قابل‌مشاهده می‌مونه) — هم‌الگو با
      `oi_engine.track_wall_shift`. منطقِ خودِ طرف‌بندی (سوئینگ‌های بالا
      = کاندیدِ مقاومت) تغییر نکرد، فقط یک لایه‌ی ردیابیِ رویداد روش
      اضافه شد.
      **وایرینگِ main.py:** `import price_action_patterns` +
      `payload["price_action"]` در تیکِ زنده + `price_action_worker_loop`
      (رفرشِ روزانه، هم‌الگو با `support_resistance_worker_loop`) +
      دو endpointِ دیباگ (`/api/price_action/{symbol}` و
      `/api/price_action/refresh`). فایل‌های حساسِ STEP 57
      (`market_pulse.py`, اتصالاتِ `order_book_imbalance`/
      `score_ex_queue`/`export_state` در `main.py`,
      `test_market_pulse.py`) دست نخوردن — تأییدِ مجدد:
      `test_market_pulse.py` (۲۳ تست) بعد از این STEP هم پاس می‌شه.
      **فرانت‌اند بدونِ تغییر** — چون خودِ `support_resistance` هم هنوز
      در UI نمایش داده نمی‌شه (فقط backend/API)؛ `price_action` هم فعلاً
      همون الگو رو دنبال کرد.
      ۵۴ تستِ جدید (`test_price_action_patterns.py` + اضافه‌شده به
      `test_candlestick_patterns.py`/`test_support_resistance.py`) —
      یک باگِ off-by-one در `pending_runway` (مرزِ محدوده‌ی جست‌وجوی
      نامزدِ شکست) همین‌جا پیدا و رفع شد. فولِ سوییت: **۱۱۸۰/۱۱۸۰ پاس**
      (از ۱۱۲۶)، `import main` تمیز، `node --check` روی اسکریپتِ
      inline فرانت‌اند تمیز (فرانت‌اند اصلاً تغییر نکرده بود).
      **بک‌لاگِ باقی‌مانده از این ۸ پارت (اولویتِ پیشنهادی برای
      STEPهای بعدی):**
      - پارتِ ۵ (Harami = Inside موجود، صبر برای شکست، ترجیحاً H1+) —
        نیازِ به منطقِ شبیهِ `false_breakout.py` رویِ Inside bar.
      - پارتِ ۳ (تأییدِ Pin Bar با شکستِ Inside bar در تایم‌فریمِ
        پایین‌تر) — ترکیبی، از `multi_timeframe.py` استفاده می‌کنه؛
        بهتره بعد از پارتِ ۲ (Spike/Pin) پیاده بشه.
      - پارتِ ۲، بخشِ Spike/Pin (هنوز پیاده نشده در این STEP): Pin Bar
        با فیلترِ روند (بدنه‌ی کوچیک+سایه‌ی بلند، فقط خلافِ روندِ
        جاری).
      - پارتِ ۴ (Doji رویِ حمایت/مقاومت/تنکان‌سن) — reuse
        `support_resistance.nearest_levels` (حالا هم با role_flip).
      - پارتِ ۸ (W Top/Bottom + Head&Shoulders، با تأکیدِ ویدیو که
        فقط شکلِ ظاهری کافی نیست، تا نک‌لاین نشکنه) — نیازِ به تعمیمِ
        `support_resistance._find_swings` رویِ توالیِ A-B-C-D-E + تأییدِ
        شکستِ نک‌لاین. بزرگ‌ترین کارِ باقی‌مونده از این ۸ پارت.
      - پارتِ ۶ (Wave/HH-HL vs LH-LL) — طبقِ خودِ ویدیو یک سیگنالِ
        ورودِ مستقل نیست، فقط context؛ به‌عنوانِ یک فیلدِ توصیفی
        (شبیهِ `regime_detail`) نه یک الگوی گیت‌کننده پیاده بشه.

- [x] **STEP 59 (Price Action کلاسیک — پارتِ ۵ از ۸: Harami + انتظار
      برای شکست):** طبقِ اولویتِ پیشنهادی‌ای که خودِ STEP 58 ثبت کرده
      بود. Harami دقیقاً همون Inside bar‌یِ STEP 58 است — چیزِ تازه‌ای
      اختراع نشد؛ فرقش اینه که به‌خودیِ‌خود سیگنالِ ورود نیست، باید صبر
      کرد تا قیمت از سقف/کفِ کندلِ مادر (prev) بیرون بزنه. ویدیو تأکید
      داره این الگو در H1+ دنبال بشه نه M5 (سفارشِ کافی جمع نمی‌شه).
      **ماژولِ جدیدِ `harami_setup.py`** — `HaramiTracker`، دو لایه‌ی
      جدا (هم‌الگو با `false_breakout.py`): تشخیصِ خودِ Inside فقط روی
      کندل‌های *بسته‌شده* (`on_new_closed_candle`)، ولی انتظار برای
      شکست روی قیمتِ زنده‌ی هر تیک (`check_breakout`) — چون این پروژه
      یک دستیارِ اسکالپِ real-time‌ه و صبرکردنِ ۶۰ دقیقه‌ی دیگه برای
      بسته‌شدنِ یک کندلِ H1 کاملِ دیگه عملاً بی‌فایده بود. ستاپِ حل‌نشده
      بعد از `MAX_WAIT_CANDLES=5` کندلِ بدونِ شکست منسوخ می‌شه؛ رویدادِ
      تأییدشده تا `EVENT_VISIBLE_SECONDS=300` بعدش هم قابل‌مشاهده
      می‌مونه (هم‌الگو با `false_breakout.EVENT_VISIBLE_SECONDS`).
      **وایرینگ:** `indicators.SymbolIndicators` حالا یک `harami:
      HaramiTracker` داره + متدِ `_update_harami` که از کندل‌های
      *بسته‌شده*‌ی همون `ichimoku_bars` (STEP 48) تغذیه می‌شه — اولویت
      با تایم‌فریمِ 1h؛ اگه 1h هنوز کمتر از ۲ کندلِ بسته‌شده داشته باشه
      (چند روزِ اولِ اجرا)، 30m به‌عنوانِ fallback به کار می‌ره، ولی
      وقتی 1h آماده شد دیگه همیشه همونه (طبقِ توصیه‌ی ویدیو). چون
      `ichimoku_bars` خودش هم روی سهمِ پایه هم روی هر قراردادِ آپشن
      جداگانه اجرا می‌شه، Harami هم خودکار روی هر دو کار می‌کنه —
      بدونِ داده‌ی تازه. `decision_engine.evaluate` حالا `harami_info
      = ind.harami.check_breakout(price)` رو می‌خونه و advisory-only
      (مثلِ fbo) یک reason اضافه می‌کنه وقتی شکست هم‌جهتِ action باشه
      یا یک ستاپ در انتظاره؛ فیلدِ جدیدِ `Verdict.harami` به
      `verdict_to_dict` (سطحِ سهم) و به `contract["signal"]["harami"]`
      (هر قراردادِ آپشن) وصل شد. یک endpointِ دیباگِ جدید هم اضافه شد:
      `/api/harami/{symbol}` (هم‌الگو با `/api/false_breakout/{symbol}`).
      **فرانت‌اند بدونِ تغییر** — هم‌راستا با پیشینه‌ی STEP 58
      (false_breakout/regime_detail هم در UI نمایش داده نمی‌شن، فقط
      در reasons متنی ظاهر می‌شن که همین‌جا هم رعایت شد).
      ۹ تستِ جدید (`test_harami_setup.py`، زمانِ دیواری با monkeypatch
      روی `harami_setup.time.time`، هم‌الگو با `test_false_breakout.py`)
      — همه سناریوها: waiting/confirmed_up/confirmed_down/
      expiry-after-max-wait/event-visible-then-expires/replace-open-
      setup-with-new-inside/idempotent-same-candle-ts. فولِ سوییت:
      **۱۱۸۹/۱۱۸۹ پاس** (از ۱۱۸۰)، `import main` تمیز، `test_market_pulse.py`
      (۲۳ تست، هم‌الگو با هشدارِ UPDATE_NOTES_STEP57) جداگانه دوباره
      تأیید شد، `node --check` روی frontend تمیز (فرانت‌اند تغییری نکرد).
      **بک‌لاگِ باقی‌مانده از این ۸ پارت:** پارتِ ۲ (Spike/Pin با فیلترِ
      روند) → پارتِ ۳ (تأییدِ Pin با شکستِ Inside در تایم‌فریمِ پایین‌تر،
      از `multi_timeframe.py` استفاده می‌کنه) → پارتِ ۴ (Doji رویِ
      S/R) → پارتِ ۸ (W/H&S، بزرگ‌ترینِ باقی‌مونده) → پارتِ ۶ (Wave،
      context-only).

- [x] **STEP 60 (Price Action کلاسیک — پارتِ ۲ از ۸: Spike Low/High،
      یعنی Pin Bar + فیلترِ روند):** طبقِ اولویتِ پیشنهادی‌ای که خودِ
      STEP 58/59 ثبت کرده بودن. نکته‌ی کلیدیِ ویدیو (پارتِ ۲، `P1.zip`)
      این بود که خودِ ویدیو صریحاً یک مثالِ ضدونقیض می‌آره: یک کندلِ
      دقیقاً هم‌شکلِ پین‌بار که وسطِ یک روندِ صعودی ظاهر می‌شه — و تأکید
      می‌کنه این Spike Low نیست، چون قبلش روندِ نزولی در جریان نبوده؛
      کسی که فقط شکلِ کندل رو نگاه کنه اشتباه می‌کنه. پس این STEP دو
      شرطِ کاملاً مستقل رو با هم می‌سنجه، نه فقط شکلِ کندل.
      **اضافه‌شده به `price_action_patterns.py` (بدونِ ماژولِ جدید —
      همون فایلِ STEP 58، چون این هم دقیقاً همون معماریِ روزانه/کش‌شونده‌
      ی Thrust/Runway رو لازم داره):**
      (۱) `pin_bar_direction(c)` — فقط شکلِ کندل: بدنه حداکثر
      `PIN_BODY_RATIO_MAX=0.35` از کلِ رنج، سایه‌ی غالب حداقل
      `PIN_WICK_RATIO_MIN=0.55` از کلِ رنج؛ خروجی `"bullish"`
      (سایه‌ی پایینِ بلند) / `"bearish"` (سایه‌ی بالای بلند) / `None`.
      (۲) `spike_label(days, idx, lookback=SPIKE_TREND_LOOKBACK=10)` —
      شکلِ کندل را با `pin_bar_direction` می‌سنجد و *هم‌زمان* دو شرطِ
      زمینه را چک می‌کند: سایه باید به‌وضوح پایین‌تر/بالاتر از لوها/های‌
      های `lookback` روزِ قبل بزنه بیرون، و closeِ روزِ قبل از پین‌بار
      باید نسبت به closeِ `lookback` روز قبل‌تر هم‌جهت باشه (پایین‌تر
      برای Spike Low، بالاتر برای Spike High) — دقیقاً همون معیارِ
      ساده‌ای که برای Thrust/Runway هم استفاده شده بود، نه یک موتورِ
      روندِ جداگانه. خروجی: `{"label": "spike_low"|"spike_high",
      "wick_price": ...}` یا `None`.
      **وایرینگ:** `compute()` حالا یک کلیدِ جدید `"pin_bar"` هم
      برمی‌گردونه (روی آخرین کندلِ روزانه)؛ چون `main.py` از قبل (STEP
      58) کلِ خروجیِ `price_action_patterns.get(sym)` رو بدونِ تغییر به
      `payload["price_action"]` وصل کرده بود، **main.py هیچ تغییری
      نخواست** — فقط یک کلیدِ جدید در همون dict ظاهر می‌شه.
      **فرانت‌اند بدونِ تغییر** — هم‌راستا با پیشینه‌ی STEP 58/59.
      **advisory-only** — این هم مثلِ last_thrust/runway هیچ‌جا
      decision_engine رو گیت نمی‌کنه، فقط نمایشی/API‌ه (برخلافِ harami
      که در STEP 59 به‌عمد به decision_engine وصل شد، چون آن‌جا سیگنالِ
      «انتظار برای شکست» روی تیکِ زنده معنا داشت؛ Spike/Pin اینجا یک
      برچسبِ توصیفیِ روزانه‌ست، دقیقاً هم‌رتبه‌ی Thrust/Runway).
      **صداقت:** `PIN_BODY_RATIO_MAX`/`PIN_WICK_RATIO_MIN`/
      `SPIKE_TREND_LOOKBACK` هیورستیک‌ان، هنوز روی داده‌ی زنده کالیبره
      نشدن — دقیقاً مثلِ بقیه‌ی آستانه‌های این فایل (BREAKOUT_PERIOD/
      HOLD_PERIOD در STEP 58).
      ⚠️ یک رگرسیونِ کوچیک این‌جا پیدا و رفع شد: تلاشِ اولیه یک
      `min_needed` سخت‌گیرانه‌تر (بر اساسِ `SPIKE_TREND_LOOKBACK`) به
      `compute()` اضافه کرده بود که باعث می‌شد Thrust/Runway هم زودتر
      از قبل با «سابقه‌ی کافی نیست» بلاک بشن (یک تستِ موجود همین رو
      گرفت: `test_compute_with_sufficient_history`). رفعش: `min_needed`
      دوباره فقط بر اساسِ `BREAKOUT_PERIOD`ه؛ `spike_label` خودش وقتی
      `idx < lookback` باشه بی‌خطر `None` برمی‌گردونه، پس نیازی به
      سخت‌گیریِ سراسری نبود.
      ۱۷ تستِ جدید در `test_price_action_patterns.py`
      (`pin_bar_direction` + `spike_label` + وایرینگِ `compute`، شاملِ
      رگرسیونِ دقیقِ همون مثالِ ضدونقیضِ ویدیو:
      `test_spike_low_rejected_when_context_is_uptrend`).
      **⚠️ محدودیتِ اجرا در همین محیط:** `pytest`/`fastapi`/`aiohttp` در
      این sandbox قابلِ نصب نبودن (بدونِ دسترسیِ شبکه)، پس فولِ سوییتِ
      رسمی (`pytest`) این‌بار اجرا نشد؛ به‌جاش هرسه‌یِ ۱۷ تستِ جدید +
      ۳۱ تستِ از‌قبل‌موجودِ همین فایل (بدونِ آن‌هایی که به فیکسچرِ
      `monkeypatch` نیاز دارن) با یک harness دستیِ import-mock اجرا و
      همگی سبز تأیید شدن. فایل‌های دیگه (`main.py`, `indicators.py`,
      `candlestick_patterns.py`, `harami_setup.py`) دست نخوردن —
      دیف‌شده و تأیید شد.
      **بک‌لاگِ باقی‌مانده از این ۸ پارت:** پارتِ ۳ (تأییدِ Pin با شکستِ
      Inside در تایم‌فریمِ پایین‌تر) → پارتِ ۴ (Doji رویِ S/R) → پارتِ ۸
      (W/H&S) → پارتِ ۶ (Wave، context-only).

- [x] **STEP 61 (Price Action کلاسیک — پارتِ ۳ از ۸: تأییدِ Spike/Pin
      با شکستِ Inside bar در تایم‌فریمِ پایین‌تر):** طبقِ ویدیو، یک
      Spike/Pin روی چارتِ روزانه به‌تنهایی برای اعتمادِ کافی کافی نیست
      («whether you can be confident enough to place buy here while
      looking at a chart real time is the most important thing») —
      راهِ ویدیو: زوم به H1 و دنبالِ یک Inside bar که هم‌جهت می‌شکنه.
      **چیزِ جدیدی محاسبه نشد** — این پروژه از STEP 59 دقیقاً همین
      تعقیبِ Inside-تا-شکست رو روی H1 زنده انجام می‌ده
      (`harami_setup.HaramiTracker`، از طریقِ `ind.harami`/
      `verdict.harami`). فقط یک تابعِ سنجشِ توافق اضافه شد:
      `price_action_patterns.mtf_confirmation(pin_bar, harami_status)`
      — اگه Spikeِ روزانه (STEP 60) و وضعیتِ زنده‌ی Haramiِ H1 (STEP 59)
      هم‌جهت باشن (`spike_low`↔`confirmed_up`، `spike_high`↔
      `confirmed_down`) → `confirmed: true`؛ اگه یک Insideِ H1 هنوز باز
      و در انتظارِ شکسته (`waiting`) → `pending: true` (اطمینانِ کمتر،
      طبقِ توصیه‌ی ویدیو به «نگاه‌کردن برای شواهدِ بیشتر»)؛ وگرنه هیچ‌کدوم.
      **وایرینگِ main.py:** `payload["price_action"]["mtf_confirmation"]`
      در هر دو مسیرِ ساختِ payload ست شد.
      ⚠️ **یک باگِ واقعیِ از قبل موجود همین‌جا پیدا و رفع شد:**
      `payload["price_action"]` فقط توی مسیرِ گذرای «هنوز تأیید نشده»ی
      STEP 58 ست می‌شد، نه در مسیرِ تأییدشده/پایدار (که اکثرِ چرخه‌ها
      همونه) — یعنی از STEP 58 تا همین الان، Thrust/Runway/pin_bar
      عملاً تقریباً هیچ‌وقت در STATEِ واقعیِ کاربر دیده نمی‌شدن، فقط در
      یک flicker گذرا. رفعش: `support_resistance` هم‌الگو، توی مسیرِ
      تأییدشده هم `price_action_patterns.get(sym)` وصل شد (+ یک کپیِ
      دیکشنری قبل از اضافه‌کردنِ `mtf_confirmation` — تا کشِ روزانه‌ی
      ماژول به‌اشتباه از تیکِ زنده mutate نشه).
      **فرانت‌اند بدونِ تغییر** — هم‌راستا با STEP 58/59/60.
      **advisory-only** — یک لایه‌ی سومِ advisory رویِ دو advisoryِ
      دیگه، هیچ‌جا گیت نمی‌کنه.
      ۷ تستِ جدید (`test_mtf_confirmation_*`) — فولِ سوییتِ
      `test_price_action_patterns.py`: ۳۸ تستِ قابلِ‌اجرا (از ۳۱)، همه
      سبز؛ همون محدودیتِ اجرای STEP 60 برقراره (`pytest`/`fastapi`/
      `aiohttp` در این sandbox بدونِ اینترنت قابلِ نصب نبودن، پس با
      harnessِ دستیِ import-mock تأیید شد، نه `pytest` رسمی). دیفِ
      `main.py` فقط همون دو نقطه‌ی بالا رو نشون می‌ده؛ بقیه‌ی فایل‌ها
      (`indicators.py`, `decision_engine.py`, `candlestick_patterns.py`,
      `harami_setup.py`) دست نخوردن.
      **بک‌لاگِ باقی‌مانده از این ۸ پارت:** پارتِ ۴ (Doji رویِ S/R) →
      پارتِ ۸ (W/H&S، بزرگ‌ترینِ باقی‌مونده) → پارتِ ۶ (Wave،
      context-only).

- [ ] **⚠️ REVISED — بک‌فیلِ تاریخیِ اینتردی عمداً پیاده نشد.**
      Senkou Span B روی ۳۰دقیقه به ~۷۸ کندل نیاز داره که برای TSETMC
      یعنی چند روزِ کاری. `history_feed.get_trade_ticks` فقط یک روزِ
      مشخص رو می‌ده (نه سریِ پیوسته)، و خودِ آن فایل صراحتاً نام‌فیلدهاش
      رو «تأییدنشده روی داده‌ی زنده» علامت زده — بک‌فیل‌کردنِ ۷+ روز از
      یک endpoint با این سطح عدم‌اطمینان ریسکِ ساختِ ابرِ غلط داره. در
      عوض، `bar_aggregator.py` فقط از تیکِ زنده انباشت می‌کنه و تا
      رسیدن به ۷۸ کندل `ready=False` نشون می‌ده — یعنی روی اینتردی، چند
      روزِ کاریِ اول بعد از فعال‌سازی، بدونِ سیگنال می‌گذره. اگه بعداً
      `get_trade_ticks` روی داده‌ی واقعی تست/تأیید شد، یک تابعِ بک‌فیلِ
      جدا (fetch جداگانه‌ی هر روز، ۷+ روز) می‌شه اضافه کرد.
- [ ] **باقی‌مانده (فقط این یکی):** اگه بعداً `get_trade_ticks` روی
      داده‌ی واقعی تست/تأیید شد، یک تابعِ بک‌فیلِ جدا (fetch جداگانه‌ی
      هر روز، ۷+ روز) می‌شه اضافه کرد تا اینتردی هم از روزِ اول بدونِ
      دورانِ warm-up کار کنه.

## PHASE H-1 — وصل‌کردنِ Ichimoku به main.py/setup_library/frontend — ✅ کامل

- [x] **`setup_library.classify_ichimoku()`** — هر کدوم از نُه
      استراتژیِ `ichimoku_strategies.classify_all` (تا STEP 49 شش‌تا،
      STEP 50 هشت‌تا، STEP 51 نُه‌تا، STEP 52 ده‌تا، STEP 54 یازده‌تا، از STEP 55 چهارده‌تا) رو، مستقل از تعدادِ تایم‌فریم
      (یک ورودیِ `{"daily":..., "30m":..., "1h":...}`)، به یک Setupِ
      نام‌دارِ جدا با برچسبِ فارسیِ خودش تبدیل می‌کنه — شاملِ R:R/هدف/حد
      ضرر برای Kumo Pullback، و strength/reversal/
      future_cloud_confirmed/gap_shrink_pct/candles_between برای بقیه،
      در متنِ note.
- [x] **`main.py`** — `build_ichimoku_payload()` (روزانه از کشِ
      `ichimoku_daily`، اینتردی زنده از `ind.ichimoku_bars`، دقیقاً
      هم‌الگو با ساختِ `sr_levels`)، وصل‌شده به `payload["ichimoku"]` و
      `payload["setups"]` در همون نقطه‌ای که `classify_stock` صدا زده
      می‌شه. حلقه‌ی پس‌زمینه‌ی `ichimoku_daily_worker_loop` (هم‌الگو با
      `support_resistance_worker_loop`) در startup ثبت شد.
- [x] **Endpointها:** `GET /api/ichimoku/{symbol}` (عیب‌یابیِ جدا از
      STATE) و `POST /api/ichimoku/refresh` (تازه‌سازیِ دستیِ روزانه) —
      هم‌الگو با `/api/support_resistance/*`.
- [x] **فرانت‌اند:** چون `setupsBadge()` از قبل عمومیه (روی هر آیتمِ
      `payload.setups` کار می‌کنه، نه فقط کلیدهای شناخته‌شده)، Setupِ
      ایچیموکو خودکار همه‌جا نمایش داده می‌شه — فقط یک آیکونِ اختصاصی
      (☁️) به `SETUP_ICON` اضافه شد، هیچ تغییرِ ساختاریِ دیگه‌ای لازم
      نبود.
- [x] پس از STEP 49/50/51 (بازبینیِ ۳۶ فایلِ آموزشیِ کاربر، اضافه‌شدنِ
      Kijun Cross + دو واگرایی + پیوت‌یابیِ فرکتال + TK Double Cross):
      ۱۰۸۸ تست سبز + یک شکستِ قدیمی در `test_execution_quality.py`.
- [x] پس از STEP 55 (CCI/ابرِ جامونده/واگراییِ مخفی/ناحیه‌ی نقدینگی/MTF):
      **۱۱۲۵ تست، همه سبز** (۱۴ تستِ جدید: ۱۱ در ichimoku_strategies + ۳ در
      setup_library)، `import main` و `node --check` تمیز.
- [x] پس از STEP 54 (Kumo Fib Pullback): ۱۱۱۱ تست، همه سبز (۸ تستِ
      جدید: ۷ در ichimoku_strategies + ۱ در setup_library)، `import main`
      و `node --check` تمیز.
- [x] پس از STEP 53 (Cloud Thickness): ۱۱۰۳ تست، همه سبز (۷ تستِ
      جدید: ۶ در ichimoku_strategies + ۱ در setup_library)، `import main`
      تمیز.
- [x] پس از STEP 52 (Kijun Flat Range + رفعِ باگِ `execution_quality`):
      ۱۰۹۶ تست، همه سبز (۶ تستِ جدیدِ ichimoku_strategies + ۱ تستِ
      setup_library + تستِ قبلاً-شکسته‌ی execution_quality)، `import main`
      و `node --check` روی JS فرانت‌اند هم تمیز.

---

# 48. تعریف Done برای نسخه حرفه‌ای (به‌روزشده)

- [x] سیستم بداند بازار در چه Regime کلیِ ساده‌ای است (enum کامل: ✅ `regime_engine.py`)
- [x] سیستم جهت، ریسک، و کیفیت قرارداد را در **یک خروجی واحد** فیوز کند — `decision_fusion.py` + `/api/decision/{symbol}`
- [x] سیستم تضاد سیگنال‌ها را تشخیص دهد
- [x] سیستم بتواند WAIT بدهد
- [x] سیستم بهترین Call/Put را رتبه‌بندی کند
- [x] سیستم ورود دیرهنگام را با ۵ سطحِ صریح رد کند — `late_entry.py`
- [x] سیستم Entry Zone/Invalidation/TP/SL/Time Stop بدهد
- [x] سیستم خروج زودهنگام را تشخیص دهد
- [x] سیستم دلیلِ تصمیم را در **یک قالبِ استاندارد واحد** نمایش دهد —
      `explanation` + `score_breakdown` در `/api/decision/{symbol}`
- [x] سیستم همه‌ی تصمیم‌ها را Journal کند و Replay/Backtest/Walk-forward داشته باشد
- [x] سیستم Risk Gate و Kill Switch داشته باشد
- [x] سیستم در داده‌ی نامطمئن معامله را Block کند
- [x] سیستم حجمِ پیشنهادیِ معامله را بر اساسِ سرمایه و ریسکِ کاربر
      محاسبه کند (بخش ۵۱)
- [x] سیستم سنِ داده را روی خودِ تصمیم نشان دهد و در تأخیرِ زیاد WAIT
      بدهد (بخش ۵۳)

---

# 49. قانون طلایی تصمیم‌یار (بدون تغییر)

```text
DATA VALID → REGIME → DIRECTION → MICROSTRUCTURE (صفِ برتر) → MOMENTUM →
VOLUME → OPTION QUALITY → CONFLICT CHECK → LATE ENTRY CHECK → RISK CHECK →
DECISION
```

این زنجیره امروز *ضمنی* در `main.py` رعایت می‌شود؛ Decision Fusion Engine آن را
*صریح* می‌کند.

---

# 50. خروجی نهایی مورد انتظار (بدون تغییر — این spec دقیقِ Decision Fusion Engine است)

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       DECISION ASSISTANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MARKET:        BULLISH        REGIME: TRENDING
DIRECTION:     CALL           SCALP SCORE: 91/100   CONFIDENCE: HIGH
BEST CONTRACT: ...
STATUS: 🟢 ARMED
ENTRY ZONE: ...   INVALIDATION: ...   TP1: ...   TP2: ...   TIME STOP: ...
WHY: ✓ ... ✓ ... ✓ ...
BLOCKERS: None
ALTERNATIVE: ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

# اولویت اجرا (نسخه‌ی نهایی، خلاصه)

```text
Existing App (تقریباً همه‌چیز تا فاز ۸ رودمپِ اصلی)
     ↓
Market Regime Engine
     ↓
Decision Fusion Engine ⭐
     ↓
پنل یکپارچه‌ی Current Decision
     ↓
پرداخت‌های کوچکِ Phase B/C
     ↓
ML (فقط با داده‌ی کافی)
```

# معیار موفقیت (بدون تغییر)

```text
Fewer bad entries · Lower late-entry rate · Lower drawdown ·
Higher expectancy · Better exit timing · Higher setup selectivity
```
هدف: وقتی شرایط خوب نیست، سیستم با اطمینان بگوید **WAIT**.

---

## STEP 62 — Best Contract Finder (ترکیبِ تصمیم‌یار + شمع‌خوان)

- `backend/contract_finder.py` (جدید، توابعِ خالص + `BiasTracker` + `FinderStore`):
  - جهتِ ترکیبیِ سهمِ پایه: حکمِ زنده (۲۵) + تایم‌فریم‌های ۱/۵/۱۵/۳۰ دقیقه (۸/۱۴/۱۴/۱۴، از تیکِ زنده با EMA5/13؛ زیرِ ۱۴ کندل «partial») + دیدِ روزانه‌ی شمع‌خوان‌گونه (MA20/MA50، MACD، RSI، ADX/DMI؛ وزن ۲۵). خروجی BULL/BEAR/NEUTRAL.
  - بهترین خرید: کال اگر BULL، پوت اگر BEAR؛ امتیاز از کیفیت، نقدشوندگی، دلتا، اسپرد، سررسید، حکمِ خودِ قرارداد، ریسک و جریمه‌ی حباب.
  - بهترین فروشِ اول (آفست): حباب = قیمت نسبت به ارزشِ منصفانه‌ی Black-Scholes با نوسانِ تاریخیِ ۲۰ روزه؛ یا هم‌جهت (فروشِ کال در BEAR، فروشِ پوت در BULL، خنثی نیمه‌امتیاز). خلافِ جهتِ قوی فقط با حبابِ ≥۳۰٪ و با هشدار. فقط قراردادهای نقدشونده (برای آفست).
  - هدف/حدضرر/سطحِ ابطالِ سهمِ پایه (ATR روزانه) — هیورستیک.
- `main.py`: `FINDER_TRACKERS` (hook در worker_loop)، `contract_finder_daily_loop` (روزانه، ۲۰ ساعت یک‌بار)، `contract_finder_loop` (هر ۵ ثانیه از STATE/OPTION_STATE، بدونِ درخواستِ شبکه‌ی اضافه)، `GET /api/contract-finder`.
- فرانت‌اند: تبِ «🎯 بهترین قرارداد» (polling هر ۵ ثانیه فقط وقتی تب بازه، فیدِ تغییرات).
- تست: ۲۹ تستِ جدید (`tests/test_contract_finder.py`)؛ کلِ سوئیت ۱۲۴۳ سبز. فرانت‌اند در jsdom اجرا شد (بدونِ خطای همگام، رندرِ تب تأیید شد).
- ⚠️ هنوز روی داده‌ی زنده‌ی TSETMC اجرا نشده (sandbox دسترسی ندارد). تایم‌فریم‌های ۱۵/۳۰ دقیقه بعد از شروعِ سرور از صفر ساخته می‌شن و حافظه‌ای‌اند (با ری‌استارت پاک می‌شن).
- backlog: هشدارِ صوتی/تلگرامِ تغییرِ بهترین قرارداد، افزودنِ دکمه‌ی «ثبت ورود» از همین تب (اتصال به تب «معاملات باز» برای فروشِ اول)، پشتیبانیِ short در `positions_worker_loop` (حدضررِ معکوس)، کالیبراسیونِ آستانه‌ی حباب روی داده‌ی واقعی.

### STEP 62.1 — اصلاحِ محاسبه‌ی «حباب» (باگِ گزارش‌شده توسط کاربر)
- مشکل: حباب با Black-Scholes و نوسانِ تاریخی (HV) حساب می‌شد. قیمتِ آپشن در بازارِ ایران چند برابرِ مدلِ HV معامله می‌شود (مثلاً IV≈۹۳٪ در برابرِ HV≈۳۴٪)، و برای پوت/کالِ خیلی خارج از اختیار ارزشِ مدل تقریباً صفر است؛ نتیجه «حباب ۷۲۹٪/۸۲۰٪» برای قراردادهای دلتا≈۰ بود (نادرست).
- راه‌حل: حباب = ٪ بالاتر بودنِ IV قرارداد از IV مرجعِ همان سررسید (میانه‌ی IV قراردادهای نقدشونده با |دلتا| بین ۰.۳۵ تا ۰.۶۵، حداقل ۲ نمونه). HV دیگر در حباب نقشی ندارد. بدون مرجعِ معتبر، حباب None است (عددِ ساختگی نمی‌دهد).
- فروشِ اول فقط برای |دلتا| بین ۰.۲۰ تا ۰.۷۰ (قراردادِ خیلی خارج از اختیار: قیمت/IV نویز و ریسکِ دُم). آستانه‌ها: حباب ≥۲۰٪، شدید ≥۴۰٪.
- ۶ تستِ جدید/بازنویسی‌شده (از جمله رگرسیونِ دقیقِ باگ)؛ کلِ سوئیت ۱۲۴۹ سبز.
- هنوز کالیبره نشده: آستانه‌ها هیورستیک‌اند. بهبودِ بعدی: ترکیب با iv_rank/iv_percentile (STEP 42) به‌عنوانِ تأییدِ دوم.

### STEP 62.2 — بازتعریفِ «حباب» به‌صورتِ فاصله‌ی سربه‌سر + فروشِ تاکتیکی + آخرین قیمت (درخواستِ کاربر)
- **حباب (جایگزینِ تعریفِ IV نسبی در 62.1):** حباب = ٪ رشد (کال) یا افت (پوت) که سهمِ پایه باید بکند تا قرارداد سربه‌سر شود؛ از `breakeven.compute`. کال: (اعمال+قیمت−S)/S، پوت: (S−(اعمال−قیمت))/S. آستانه‌ها: ≥۵٪ حباب‌دار، ≥۱۰٪ قوی، ≤۲٪ کم. IV نسبی فقط به‌عنوانِ `iv_premium_pct` (اطلاعی) مانده؛ `fair_value` هنوز با IV مرجع است.
- **عدمِ تکرارِ قرارداد در خرید و فروش:** قراردادِ هم‌سو با جهتِ اصلی (کال در BULL، پوت در BEAR) هرگز در فروش نمی‌آید؛ نگهبانِ نهایی در `build_symbol`.
- **فروشِ تاکتیکی:** `short_term_bias` (فقط ۱/۵/۱۵/۳۰ دقیقه؛ امتیاز ≥۳۵، حداقل ۲ تایم‌فریم، یکی ≥۵ دقیقه). BULL+کوتاه‌مدت نزولی ⇒ فروشِ کال با برچسبِ 🎯 و هشدار؛ BEAR+کوتاه‌مدت صعودی ⇒ فروشِ پوت. روندِ «قوی» ⇒ نیازِ امتیازِ ≥۵۰. قراردادِ تاکتیکی از لیستِ خرید حذف می‌شود.
- **آخرین قیمت:** هر کارت `last_price`، `last_change_pct` (نسبت به قیمتِ دیروزِ قرارداد)، `close_price`، `volume`، `open_interest` و `price_source` دارد.
- ⚠️ آستانه‌ها هیورستیک و کالیبره‌نشده‌اند.

---

# STEP 63 — چک‌لیستِ حرفه‌ای‌سازی (اجرا و تیک‌خوردن مرحله‌به‌مرحله)

راهنما: `[x]` انجام و تست شده · `[ ]` باقی‌مانده · `[~]` کد آماده ولی نیازمند داده‌ی زنده/اقدامِ دستی.
⚠️ همه‌ی آستانه‌ها هیورستیک‌اند؛ هیچ‌کدام روی داده‌ی زنده‌ی TSETMC اجرا نشده (sandbox شبکه ندارد).

## A — اعتبارسنجیِ Finder (ژورنالِ پیشنهادها)  ← اولویت ۱
- [x] A1. `finder_journal.py`: ثبتِ بهترین خرید/فروشِ هر نماد در SQLite (بدون تکرار تا بسته شدنِ پیشنهادِ قبلی)
- [x] A2. ارزیابیِ نتیجه: هدف / حدضرر / انقضا + بیشترین سود و زیانِ لحظه‌ای (MFE/MAE)
- [x] A3. آمار و گزارشِ کالیبراسیون: نرخِ موفقیت به تفکیکِ خرید/فروش/تاکتیکی/باکتِ حباب/جهت
- [x] A4. اتصال به `contract_finder_loop` در `main.py`
- [x] A5. endpoint ‏`GET /api/contract-finder/journal`
- [x] A6. پنلِ آمار در تبِ «بهترین قرارداد»
- [x] A7. تست‌های واحد
- [~] A8. تنظیمِ آستانه‌ها (حباب، کوتاه‌مدت، وزن‌ها) بر پایه‌ی گزارش — ابزارِ پیشنهاد (`finder_journal.suggest_calibration` + نمایش در پنلِ ژورنال) آماده؛ فقط با ≥۱۴ روز داده و ≥۳۰ نمونه‌ی بسته‌شده در هر گروه پیشنهاد می‌دهد و هرگز خودکار اعمال نمی‌کند. خودِ تنظیم بعد از ≥۲ هفته داده‌ی زنده

## B — ریسکِ فروشِ اول
- [x] B1. `short_risk.py`: زیانِ هر قرارداد در سناریوهای حرکتِ سهمِ پایه (BS با IV فعلی + ارزشِ ذاتی)
- [x] B2. اتصال به آیتم‌های فروش (`risk_scenarios`)
- [x] B3. نمایش در UI («اگر سهم +۱۰٪ شود، زیان ≈ …»)
- [x] B4. تست‌ها
- [x] B5. وجه تضمینِ فروش — فرمولِ منتشرشده‌ی بورس (`margin_calc.py`): IM = max(A·S − «در‌زیان‌بودن», B·K) با A=۲۰٪، B=۱۰٪؛ وجه تضمینِ لازم = IM + قیمتِ پایانی؛ حداقل = ۷۰٪ لازم. نرخِ دستیِ کاربر همچنان اولویت دارد؛ بدونِ strike/نوع/قیمتِ سهم → «نامشخص». ⚠️ ضرایب را بورس اعلام می‌کند و ممکن است عوض شده باشد؛ با عددِ تابلوی نماد تطبیق دهید.
- [x] B6. سقفِ زیان و حداکثر تعدادِ قرارداد (اتصال به `position_sizing`) — `risk_budget.py`

## C — هشدارِ تغییرِ بهترین قرارداد
- [x] C1. `EventAlertThrottle` + فرمتِ پیام (فقط وقتی بازار باز؛ cooldown)
- [x] C2. اتصال به تلگرام در `contract_finder_loop`
- [x] C3. تست‌ها
- [x] C4. کلیدِ روشن/خاموش از UI

## D — اطلاعاتِ تصمیم
- [x] D1. نمودارِ payoff (سود/زیان در سررسید) برای هر پیشنهاد — `payoff.py` + `/api/contract-finder/payoff`
- [x] D2. صف و حدِ نوسانِ سهمِ پایه کنارِ پیشنهاد (ریسکِ قفل‌شدن/آفست‌نشدن)

## E — ماندگاری
- [x] E1. بازسازیِ کندل‌های ۱/۵/۱۵/۳۰ دقیقه از ریز معاملاتِ امروزِ TSETMC (به‌جای ذخیره/بارگذاری؛ با ری‌استارت از صفر نشوند)

## F — یکپارچگی با معاملات
- [x] F1. دکمه‌ی «ثبت ورود» از کارتِ finder
- [x] F2. پشتیبانیِ short در `positions_worker_loop` (حدضررِ معکوس)

## G — بدهیِ فنی
- [x] G1. `.gitignore` (+ حذفِ `__pycache__`، `*.db`، `last_state.json`، `logs/` از بسته)
- [x] G2. `run_tests.py` (اجرای کلِ سوئیت بدونِ pytest)
- [x] G3. CI (اجرای خودکارِ تست‌ها) — `.github/workflows/tests.yml` + `scripts/check_frontend.mjs` (روی GitHub هنوز اجرا نشده)
- [x] G4. شکستنِ `main.py` و `index.html` به ماژول‌های کوچک‌تر — انجام شد (دورهای ۵–۱۲): `main.py` ۴۴۷۴ → ≈۲۵۰۰ خط (فقط وضعیتِ سراسری، `worker_loop`، `option_worker_loop` و سیم‌کشی)؛ `index.html` ≈۲۷۲KB → ≈۳۱KB.

### وضعیتِ اجرا (به‌روزرسانی)
- انجام شد: A1–A7، B1–B4، C1–C4، G1–G2 (ماژول‌های `finder_journal.py`، `short_risk.py`، `EventAlertThrottle`، `run_tests.py`، `.gitignore`؛ سه endpoint: `/api/contract-finder/journal`، `GET/POST /api/contract-finder/alerts`؛ پنلِ ژورنال، سطرِ ریسکِ فروش و کلیدِ هشدار در تب).
- تست: ماژول‌های finder/journal/short_risk/breakeven ۸۱ تستِ سبز. سوئیتِ کامل در sandbox به‌خاطرِ نبودِ pytest/aiohttp اجرا نشد؛ روی سیستمِ خودتان `pytest -q` بزنید.
- `main.py` فقط py_compile شد (fastapi در sandbox نیست)؛ اجرای زنده لازم است.
- بعدی: A8 (بعد از ≥۲ هفته داده)، B5/B6، D1–D2، E1، F1–F2، G3–G4.

- انجام شد (دور دوم): F1 (دکمه‌ی «➕ ثبت ورود» روی کارتِ finder؛ حدضرر/هدف/ابطال از همان کارت) و F2 (`position_rules.py`: برای short option قوانینِ Early Exit/Time Stop/dynamic_risk اعمال نمی‌شود چون برای فروشنده معنیِ معکوس دارند؛ قانونِ تازه‌ی «ابطالِ سهمِ پایه»؛ `pnl_rial` ریالی). منطقِ `_check_position_exit` با استخراجِ تابع از `main.py` روی ۵ سناریو (ابطال، short بدونِ time-stop، حدضرر/حدسودِ short، long همچنان time-stop) دستی راستی‌آزمایی شد؛ `main.py` کامل اجرا نشد.
- باقی‌مانده: A8، B5، B6، D1–D2، E1، G3–G4.

- انجام شد (دور سوم): E1 — به‌جای ذخیره در دیتابیس، کندل‌ها از *ریز معاملاتِ همان روزِ TSETMC* بازسازی می‌شوند (`contract_finder.rebuild_tracker`؛ `main.finder_resync_all` در startup و `POST /api/contract-finder/resync` + دکمه‌ی «🔄 همگام‌سازیِ کندل‌ها»). فقط وقتی بازار «باز» است. `history_feed.get_trade_ticks` برای روزِ جاری اگر `GetTradeIntraDay` خطا/خالی داد، `Trade/GetTrade/{insCode}` را هم امتحان می‌کند (نامِ اولی روی شبکه‌ی واقعی هرگز تأیید نشده بود).
- ⚠️ تأیید نشده روی شبکه‌ی واقعی: نامِ دقیقِ فیلدهای پاسخ (`hEven/pTran/qTitTran/canceled`). اگر در لاگ «هیچ تیکِ معتبری پارس نشد» دیدید، یک پاسخِ خام را با `/api/history/...` ببینید و `history_feed.TRADE_FIELD_CANDIDATES` را اصلاح کنید.
- محدودیت: فقط جلسه‌ی امروز (۱/۵/۱۵/۳۰ دقیقه). ایچیموکوی ۳۰د/۱ساعته (حداقل ۷۸ کندل = چند روز) نیازمندِ `GetTradeHistory` برای چند روزِ قبل است — هنوز انجام نشده.
- باقی‌مانده: A8، B5، B6، D1–D2، G3–G4.

- انجام شد (دور چهارم): D2 — `market_risk.py`: صفِ خرید/فروشِ سهمِ پایه (`queue_status`) و وضعیتِ زنجیره (`chain_state`) کنارِ هر پیشنهاد. فروشِ کال در صفِ خرید و فروشِ پوت در صفِ فروش *حذف* می‌شود (قرارداد قفل می‌شود و آفست ممکن نیست)؛ بقیه‌ی حالت‌ها هشدار + جریمه‌ی کوچکِ امتیاز؛ برچسبِ صف/فشارِ شکستن کنارِ نماد. هیچ درخواستِ شبکه‌ی تازه‌ای لازم نیست.
- ⚠️ حدِ مجازِ نوسانِ رسمیِ TSETMC در دسترس نیست؛ «صف» از قاعده‌ی مشاهده‌ایِ `queue_status` (سقف/کفِ همان روز) می‌آید و آستانه‌ها هیورستیک‌اند.
- باقی‌مانده: A8، B5، B6، D1، G3، G4.

- انجام شد (دور پنجم): D1، B6، G3، تکه‌ی اولِ G4، و ابزارِ پیشنهادِ A8. تست‌های جدید: `test_payoff.py`، `test_risk_budget.py`، `test_finder_payoff.py` و ۸ تست در `test_finder_journal.py`. فرانت‌اند در jsdom اجرا شد (بودجه‌ی ریسک، نمودار و حفظِ حالتِ بازِ آن بعد از polling، پنلِ سقف‌ها، چهار حالتِ پیشنهادِ کالیبراسیون).
- ⚠️ سوئیتِ کامل و `main.py` در sandbox اجرا نشد (زیپِ ورودی ناقص بود)؛ `main.py` فقط py_compile شد. روی سیستمِ خودتان `pytest -q` بزنید.
- باقی‌مانده: A8 (داده‌ی زنده)، B5 (فرمولِ رسمی)، G4 (بقیه‌ی تکه‌ها).

- انجام شد (دور ششم): تکه‌ی دومِ G4 — بلوکِ finder (وضعیتِ FINDER_*، `contract_finder_daily_loop`، `contract_finder_loop`، `finder_resync_*`، `_finder_with_budget` و ۹ endpoint شاملِ `/api/settings/risk_limits`) از `main.py` به `backend/finder_service.py` (APIRouter + `configure()` برای پرهیز از import حلقوی) منتقل شد؛ رفتار بدونِ تغییر. `main.py` از ۴۴۷۴ به ۴۲۸۴ خط. راستی‌آزمایی: OpenAPI قبل/بعد دقیقاً یکسان (۹۳ عملیات)، ۴ endpoint با TestClient پاسخ ۲۰۰ داد، ۴ تستِ جدید (`tests/test_finder_service.py`)؛ `pytest -q` → ۱۳۴۰ سبز.
- ⚠️ `python run_tests.py` (بدونِ pytest) روی ۱۳ تست شکست می‌خورد (مثلاً `test_oi_engine`: وابسته به stateِ مشترک/fixture)؛ با `pytest -q` همه سبزند — CI باید pytest بزند.
- باقی‌مانده: A8 (داده‌ی زنده)، B5 (فرمولِ رسمی وجه تضمین)، G4 (تکه‌های بعدی: `main.py` ≈ ۴۲۸۴ خط؛ `index.html` ≈ ۲۷۲KB).

- انجام شد (دور هفتم): تکه‌ی سومِ G4 — `frontend/index.html` از ≈۲۷۲KB به ≈۳۱KB رسید. CSS به `styles.css` و اسکریپتِ inline (≈۳۳۰۰ خط) به ۶ فایلِ کلاسیک به‌ترتیبِ اجرای قبلی شکسته شد: `core.js` (stateِ مشترک، مرتب‌سازی، سلامتِ فید، kill switch، تب‌ها)، `badges.js`، `options.js` (زنجیره‌ی آپشن)، `fusion_lists.js` (Decision Fusion، دیده‌بان، بهترین قراردادها، تاریخچه)، `positions_replay.js` (هشدار/نوتیف، `connect`، پوزیشن‌ها، Replay)، `perf_compare.js` (عملکرد، ML، مقایسه، روند، اسکنر). ترتیبِ `<script>`ها: `finder.js` سپس این ۶ فایل.
- راستی‌آزمایی: `check_frontend.mjs` (jsdom) سبز؛ مقایسه‌ی نسخه‌ی قبل/بعد در jsdom: ۲۲۴ تابعِ سراسری دقیقاً یکسان، بدونِ خطا؛ همه‌ی فایل‌ها از `StaticFiles` با ۲۰۰ سرو می‌شوند. ⚠️ فقط jsdom؛ مرورگرِ واقعی باید یک‌بار نگاه شود. اگر `check_frontend.mjs` را روی فایلِ دیگری اجرا می‌کنید، srcهای محلی خودکار inline می‌شوند.
- باقی‌مانده: A8 (داده‌ی زنده)، B5 (فرمولِ رسمیِ وجه تضمین)، G4 (فقط `main.py` ≈ ۴۲۸۴ خط؛ تکه‌های بعدی: positions/watchlist/backtest).

- انجام شد (دور هشتم): تکه‌ی چهارمِ G4 — بلوکِ پوزیشن‌ها (`POSITIONS`، `_check_position_exit`، `_positions_check_cycle`، `positions_worker_loop`، endpointهای `/api/positions*` و `/api/portfolio-risk`) از `main.py` به `backend/positions_service.py` منتقل شد (APIRouter + `configure()`؛ ثابت‌ها/STATE از main تزریق می‌شوند). `main.py` ≈ ۳۹۴۷ خط. `test_position_monitor.py` به `positions_service` منتقل شد (+۳ تستِ جدید). راستی‌آزمایی: OpenAPI قبل/بعد یکسان (۹۳ عملیات)، `pytest -q` سبز (۱۳۴۳).
- باقی‌مانده: A8، B5، G4 (تکه‌های بعدی: watchlist، backtest/walk-forward، تنظیماتِ position_sizing).

- انجام شد (دور نهم): تکه‌ی پنجمِ G4 — Watchlist (`WATCHLIST`، `WATCHLIST_MAX_CONTRACTS`، مدل‌های `WatchlistItem/RemoveItem`، `build_items` و ۳ endpoint) از `main.py` به `backend/watchlist_service.py` رفت. `WATCHLIST` فقط درجا تغییر می‌کند و main همان شیء را import می‌کند؛ بنابراین بارگذاری/ذخیره‌ی persist، `option_worker_loop` و push وب‌سوکت بدونِ تغییر کار می‌کنند. `main.py` ≈ ۳۸۷۱ خط. راستی‌آزمایی: OpenAPI یکسان (۹۳ عملیات)، چرخه‌ی add/remove با TestClient، ۴ تستِ جدید؛ `pytest -q` سبز (۱۳۴۷).
- باقی‌مانده: A8، B5، G4 (backtest/walk-forward، تنظیماتِ position_sizing).

- انجام شد (دور دهم): تکه‌ی ششمِ G4 — Backtest (ثابت‌های `BACKTEST_*`، `BACKTEST_STATE`، `_backtest_done_for_deven`، `_calibration_recorded`، `_maybe_record_calibration`، `backtest_worker_loop` و ۵ endpoint شاملِ latest/multi_day/walk_forward/export) از `main.py` به `backend/backtest_service.py` رفت. سه ساختارِ حالت فقط درجا تغییر می‌کنند و main همان اشیاء را برای persist import می‌کند؛ مقدارِ پیش‌فرضِ `candle_seconds=60/lookahead=5` در امضای endpointها حفظ شد؛ `_download_response` و ثابت‌های بازار با `configure()` تزریق می‌شوند. `main.py` ≈ ۳۵۶۱ خط (از ۴۴۷۴). راستی‌آزمایی: OpenAPI یکسان (۹۳ عملیات)، ۵ تستِ جدید، `pytest -q` سبز (۱۳۵۲).
- باقی‌مانده: A8، B5، G4 (فقط تنظیماتِ position_sizing و ماژول‌های کوچکِ دیگرِ `main.py`؛ اختیاری).

- انجام شد (دور دوازدهم): تکه‌ی نهاییِ G4 — endpointهای سبکِ `main.py` به سه ماژولِ route رفتند: `system_routes.py` (kill switch، position_sizing، سلامتِ فید، run_mode، snapshotها، تحلیل‌های سبک)، `analysis_routes.py` (best-contracts، scanner، decision، الگوها، breakeven/stress، IV، calibration، time_of_day) و `journal_routes.py` (ژورنال، ML، audit، formula registry، local_db، export)؛ هلپرِ مشترکِ دانلود به `http_utils.py`. هر ماژول `configure(**deps)` سخت‌گیر دارد (کم/اضافه → TypeError) و وابستگی‌ها را main آخرِ فایل به‌صورتِ ارجاع تزریق می‌کند. `/api/settings/fast_mode` عمداً در main ماند (متغیرِ سراسریِ rebind‌شونده). `_compute_best_contracts` را worker از `analysis_routes` import می‌کند.
- راستی‌آزمایی: schemaِ کاملِ OpenAPI (۹۳ عملیات) با نسخه‌ی پیش از G4 یکسان است (تنها تفاوت: متنِ docstringِ `/api/watchlist` به‌خاطرِ تغییرِ نامِ تابع)؛ ۲۹ endpoint با TestClient بدونِ ۵xx؛ ۱۰ تستِ جدید (`test_route_modules.py`)؛ `pytest -q` سبز (۱۳۶۲).
- ⚠️ `worker_loop` (≈۵۵۰ خط) و `option_worker_loop` (≈۱۱۰۰ خط) عمداً در main ماندند: به تقریباً همه‌ی stateهای سراسری وصل‌اند و بدونِ داده‌ی زنده/تستِ یکپارچه ریسکِ شکستنِ رفتارِ real-time دارند. اگر خواستید، بعد از A8 (داده‌ی زنده) با تستِ مقایسه‌ایِ خروجیِ tick‌به‌tick جدا شوند.
- باقی‌مانده: A8 (داده‌ی زنده)، B5 (فرمولِ رسمیِ وجه تضمین).

- انجام شد (دور سیزدهم): B5 — `margin_calc.py` (فرمولِ وجه تضمینِ اولیه/لازم/حداقل) و اتصال به `risk_budget.margin_estimate` (اولویت: نرخِ کاربر ← فرمول ← نامشخص). خروجیِ کارتِ finder: `margin_source` (`formula`/`user_rate`) و `margin_required_per_contract`. دو لینکِ داده‌شده (مفید و آپشن‌باز) برای ربات بسته بودند (robots)؛ فرمول از متنِ جستجو و چند منبعِ هم‌خوان گرفته شد، نه از خودِ آن صفحه‌ها. ۸ تستِ جدید (`test_margin_calc.py`) با مثالِ عددیِ منتشرشده.
- ⚠️ نقشِ دقیقِ ثابتِ C=۱۰٬۰۰۰ در منابع روشن نبود (اعمال نشد). برای راستی‌آزمایی، وجه تضمینِ اولیه‌ی یک نمادِ واقعی را از تابلوی بورس بدهید تا با فرمول تطبیق دهیم.
- باقی‌مانده: A8 (داده‌ی زنده) و جداسازیِ اختیاریِ `worker_loop`/`option_worker_loop` بعد از A8.


## STEP 64 — ارتقای کیفیتِ نتیجه (بر پایه‌ی ارزیابیِ پس از G4/B5)

راهنما: `[x]` انجام و تست شده · `[ ]` باقی‌مانده · `[~]` کد آماده ولی نیازمند داده‌ی زنده/تطبیقِ دستی.
⚠️ منطقِ این بسته: گلوگاهِ نتیجه «سیگنالِ بیشتر» نیست، **اثباتِ لبه‌ی خالص + ریسکِ قابل‌کنترل** است. پس سیگنالِ جدید فقط به‌صورتِ *زمینه/هشدار* اضافه می‌شود و تا گذشتن از دروازه‌ی اعتبارسنجی (۶۴.۲ + A8) وزنِ تصمیم نمی‌گیرد. همه‌ی آستانه‌ها هیورستیک‌اند و روی داده‌ی زنده اجرا نشده‌اند.

**ترتیبِ اجرا (به همین ترتیب جلو می‌رویم؛ هر مرحله بعد از تیک خوردن بسته می‌شود):** ۶۴.۱ → ۶۴.۲ → ۶۴.۳ → ۶۴.۴ → ۶۴.۵ → ۶۴.۶ → ۶۴.۷

**تعریفِ «انجام شد» برای هر مرحله:** (۱) `pytest -q` سبز؛ (۲) schemaِ OpenAPI فقط با تفاوت‌های عمدیِ همان مرحله عوض شده؛ (۳) برای هر عددِ تخمینی برچسبِ «تخمینی» و منبعِ آن نمایش داده شود؛ (۴) همین چک‌لیست تیک بخورد و خطِ «انجام شد (دورِ N)» اضافه شود؛ (۵) زیپِ جدید تحویل شود.

### ۶۴.۱ — پایشِ وجه تضمین و هشدارِ زودهنگامِ مارجین‌کال  (نیازی به داده‌ی زنده ندارد؛ از B5 استفاده می‌کند)
- [ ] 64.1a. `margin_monitor.py` (توابعِ خالص): وجه تضمینِ لازمِ هر پوزیشنِ فروش با `margin_calc`؛ درصدِ مصرفِ سرمایه؛ آستانه‌ی ۷۰٪؛ وضعیتِ `ok | warn | danger | unknown`
- [ ] 64.1b. قیمتِ سهمِ پایه‌ای که در آن آستانه‌ی مارجین‌کال فعال می‌شود (حلِ عددی bisection با قیمتِ BS و IV فعلی) + فاصله‌ی درصدیِ آن تا قیمتِ فعلی؛ بدونِ IV/strike → `unknown` (نه حدس)
- [ ] 64.1c. endpoint ‏`GET /api/margin-monitor` (روی پوزیشن‌های بازِ فروش در `positions_service`)
- [ ] 64.1d. هشدارِ تلگرام با cooldown (الگوی `EventAlertThrottle`؛ فقط وقتی بازار باز) + کلیدِ روشن/خاموش
- [ ] 64.1e. پنلِ «ریسکِ وجه تضمین» در تبِ پوزیشن‌ها (نوارِ مصرف، فاصله تا مارجین‌کال، برچسبِ تخمینی)
- [ ] 64.1f. تست‌ها: یکنواختیِ وجه تضمین نسبت به قیمت، همگراییِ bisection، ورودیِ ناقص → unknown، cooldown
- [~] 64.1g. تطبیق با عددِ واقعیِ تابلوی بورس (قیمت سهم/اعمال/نوع/وجه تضمینِ اولیه از کاربر) و اصلاحِ ضرایبِ A/B در صورتِ مغایرت

### ۶۴.۲ — جدولِ عملکردِ خالص + قطعِ خودکارِ ستاپ‌های ضعیف  (بیشترین اثر؛ ادامه‌ی A8)
- [ ] 64.2a. `finder_scoreboard.py`: امیدِ ریاضیِ **خالص** به تفکیکِ ستاپ × رژیمِ بازار × ردهِ‌ی نقدشوندگی از ژورنالِ finder
- [ ] 64.2b. مدلِ هزینه با تنظیماتِ کاربر (کارمزدِ خرید/فروش، مالیاتِ فروش، slippage به‌تیک)؛ نرخ‌های نامعلوم هاردکد نمی‌شوند — بدونِ نرخ فقط «ناخالص» نمایش و برچسب‌گذاری می‌شود
- [ ] 64.2c. بازه‌ی اطمینانِ نرخِ موفقیت (Wilson) + حداقل نمونه (N)؛ وضعیتِ ستاپ: `active | observe_only | insufficient_data`
- [ ] 64.2d. اتصال به finder: ستاپِ `observe_only` در کارت با برچسبِ «فقط مشاهده» و بدونِ پیشنهادِ تعداد (قابلِ خاموش‌کردن)
- [ ] 64.2e. endpoint + جدولِ UI در پنلِ ژورنال
- [ ] 64.2f. تست‌ها: محاسبه‌ی هزینه، Wilson، دروازه‌ی N، ستاپِ بدونِ نمونه
- [~] 64.2g. معنادار شدنِ اعداد = ≥۱۴ روز داده‌ی زنده (همان A8)

### ۶۴.۳ — مدلِ احتمالِ پر شدنِ سفارش
- [ ] 64.3a. ثبتِ قیمتِ ورودِ واقعی در برابرِ قیمتِ پیشنهادی (از «ثبت ورود» F1) در ژورنال
- [ ] 64.3b. `fill_model.py`: برآوردِ احتمالِ fill از صف و حجمِ سمتِ مقابل (هیورستیک، برچسبِ تخمینی)
- [ ] 64.3c. نمایشِ «احتمالِ پر شدن» کنارِ قیمتِ ورود در کارت
- [ ] 64.3d. تست‌ها (صفِ خالی/پر، ورودیِ ناقص)
- [~] 64.3e. کالیبراسیونِ مدل با fillهای واقعیِ ژورنال (نیازمندِ داده)

### ۶۴.۴ — ریسکِ کلِ پرتفوی
- [ ] 64.4a. `portfolio_greeks.py`: جمعِ دلتا/گاما/تتا/وگا (معادلِ سهم) به تفکیکِ نماد و کل
- [ ] 64.4b. همبستگیِ نمادها از تاریخچه‌ی روزانه؛ گروه‌بندیِ پوزیشن‌های هم‌جهت (ریسکِ «یک شرطِ بزرگ روی بازار»)
- [ ] 64.4c. تستِ استرسِ پرتفوی (حرکتِ هم‌زمانِ بازار ±۵/±۱۰٪) با موتورِ `short_risk`
- [ ] 64.4d. هشدارِ سقفِ دلتای خالص نسبت به سرمایه (سقفِ قابل‌تنظیم)
- [ ] 64.4e. endpoint ‏`GET /api/portfolio-greeks` + پنلِ UI
- [ ] 64.4f. تست‌ها

### ۶۴.۵ — فیلترهای مخصوصِ بازارِ ایران
- [ ] 64.5a. پرچمِ «سهمِ پایه قفل در حدِ مجازِ نوسان» (هج/آفست ناممکن) → هشدار/کاهشِ اولویتِ پیشنهاد (توسعه‌ی D2)
- [ ] 64.5b. پرچمِ روزِ صف‌دارِ شدید به‌عنوانِ «احتیاط»
- [ ] 64.5c. `corporate_events.py`: تقویمِ رویدادهای شرکتی (مجمع/سودِ نقدی/افزایشِ سرمایه) با ورودیِ دستی + هشدار اگر قبل از سررسید باشد؛ ماندگار در persist
- [ ] 64.5d. تست‌ها
- [~] 64.5e. راستی‌آزمایی قاعده‌ی تعدیلِ قیمتِ اعمال برای رویدادهای شرکتی با سندِ رسمیِ بورس (من از sandbox نمی‌توانم تأیید کنم)

### ۶۴.۶ — سیگنالِ IV در برابرِ نوسانِ واقعی
- [ ] 64.6a. `vol_edge.py`: نوسانِ تاریخی (close-to-close + Parkinson) از تاریخچه‌ی روزانه
- [ ] 64.6b. رتبه‌ی صدکیِ IV از `iv_history` + اختلافِ IV−RV (ریسکِ‌پرمیوم) + ساختارِ زمانیِ سررسیدها
- [ ] 64.6c. نمایش به‌صورتِ *زمینه* در کارت (بدونِ وزنِ تصمیم تا عبور از دروازه‌ی ۶۴.۲)
- [ ] 64.6d. endpoint + تست‌ها

### ۶۴.۷ — استراتژی‌های با ریسکِ تعریف‌شده
- [ ] 64.7a. `strategy_builder.py`: کاوردکال، بول‌کال‌اسپرد، بیرپوت‌اسپرد، کالر — بیشینه سود/زیان و سربه‌سر با `payoff.py`
- [ ] 64.7b. پیشنهادِ جایگزین برای «فروشِ لخت» در کارت‌های فروش (کاهشِ ریسکِ نامحدود)
- [ ] 64.7c. UI سازنده‌ی استراتژی + نمودارِ payoff
- [ ] 64.7d. تست‌ها
- [~] 64.7e. وجه تضمینِ اسپردها: فرمولِ B5 فقط برای فروشِ تکی است؛ برای اسپرد «نامشخص — از کارگزار/بورس بگیرید» اعلام می‌شود تا تأییدِ رسمی

### وضعیتِ اجرای STEP 64
- شروع نشده: ۶۴.۱ تا ۶۴.۷. بعدی: **۶۴.۱ — پایشِ وجه تضمین**.
- مستقل از این بسته: A8 (داده‌ی زنده) و جداسازیِ اختیاریِ `worker_loop`/`option_worker_loop` پس از A8.

