"""Local OAuth and Gmail API helpers for service gate notifications."""

import base64
import json
from email.message import EmailMessage
from pathlib import Path

from app.config import settings


BASE_DIR = Path(__file__).resolve().parents[2]
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _configured_path(value: str, default_name: str) -> Path:
    path = Path(value or default_name).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


def find_gmail_oauth_client_file():
    configured = settings.GMAIL_OAUTH_CLIENT_FILE.strip()
    if configured:
        path = _configured_path(configured, "")
        return path if path.is_file() else None

    candidates = list(BASE_DIR.glob("client_secret*.json"))
    candidates.extend((BASE_DIR / "credentials").glob("client_secret*.json"))
    candidates = [path for path in candidates if path.is_file()]
    if len(candidates) != 1:
        return None
    try:
        content = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return candidates[0] if "installed" in content else None


def gmail_token_file() -> Path:
    return _configured_path(settings.GMAIL_OAUTH_TOKEN_FILE, "gmail-oauth-token.json")


def gmail_oauth_status():
    client_file = find_gmail_oauth_client_file()
    token_file = gmail_token_file()
    messages = []
    if settings.EMAIL_AUTH_METHOD != "oauth":
        messages.append("Set EMAIL_AUTH_METHOD=oauth in .env.")
    if not settings.GMAIL_OAUTH_SENDER_EMAIL:
        messages.append("Set GMAIL_OAUTH_SENDER_EMAIL to the authorized Gmail address in .env.")
    if client_file is None:
        messages.append(
            "Put one Google Desktop OAuth client JSON in the project root, "
            "or set GMAIL_OAUTH_CLIENT_FILE to its path."
        )
    if not token_file.is_file():
        messages.append(
            "Run python -m app.services.gmail_oauth_setup and approve Gmail access in the browser."
        )
    elif client_file is not None:
        try:
            from google.oauth2.credentials import Credentials

            credentials = Credentials.from_authorized_user_file(
                str(token_file), [GMAIL_SEND_SCOPE]
            )
            if not credentials.valid and not credentials.refresh_token:
                messages.append(
                    "OAuth token is expired. Run the Gmail OAuth setup command again."
                )
        except Exception:
            messages.append(
                "OAuth token could not be read. Run the Gmail OAuth setup command again."
            )
    ready = client_file is not None and token_file.is_file() and not messages
    return {"ready": ready, "messages": messages or ["Gmail OAuth is authorized."]}


def authorize_gmail_oauth():
    client_file = find_gmail_oauth_client_file()
    if client_file is None:
        raise RuntimeError(
            "No valid Google Desktop OAuth client JSON found. Put one "
            "client_secret*.json file in the project root."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Google OAuth libraries are missing. Stop the server and install "
            "requirements.txt first."
        ) from exc

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_file), [GMAIL_SEND_SCOPE]
    )
    credentials = flow.run_local_server(port=0, open_browser=True)
    token_file = gmail_token_file()
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def _load_gmail_credentials():
    token_file = gmail_token_file()
    if not token_file.is_file():
        raise RuntimeError(
            "Gmail OAuth is not authorized. Run "
            "python -m app.services.gmail_oauth_setup first."
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        credentials = Credentials.from_authorized_user_file(
            str(token_file), [GMAIL_SEND_SCOPE]
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_file.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise RuntimeError("Gmail OAuth token is invalid or expired.")
        return credentials
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Could not load Gmail OAuth token: {exc}") from exc


def send_gmail_api_message(recipient, subject: str, body: str):
    sender = settings.GMAIL_OAUTH_SENDER_EMAIL
    if not sender:
        raise RuntimeError("Set GMAIL_OAUTH_SENDER_EMAIL to the authorized Gmail address in .env.")
    try:
        from googleapiclient.discovery import build

        credentials = _load_gmail_credentials()
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        mail = EmailMessage()
        mail["To"] = recipient or sender
        mail["From"] = sender
        mail["Subject"] = subject
        mail.set_content(body)
        raw = base64.urlsafe_b64encode(mail.as_bytes()).decode("ascii")
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return sender
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Gmail API send failed: {exc}") from exc
