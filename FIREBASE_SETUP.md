## Firebase setup

1. Create a Firebase project and add a Web App.
2. Authentication > Sign-in method: enable Google.
3. Authentication > Settings > Authorized domains: add the Vercel domain.
4. Create Cloud Firestore and publish firestore.rules.
5. Deploy this repository to Vercel. Set FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID, FIREBASE_APP_ID, FIREBASE_SERVICE_ACCOUNT (full service-account JSON, secret only in Vercel), and INTERION_ADMIN_EMAIL.
6. Redeploy. Sign into the dashboard with the owner email; it is auto-approved. New users are pending until approved.

## Python host

Install requirements, copy .env.example to .env, set INTERION_CLOUD_URL and FIREBASE_WEB_CONFIG (Firebase Web App config JSON), then run python interion.py. Open the host IP on the computer first and sign in. That account binds the host. Scan the QR on the phone and use the exact same Google account.

## Limits

This first version requires internet for cloud verification. File bytes stay local; metadata logs go to Firestore. Offline authorization is not implemented yet. Local HTTP is not encrypted, so keep use to a trusted LAN until TLS is configured.
