"""Authorize Gmail once using the downloaded Google Desktop OAuth client JSON."""

from app.services.google_oauth import authorize_gmail_oauth


def main():
    try:
        credentials = authorize_gmail_oauth()
    except Exception as exc:
        raise SystemExit(f"Gmail OAuth setup failed: {exc}") from exc
    print("Gmail OAuth setup completed.")
    print("A local refresh token was saved. Keep it private and do not upload it.")
    print("Restart the Service Gate app, then use Notifications > Send test email.")


if __name__ == "__main__":
    main()
