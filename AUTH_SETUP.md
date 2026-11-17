# INTERion Google sign-in and approval

## What it does
- Visitors sign in with Google.
- New accounts are saved as **pending** and cannot access any file-sharing route.
- Only the Google account in `INTERION_ADMIN_EMAIL` can open `/admin` and approve or reject accounts.
- Access status is checked on each request, so rejecting a previously approved user blocks the next request.
- Decisions are stored locally in `auth_users.json`.

## One-time setup
1. In Google Cloud Console, create an OAuth 2.0 Client ID with application type **Web application**.
2. Add the exact origin users open to **Authorized JavaScript origins** (for example `http://192.168.1.20:8000`).
3. Set `GOOGLE_CLIENT_ID` to that client ID.
4. Set `INTERION_ADMIN_EMAIL` to the Google account that must be the sole owner/admin.
5. Set `INTERION_SESSION_SECRET` to a random secret of at least 32 characters.
6. Install packages with `pip install -r requirements.txt`, then run `python interion.py`.

Copy `.env.example` as a reference. The app does not automatically load dotenv files; export these variables in your shell or configure them in your process manager. Never commit real credentials or secrets.

## Use
- Visitors sign in at the INTERion home page and see **Pending for approval**.
- The owner signs in with the configured Google account and opens `/admin`.
- Approve or reject each account. Rejected accounts cannot access the file-sharing routes.

## Security notes
- Google ID tokens are verified server-side; client-supplied profile details are not trusted.
- Sessions use signed HTTP-only cookies and a login nonce.
- Use plain HTTP only on a trusted private network. For access beyond a trusted LAN, serve through HTTPS and set `INTERION_COOKIE_SECURE=true`.
- Back up `auth_users.json`. Do not expose it or the `shared_files` directory through a separate static file server.
