## Firebase and Vercel setup (owner only)

The owner configures the cloud service once. People downloading InterION do **not** create a `.env` file and do **not** enter API keys.

### One-time owner setup

1. Create a Firebase project and add a Web App.
2. In Firebase Authentication, enable Google sign-in.
3. In Authentication settings, add `interion-zeta.vercel.app` to Authorized domains.
4. Create Cloud Firestore.
5. Deploy this repository to Vercel.
6. In Vercel → Project → Settings → Environment Variables, set:
   - `FIREBASE_API_KEY`
   - `FIREBASE_AUTH_DOMAIN`
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_APP_ID`
   - `FIREBASE_SERVICE_ACCOUNT` (the complete service-account JSON; keep this private)
   - `INTERION_ADMIN_EMAIL` (the exact Google email that belongs to the owner)
7. Redeploy after adding or changing environment variables.
8. Open https://interion-zeta.vercel.app/ and sign in with the owner Google account. The matching email is automatically assigned the admin role.

### What downloaded users do

1. Download or clone the repository.
2. Install the packages once with `pip install -r requirements.txt`.
3. Run `python interion.py`.
4. Open the local address printed in the terminal and sign in with Google.

InterION automatically fetches its public Firebase Web App configuration from `https://interion-zeta.vercel.app/api/config`. No local API keys, `.env` file, Firebase console access, or manual configuration is required from downloaded users.

New accounts remain pending until the owner approves them in the Vercel Control Center. Approved users sign in with the same Google account on the host and devices connecting to that host.

### Security and limits

- Only the public Firebase Web App configuration is returned by `/api/config`.
- The Firebase Admin service-account key and owner email stay in Vercel environment variables and are never sent to the Python client.
- The server verifies Firebase ID tokens and checks approval status. Do not put private service-account credentials in the repository.
- File contents stay on the local network; only transfer metadata is sent to the cloud for logs.
- Cloud verification requires an internet connection. Offline authorization is not implemented.
- Local HTTP is not encrypted. Use InterION only on a trusted LAN until TLS is configured.
