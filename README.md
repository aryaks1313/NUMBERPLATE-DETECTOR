# Coastal Star Service Gate Number Plate Recognition

A web application that reads Indian vehicle registration plates from a live camera or uploaded video, looks for a matching service booking, and alerts the assigned advisor.

## Main features

- YOLO plate detection and PaddleOCR text recognition.
- Indian registration normalization, for example `KL 07 AB 1234`.
- Booking lookup from the database or an imported CSV.
- Best-frame results for each recognized plate, with detector and OCR confidence.
- Two bookings per advisor in each 30-minute time slot.
- High-confidence unmatched arrivals can be assigned to an advisor with available capacity as walk-ins.
- Dashboard notifications, optional Gmail OAuth notifications, and optional WhatsApp Cloud API alerts.
- Video sampling defaults to 4 frames per second for quicker processing. The result page reports the measured processing rate; this target does not guarantee 4 FPS inference speed.

## Requirements

- Windows with Python 3.11 recommended.
- A configured database (SQLite for a local demo, or PostgreSQL).
- The trained plate detector weights, normally `models/best.pt`.
- Network access for PaddleOCR's first model download, unless local OCR model directories are configured.

## Install and run (Windows PowerShell)

1. Create and activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`. Keep your existing `.env` if it already has database settings; add or edit the required values instead of overwriting them.

4. Set `DATABASE_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SESSION_SECRET`, and `YOLO_MODEL_PATH` in `.env`. For the bundled weights, set:

   ```env
   YOLO_MODEL_PATH=models/best.pt
   ```

5. Start the app:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

6. Open `http://127.0.0.1:8000` and sign in with the configured admin credentials.

## Demo workflow

1. In **Service Advisors**, create or update advisor contacts.
2. In **Bookings**, create bookings or import a CSV. Use an Indian plate such as `KL07AB1234` and a date/time matching the demo.
3. In **Video Processing**, upload an MP4, AVI, MOV, or MKV clip with a visible plate. Uploads are limited to 200 MB.
4. Review the recognized plate, best-frame image, confidence scores, booking match, and assigned advisor.
5. Open **Notifications** to view the advisor dashboard alert. External email or WhatsApp requires its own account/API setup.

The app's current default video sampling target is 4 frames per second. Use a short clip with the plate visible for several seconds for a quick presentation. Low-confidence readings are hidden using the thresholds in `.env`.

## Booking CSV format

Use the `bookings-template.csv` download in the app. Required columns are:

```csv
customer_name,phone,vehicle_number,vehicle_model,booking_date,booking_time,service_type,status,advisor_id,advisor_name
Demo Customer,9876543210,KL07AB1234,Mercedes-Benz C-Class,2026-11-23,10:30,General Service,Scheduled,1,Service Advisor 1
```

Use `YYYY-MM-DD` for the date and 24-hour `HH:MM` for time. Each advisor can have no more than two active bookings in the same 30-minute time block. The importer reports row errors and does not partially import an invalid file.

## Gmail OAuth setup

The app uses the Gmail API OAuth flow, so it does not need an SMTP App Password. Enable the Gmail API in the Google Cloud project that owns your Desktop OAuth client. If the consent screen is in Testing, add the account you will authorize as a test user. Put the downloaded Desktop client JSON in the project root, then follow [GMAIL_OAUTH_SETUP.md](GMAIL_OAUTH_SETUP.md).

Run the one-time browser authorization with:

```powershell
.\.venv\Scripts\python.exe -m app.services.gmail_oauth_setup
```

The app saves an OAuth refresh token locally. Keep both the client JSON and generated token private. They are ignored by Git.

## WhatsApp setup

WhatsApp requires a Meta WhatsApp Business Cloud API access token, a Business phone-number ID, and an approved template matching the template name and four body values configured in `.env`. Enable it with `WHATSAPP_ENABLED=true`. Set the recipient phone on the assigned advisor in **Service Advisors**.

## Security and limitations

- Never commit `.env`, OAuth client JSON, OAuth token JSON, or API tokens.
- Recognition accuracy depends on plate size, focus, lighting, angle, detector quality, and OCR model availability. Test with the actual presentation camera and sample clips; the confidence cutoff is not a guarantee of a specific accuracy rate.
- `VIDEO_SAMPLE_FPS` controls how many frames are sampled. The measured processing speed depends on the computer and does not necessarily reach the sampling target.
- For longer-term external use, configure the Google OAuth consent screen and verification status appropriate for the audience.
