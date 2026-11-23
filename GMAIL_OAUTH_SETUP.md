# Gmail notifications with OAuth

This setup uses Google's Gmail API and does not need a Gmail SMTP/App Password.
The downloaded Desktop OAuth client JSON already contains the client ID. Do not
copy the client ID or client secret into `.env`.

## One-time Google Cloud setup

1. In Google Cloud, enable the **Gmail API** for the project that owns the OAuth client.
2. Configure the OAuth consent screen / Google Auth Platform. For an app in **Testing**,
   add the Gmail account you will authorize as a test user.
3. Create an OAuth client with application type **Desktop app**, then download its JSON.
4. Put the JSON in this project folder with its normal `client_secret_*.json` name.
   The app detects a single Desktop client JSON in the project root.

## Authorize this computer

1. In `.env`, set:

   ```env
   EMAIL_ENABLED=true
   EMAIL_AUTH_METHOD=oauth
   GMAIL_OAUTH_CLIENT_FILE=
   GMAIL_OAUTH_TOKEN_FILE=gmail-oauth-token.json
   ```

2. Stop the running server, then install the added libraries:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Run the one-time authorization command:

   ```powershell
   .\.venv\Scripts\python.exe -m app.services.gmail_oauth_setup
   ```

4. In the browser window, choose the sending Gmail account and grant the app
   permission to send email. The app saves a local refresh-token file.
5. Start the app again, open **Notifications**, and use **Send test email to sender
   account**. Set each advisor's destination email in **Service Advisors**.

Keep both the downloaded client JSON and generated OAuth token private. They are
excluded by `.gitignore`. If the OAuth consent screen stays in Testing, refresh tokens
for Gmail scopes can expire after seven days; reauthorize, or publish/verify the app
before using it as a long-term service.
