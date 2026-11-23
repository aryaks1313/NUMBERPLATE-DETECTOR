"""Optional email and WhatsApp delivery for advisor arrival alerts."""

from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
import logging
import smtplib
import ssl

import requests

from app.config import settings
from app.services.google_oauth import gmail_oauth_status, send_gmail_api_message


logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="advisor-alert")


def normalize_indian_phone(value: str) -> str:
    """Convert a 10-digit Indian mobile number to WhatsApp's country-code form."""
    digits = "".join(character for character in (value or "") if character.isdigit())
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return ""


def _send_email(recipient: str, subject: str, message: str):
    if not (settings.EMAIL_ENABLED and recipient):
        return

    mail = EmailMessage()
    mail["Subject"] = subject
    mail["To"] = recipient
    mail.set_content(message)

    try:
        if settings.EMAIL_AUTH_METHOD == "oauth":
            send_gmail_api_message(recipient, subject, message)
        else:
            if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
                logger.warning("Email alert not sent: SMTP credentials are missing.")
                return
            mail["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.starttls(context=context)
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(mail)
        logger.info("Advisor email notification sent to %s", recipient)
    except Exception:
        logger.exception("Advisor email notification failed for %s", recipient)


def send_test_email():
    """Send a Gmail API or SMTP test to its configured sender account."""
    if not settings.EMAIL_ENABLED:
        raise RuntimeError("Gmail alerts are off. Set EMAIL_ENABLED=true and restart.")
    if settings.EMAIL_AUTH_METHOD == "oauth":
        status = gmail_oauth_status()
        if not status["ready"]:
            raise RuntimeError("Gmail OAuth is not authorized. " + " ".join(status["messages"]))
        sender = send_gmail_api_message(
            None,
            "Service Gate Gmail notification test",
            "Gmail OAuth notifications are connected. This is a test from the Service Gate app.",
        )
        return sender

    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise RuntimeError(
            "Gmail SMTP is missing SMTP_USERNAME or SMTP_PASSWORD. "
            "Use a Google App Password for SMTP_PASSWORD."
        )

    mail = EmailMessage()
    mail["Subject"] = "Service Gate Gmail notification test"
    mail["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    mail["To"] = settings.SMTP_USERNAME
    mail.set_content(
        "Gmail notifications are connected. This is a test from the Service Gate app."
    )
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls(context=context)
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(mail)
    except Exception as exc:
        logger.exception("Gmail test email failed")
        raise RuntimeError(
            f"Gmail test failed ({type(exc).__name__}): {exc}"
        ) from exc
    return settings.SMTP_USERNAME


def _send_whatsapp(recipient: str, plate: str, customer: str, advisor: str, appointment: str):
    phone = normalize_indian_phone(recipient)
    if not (
        settings.WHATSAPP_ENABLED
        and settings.WHATSAPP_ACCESS_TOKEN
        and settings.WHATSAPP_PHONE_NUMBER_ID
        and settings.WHATSAPP_TEMPLATE_NAME
        and phone
    ):
        return

    url = (
        "https://graph.facebook.com/"
        f"{settings.WHATSAPP_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_TEMPLATE_NAME,
            "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": plate or "Unknown plate"},
                    {"type": "text", "text": customer or "Walk-in customer"},
                    {"type": "text", "text": advisor or "Service advisor"},
                    {"type": "text", "text": appointment or "Walk-in"},
                ],
            }],
        },
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Advisor WhatsApp notification accepted for %s", phone)
    except Exception:
        logger.exception("Advisor WhatsApp notification failed for %s", phone)


def queue_advisor_notifications(advisor, result):
    """Queue configured external channels without slowing camera/video recognition."""
    message = result.get("message") or "A vehicle has arrived at the service gate."
    subject = f"Service gate arrival: {result.get('plate_display') or result.get('plate_number', '')}"
    values = (
        advisor.phone or "",
        advisor.email or "",
        result.get("plate_display") or result.get("plate_number") or "",
        result.get("customer_name") or "Walk-in customer",
        advisor.name,
        result.get("booking_time") or "Walk-in",
    )

    if settings.EMAIL_ENABLED:
        if settings.EMAIL_AUTH_METHOD == "oauth":
            if gmail_oauth_status()["ready"] and values[1]:
                _executor.submit(_send_email, values[1], subject, message)
            else:
                logger.warning(
                    "Gmail alert not queued: authorize OAuth and save the assigned advisor email."
                )
        elif settings.SMTP_USERNAME and settings.SMTP_PASSWORD and values[1]:
            _executor.submit(_send_email, values[1], subject, message)
        else:
            logger.warning(
                "Email alert not queued: set SMTP credentials and the assigned advisor email."
            )
    if settings.WHATSAPP_ENABLED:
        if (
            settings.WHATSAPP_ACCESS_TOKEN
            and settings.WHATSAPP_PHONE_NUMBER_ID
            and settings.WHATSAPP_TEMPLATE_NAME
            and normalize_indian_phone(values[0])
        ):
            _executor.submit(_send_whatsapp, values[0], *values[2:])
        else:
            logger.warning(
                "WhatsApp alert not queued: set Cloud API credentials and the assigned advisor phone."
            )
