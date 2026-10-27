/**
 * فرصة: مُرسِل Gmail عبر Apps Script
 * الاستضافة المجانية تحجب منافذ SMTP، فترسل المنصة الطلب فوق HTTPS إلى هذا السكربت،
 * والسكربت يرسل الرسالة من حساب Gmail الخاص بك (وتظهر في «المرسل»).
 *
 * 1) script.google.com ← مشروع جديد ← الصق هذا الملف.
 * 2) إعدادات المشروع ← خصائص السكربت ← أضف TOKEN بقيمة عشوائية طويلة (نفس GAS_TOKEN في Render).
 * 3) نشر ← نشر جديد ← تطبيق ويب: التنفيذ بصفتي، الوصول: أي شخص. انسخ الرابط إلى GAS_URL.
 */
function doPost(e) {
  var out = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  try {
    var req = JSON.parse(e.postData.contents);
    var token = PropertiesService.getScriptProperties().getProperty("TOKEN");
    if (!token || token.length < 24 || req.token !== token) return out({ ok: false, error: "رمز غير صالح" });
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(req.to || "")) return out({ ok: false, error: "بريد المستلم غير صالح" });

    // منع التكرار: نفس المفتاح خلال 6 ساعات لا يُرسل مرتين
    var lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try {
      var cache = CacheService.getScriptCache();
      var key = "sent:" + String(req.key || "").slice(0, 200);
      if (req.key && cache.get(key)) return out({ ok: true, duplicate: true });

      var opts = {
        name: req.name || undefined,
        replyTo: req.replyTo || undefined,
        attachments: (req.attachments || []).map(function (a) {
          return Utilities.newBlob(Utilities.base64Decode(a.data), a.type || "application/pdf", a.name || "CV.pdf");
        }),
      };
      GmailApp.sendEmail(req.to, req.subject || "", req.body || "", opts);
      if (req.key) cache.put(key, "1", 21600);
    } finally {
      lock.releaseLock();
    }
    return out({ ok: true });
  } catch (err) {
    return out({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}
