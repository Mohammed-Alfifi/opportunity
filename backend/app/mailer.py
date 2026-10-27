"""إرسال التقديم عبر SMTP أو Gmail Apps Script (لا يُستدعى إلا بعد ضغطك زر الإرسال)."""
import base64
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .config import settings


class MailError(Exception):
    pass


GAS_HOSTS = ("script.google.com", "script.googleusercontent.com")


def configured() -> bool:
    if settings.mail_transport == "gas":
        return bool(settings.gas_url and settings.gas_token)
    return bool(settings.smtp_user and (settings.smtp_password or settings.smtp_security == "none"))


def sender_label() -> str:
    if settings.mail_transport == "gas":
        return settings.smtp_user or "حساب Gmail المرتبط بالسكربت"
    return settings.smtp_user


def build_message(to: str, subject: str, body: str, from_name: str, reply_to: str | None,
                  attachment: bytes | None, attachment_name: str | None) -> EmailMessage:
    for value in (to, subject, from_name, reply_to or ""):
        if "\r" in value or "\n" in value:
            raise MailError("المستلم والموضوع يجب أن يكونا في سطر واحد")
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, settings.smtp_user)) if from_name else settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    if reply_to and reply_to != settings.smtp_user:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if attachment:
        msg.add_attachment(
            attachment, maintype="application", subtype="pdf",
            filename=attachment_name or "CV.pdf",
        )
    return msg


def send(msg: EmailMessage, key: str | None = None) -> None:
    if settings.mail_transport == "gas":
        return _send_gas(msg, key)
    if not configured():
        raise MailError("اضبط SMTP_USER و SMTP_PASSWORD في ملف .env (في Gmail استخدم كلمة مرور التطبيقات)")
    try:
        ctx = ssl.create_default_context()
        security = settings.smtp_security or ("ssl" if settings.smtp_port == 465 else "starttls")
        if security == "none":
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                if settings.smtp_password and s.has_extn("auth"):
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        elif security == "ssl":
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx, timeout=30) as s:
                s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise MailError("رفض الخادم بيانات الدخول؛ تأكد من كلمة مرور التطبيقات") from e
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"فشل الإرسال: {e}") from e


def _send_gas(msg: EmailMessage, key: str | None) -> None:
    """يرسل عبر سكربت Apps Script منشور كتطبيق ويب على حسابك (انظر deploy/gmail-relay.gs).
    الرسالة تخرج من Gmail نفسه وتظهر في «المرسل». key يمنع التكرار إن أعدت المحاولة بعد انقطاع."""
    import httpx
    from urllib.parse import urlparse

    if not configured():
        raise MailError("اضبط GAS_URL و GAS_TOKEN (رابط سكربت الإرسال ورمزه)")
    u = urlparse(settings.gas_url)
    if u.scheme != "https" or u.hostname not in GAS_HOSTS:
        raise MailError("GAS_URL يجب أن يكون رابط تطبيق ويب من script.google.com")
    body_part = msg.get_body(preferencelist=("plain",))
    payload = {
        "token": settings.gas_token,
        "key": key or msg["Message-ID"],
        "to": msg["To"],
        "subject": msg["Subject"],
        "body": body_part.get_content() if body_part else "",
        "name": _display_name(msg["From"]),
        "replyTo": msg["Reply-To"] or "",
        "attachments": [
            {"name": a.get_filename() or "CV.pdf", "type": a.get_content_type(),
             "data": base64.b64encode(a.get_payload(decode=True)).decode()}
            for a in msg.iter_attachments()
        ],
    }
    try:
        # Apps Script يرد بتحويل 302 إلى script.googleusercontent.com حيث تُقرأ النتيجة
        r = httpx.post(settings.gas_url, json=payload, timeout=60, follow_redirects=True)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise MailError(f"تعذّر الوصول إلى سكربت الإرسال: {e}") from e
    if not data.get("ok"):
        raise MailError(f"رفض سكربت الإرسال الطلب: {data.get('error', 'سبب غير معروف')}")


def _display_name(from_header: str | None) -> str:
    from email.utils import parseaddr

    return parseaddr(from_header or "")[0]
