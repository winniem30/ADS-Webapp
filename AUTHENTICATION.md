# Firebase authentication setup

The production web app uses Firebase Authentication for sign-in and the Firebase Admin SDK to verify server-side session cookies. The browser does not choose a user ID or role. The server derives the UID and custom `role` claim from the verified Firebase token. Supported roles are `analyst`, `reviewer`, and `administrator`; users without a role claim receive the least-privileged `analyst` role.

## Firebase project setup

1. Create or select the Firebase project that ADS is authorized to use.
2. Register a Firebase web app and enable the Email/Password provider in Authentication.
3. Add the actual web app values to local environment variables or the Render service environment. This app requires:
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_WEB_API_KEY`
   - `FIREBASE_AUTH_DOMAIN`
   - `FIREBASE_WEB_APP_ID`
4. Configure Google Application Default Credentials for the Flask process so `firebase-admin` can verify tokens and create session cookies. On a developer machine, use the approved Google Cloud credentials for the same project. On Render, use a protected Secret File and set `GOOGLE_APPLICATION_CREDENTIALS` to its mounted path. Never commit a service-account key or place it in frontend configuration.
5. Set `AUTH_MODE=firebase`, `FLASK_ENV=production`, and a strong `SECRET_KEY`. Production startup fails closed if Firebase web configuration or the secret is missing.
6. Add the deployed ADS origin to the Firebase Authentication authorized domains.

Firebase web configuration values are public client identifiers; they are not substitutes for Admin credentials. Do not copy values from another project. The Firebase Console and official setup guide provide the real configuration for the project you control.

## Roles

Set Firebase custom claims through a trusted, administrator-controlled provisioning process. For example, an authorized backend can assign a role claim after verifying the operator's identity and approval. Never accept role changes from this browser app. The app defaults missing or unrecognized claims to `analyst`.

Case transitions and assignments enforce reviewer/administrator roles on the server. Reviewer assignment checks the target user's Firebase custom claim. The current role claims must be provisioned outside this app; there is no in-app user/role administration screen.

## Local development

`run_local.bat` selects `FLASK_ENV=development`; `.env.example` sets `AUTH_MODE=development`. The sign-in page then provides a local analyst session for development only. The endpoint returns 404 outside development mode. Do not deploy with this mode.

To exercise Firebase locally, provide the four Firebase web values, `FIREBASE_PROJECT_ID`, and valid Admin SDK credentials, then set `AUTH_MODE=firebase`. No Firebase account, project, or service-account key is supplied by this repository.

## Session behavior

The browser signs in through Firebase Email/Password, sends the short-lived ID token to `/auth/session`, and receives an HttpOnly, SameSite Strict session cookie. Protected HTML and API routes verify the Firebase cookie and revocation status on the backend. `/health` and the IBM service readiness endpoint remain public for hosting health checks. Sign-out clears both Firebase client state and the server cookie.

Firebase session cookies are configured for one hour. Firebase's Admin SDK verifies them server-side and checks revocation; see Google's [Firebase session cookie guidance](https://firebase.google.com/docs/auth/admin/manage-cookies) and [Firebase web app setup](https://firebase.google.com/docs/web/setup).
