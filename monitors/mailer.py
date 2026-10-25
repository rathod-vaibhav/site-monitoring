from email.utils import formataddr
from mimetypes import guess_type
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_email(to, subject, html_body, *, text_body=None, cc=None, bcc=None, attachments=None):
    """Send an HTML email through Django's configured SMTP backend."""
    to = [to] if isinstance(to, str) else list(to)
    cc = [cc] if isinstance(cc, str) else list(cc or [])
    if bcc is None:
        configured_bcc = settings.EMAIL_BCC
        bcc = [] if configured_bcc.strip().lower() in ("", "false", "0", "none") else [configured_bcc]
    else:
        bcc = [bcc] if isinstance(bcc, str) else list(bcc or [])
    from_email = formataddr((settings.EMAIL_FROM_NAME, settings.DEFAULT_FROM_EMAIL))

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body or "This message contains HTML. Please view it in an HTML-capable email client.",
        from_email=from_email,
        to=to,
        cc=cc,
        bcc=bcc,
    )
    message.attach_alternative(html_body, "text/html")
    for filename, path in (attachments or {}).items():
        content_type = guess_type(filename)[0] or "application/octet-stream"
        message.attach(filename, Path(path).read_bytes(), content_type)
    return message.send(fail_silently=False)
