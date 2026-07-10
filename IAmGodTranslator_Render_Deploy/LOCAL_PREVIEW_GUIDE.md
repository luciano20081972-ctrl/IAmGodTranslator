# GodTranslator v10.2 Local Preview Guide

Use this helper to preview the v10.2 feature branch without saving secrets.

```powershell
cd IAmGodTranslator_Render_Deploy
.\run_local_preview.ps1
```

You can also right-click the script and choose **Run with PowerShell**.

The script asks for:

- `DATABASE_URL` as hidden/private input
- `ADMIN_PASSWORD` as hidden/private input
- optional public Supabase Auth settings

It sets `DB_SCHEMA=godtranslator_v10` for the current process only and starts:

```text
http://127.0.0.1:8001
```

Do not paste service-role keys, OpenAI keys, database passwords, or admin passwords into screenshots or documentation.

The helper never creates `.env` and never saves the values you paste. Close the PowerShell window or press `Ctrl+C` to stop the preview.

Recommended checks:

- `http://127.0.0.1:8001/api/health`
- `http://127.0.0.1:8001/#/library`
- `http://127.0.0.1:8001/#/novel/i-am-god`
- `http://127.0.0.1:8001/#/reader/i-am-god/1/ai`
- Admin login, then `#/translate/i-am-god`, `#/jobs`, `#/admin/overview`, `#/admin/missing`, and `#/recovery/i-am-god`
- Confirm mobile widths around `390x844` and tablet width around `768px` have no horizontal overflow or clipped controls.

If Python is not found, install Python 3.12+ or activate the project virtual environment, then run the script again.
