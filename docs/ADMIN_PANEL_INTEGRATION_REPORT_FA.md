# گزارش یکپارچه‌سازی صفحهٔ اصلی، Login و Admin Panel

**تاریخ:** ۱۴۰۵/۰۹/۰۵ — ۲۶ نوامبر ۲۰۲۶
**Workspace:** `.worktree-main-integration`
**Branch:** `main`
**Base SHA:** `1a3c05e99a462753d5083ebfcbb3145b9940fa41`

## خلاصهٔ تغییرات

این مرحله به‌صورت افزایشی روی worktree مستقل انجام شد. فایل‌های اصلی پروژه و سایر worktreeها دست‌نخورده ماندند. تغییرات فعلی هنوز commit یا push نشده‌اند.

### ۱. Upload و اعتبارسنجی Audio

- فهرست Tracks فقط رکوردهایی را برمی‌گرداند که `audio_path` معتبر و نهایی‌شده دارند؛ Draftهای ناقص در این فهرست نمایش داده نمی‌شوند.
- Backend هنگام انتقال به `review` یا `published` وجود Audio نهایی‌شده را اجباری می‌کند.
- `finalize` دیگر نمی‌تواند با حذف مرحلهٔ دریافت Signed URL یا با ارسال `audio:false` برای Track فاقد Audio، پاسخ موفق بدهد. پاسخ خطا `finalize_failed` با علت `upload_missing` است.
- فایل جایگزین ابتدا در مسیر جدید بارگذاری و در Backend از نظر اندازه و امضای فایل بررسی می‌شود. فقط پس از تأیید، مسیر دیتابیس به فایل جدید تغییر می‌کند و حذف فایل قبلی به‌صورت best-effort انجام می‌شود.
- اگر فایل جایگزین نامعتبر باشد، فایل قبلی حفظ می‌شود و فایل جدید رد و پاک‌سازی می‌شود.
- Retry جایگزینی Audio به شناسهٔ همان Track متصل است و به وضعیت لغو Upload قبلی وابسته نیست.

### ۲. مدیریت Track

- Dialog ویرایش Track امکان جایگزینی Audio را اضافه کرده است.
- برای Track منتشرشده، ابتدا باید وضعیت آن از Published خارج شود؛ Backend نیز جایگزینی Audio روی Track منتشرشده را رد می‌کند.
- ویرایش Metadata، Cover، وضعیت حقوق انتشار، Unreleased و اجازهٔ Download موجود حفظ شده است.
- زمان ایجاد، آخرین ویرایش و وضعیت فعلی در Dialog نمایش داده می‌شود.
- قابلیت نمایشی بدون endpoint معتبر اضافه نشده است.

### ۳. مسیرهای Admin

- مسیرها به شکل slash-based هستند: `/adminpanel`، `/adminpanel/dashboard`، `/adminpanel/upload`، `/adminpanel/tracks` و `/adminpanel/administrators`.
- `history.pushState` و `popstate` با مسیرهای جدید کار می‌کنند و ساختن hash برای جابه‌جایی تب‌ها حذف شده است.
- تشخیص Admin در Login بر اساس `location.pathname` و مسیر `/adminpanel` انجام می‌شود.
- میانبر Admin صفحهٔ اصلی به `/adminpanel` اشاره می‌کند.
- `frontend/vercel.json` برای rewrite مسیر پایه و زیرمسیرهای Admin به `admin.html` اضافه شده است.
- لینک Back to Website به `/` حفظ شده است.

**محدودیت تأیید مسیر:** اطلاعات خواندنی پروژهٔ Vercel مقدار Root Directory را در خروجی قابل‌دسترسی نشان نداد. فایل rewrite داخل `frontend` قرار دارد و فقط در صورتی روی Deploy اثر می‌گذارد که Root Directory پروژهٔ `musicfinder-web` برابر `frontend` باشد. این تنظیم را تغییر ندادم و Deploy هم انجام نشد؛ بنابراین فعال‌شدن مسیرهای جدید روی Production هنوز تأیید نشده است.

### ۴. هماهنگی ظاهری

- توکن‌های پایهٔ Admin از palette واقعی صفحهٔ اصلی گرفته شدند: زمینهٔ `#110b08`، سطوح شیشه‌ای گرم، border روشنِ گرم، متن `#f4e8d4` و accentهای آبی/خاکستری، amber و burgundy.
- پس‌زمینهٔ Admin glowهای گرم و لایه‌های رنگی هماهنگ با صفحهٔ اصلی دارد.
- Login اصلی و Admin Login از همان component و فونت برند استفاده می‌کنند؛ پس‌زمینه، دکمه‌ها، ورودی‌ها، focus و scrollbar به palette مشترک نزدیک شده‌اند.
- در RTL، لوگوی واقعی `/favicon.svg` و نوشتهٔ برند در سمت راست قرار می‌گیرند؛ متن MusicFinder به‌صورت LTR و ایزوله باقی می‌ماند.
- عنوان Header به `MusicFinder · adminpanel` تغییر کرده و فاصلهٔ مصنوعی بین `Music` و `Finder` حذف شده است.
- `theme-color` صفحهٔ اصلی و Admin با زمینهٔ واقعی `#110b08` هماهنگ شده است.

**محدودیت بررسی بصری:** اجرای screenshot محلی در Edge به پاسخ `unauthorised` رسید و تصویر قابل‌استفاده‌ای از UI تولید نشد. بنابراین ظاهر با تطبیق توکن‌ها و تست‌های CSS/DOM بررسی شده، نه با تأیید screenshot واقعی در مرورگر.

### ۵. Lyrics و انتخاب متن

- گزینهٔ `Search by lyrics` باقی مانده، اما disabled و غیرقابل کلیک است.
- ترجمهٔ فارسی آن `جستجو با متن آهنگ · موقتاً غیرفعال` است.
- `mfSearchMode` روی `all` باقی می‌ماند.
- انتخاب متن رابط به‌صورت پیش‌فرض غیرفعال است؛ ورودی‌ها، textarea، select، Search Bar و تمام محتوای Search Results استثنای انتخاب‌پذیری دارند.

## نتایج اعتبارسنجی

| بررسی | نتیجه |
|---|---:|
| کل Python suite | **147 passed** |
| JavaScript test files | **4 فایل موفق** |
| `test_admin_permissions.py` | **52 passed** |
| Inline scripts در `index.html` | 14 بلوک، syntax OK |
| Inline scripts در `admin.html` | 7 بلوک، syntax OK |
| Inline scripts در `confirm.html` | 4 بلوک، syntax OK |
| `python -m compileall` | موفق |
| `node --check` فایل‌های JS اصلی | موفق |
| اعتبار JSON در `frontend/vercel.json` | موفق |
| `git diff --check` | موفق |

تست‌های جدید، حذف Track ناقص از فهرست، جلوگیری از رد شدن از مرحلهٔ Audio، جایگزینی موفق Audio، حفظ فایل قبلی هنگام جایگزینی ناموفق و Retry روی Track درست را پوشش می‌دهند.

## وضعیت Git و محیط‌های متصل

- `HEAD` و `origin/main` همچنان روی `1a3c05e99a462753d5083ebfcbb3145b9940fa41` هستند.
- تغییرات فقط در worktree `.worktree-main-integration` باقی مانده‌اند.
- branchهای محافظت‌شده دست‌نخورده‌اند:
  - `work/owner-agent-20261118`: `6515a228f8f2ead44dc3f10be1a43061ab8f08f2`
  - `feat/admin-ai-agent`: `611ce447174a75cabead09c16bc41c4040a9b03a`
  - `backup/agent-phase1-20261112-005842`: `94e6b2424da4c873ec15e72c261cd3fcec951675`
  - `feature/music-upload`: `02b14a6219389557308ee1520bb0b751aca67286`
- پوشهٔ اصلی `MusicFinder` و worktreeهای دیگر تغییر داده نشدند.
- تست‌های Upload از Backend درون‌حافظه‌ای استفاده می‌کنند؛ هیچ فایل واقعی به Supabase ارسال یا از آن حذف نشد.
- لاگ‌های Production در بازهٔ بررسی‌شده خطای runtime مرتبط با Upload نشان ندادند؛ در ۳۰ دقیقهٔ اخیر نیز ورودی Upload قابل‌مشاهده نبود. پس عملکرد واقعی Storage در Production هنوز اثبات نشده است.
- آخرین Deploy قابل‌مشاهدهٔ Web همچنان روی SHA پایهٔ `1a3c05e` است.
- هیچ Deploy، push، merge، commit یا Supabase migration انجام نشد.

## کارهای باقی‌مانده پیش از انتشار

1. مقدار Root Directory پروژهٔ `musicfinder-web` در Vercel باید از تنظیمات پروژه تأیید شود.
2. پس از اجازهٔ جداگانه، Preview Deploy انجام شود و مسیرهای `/adminpanel/*` در همان Preview بررسی شوند.
3. در Preview یک فایل صوتی آزمایشی واقعی بارگذاری شود تا signed URL، CORS، PUT، Storage و `finalize` خارج از fake backend نیز تأیید شوند.
4. Login فارسی/انگلیسی و Admin Dashboard/Upload/Tracks با screenshot مرورگر بررسی شوند.
5. پس از تأیید موارد بالا، تغییرات برای commit و انتشار جداگانه بازبینی شوند.

**نتیجه:** اصلاحات کد و تست‌های محلی این مرحله موفق‌اند؛ اما تا زمان تأیید Root Directory، بررسی مرورگر و یک Upload واقعی در Preview، نباید این مرحله را Deploy-ready یا Upload در Production را اثبات‌شده اعلام کرد.
