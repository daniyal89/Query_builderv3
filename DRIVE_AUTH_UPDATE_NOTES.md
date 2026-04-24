# Drive auth update

This update changes Google Drive pages to the final user-friendly flow.

## What changed

- Drive Download no longer asks normal users for OAuth client JSON.
- Drive Download defaults to Auto mode: public file download first, then Google login if needed.
- Upload master in Drive no longer shows OAuth client JSON to normal users.
- Optional service-account JSON is still available in Advanced authentication.
- Google login uses this default OAuth client path:

```text
config/google_oauth_client.json
```

You may also set this environment variable:

```text
QUERY_BUILDER_GOOGLE_OAUTH_CLIENT_JSON=C:\path\to\client_secret.json
```

## Required once by the app admin/developer

Create a Google Cloud Desktop OAuth client JSON, rename it to `google_oauth_client.json`, and put it in the `config` folder.

This is not a service-account JSON file.

## After copying this patch

Run:

```powershell
cd frontend
npm install
npm run build
cd ..
python main.py
```

Then press Ctrl+F5 in the browser.
