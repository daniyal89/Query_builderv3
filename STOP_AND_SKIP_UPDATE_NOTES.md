# Stop and Skip Update Notes

This update adds stop/cancel support and confirms skip behavior for FTP and Google Drive jobs.

## New stop buttons

- FTP Download page: `Stop download`
- Drive Download page: `Stop download`
- Upload master in Drive page: `Stop upload`

When Stop is clicked, the backend marks the job as `cancelling`. The current file operation may need to finish or timeout, then the job becomes `cancelled`.

## Skip behavior

- FTP Download: `skip_existing` skips local files when the local file size already matches the FTP file size.
- Drive Download: when `Overwrite existing local files` is unchecked, existing local files are skipped.
- Drive Upload: when `Skip files that already exist in Drive folder by name` is checked, files already present in the target Drive folder are skipped by filename.

## Rebuild required

This package contains updated frontend source. Rebuild the frontend before running the app:

```powershell
cd D:\PROJECTS\Query_builderv3\frontend
npm install
npm run build
cd ..
python main.py
```

If `npm install` shows Vite peer dependency error, keep `vite` at `^5.4.0` or `^7.3.2`, but do not use Vite 8 with `@vitejs/plugin-react@4.x`.
