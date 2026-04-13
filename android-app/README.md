# ProspEl Receipt Scanner

Small Android companion app for scanning receipt QR codes and sending the QR URL into the current ProspEl backend.

## Features

- connect to the current ProspEl server over LAN;
- log in with the same credentials as the web app;
- load the project list;
- scan receipt QR codes with the phone camera;
- send QR URL to `POST /api/receipts/import-from-qr`;
- assign the imported receipt to the default project immediately.

## Requirements

- Android Studio;
- Android SDK 35;
- Android phone with Android 8+;
- `USB debugging` enabled, or wireless run from Android Studio;
- running ProspEl backend in the same network as the phone.

## Open the project

1. Open this folder in Android Studio:
   `D:\Work\Programming\Buh_Prosp\android-app`
2. Wait for Gradle Sync.
3. If Android Studio asks to install SDK or Build Tools, accept.
4. Connect the phone.
5. Press `Run`.

## First run

1. Open the setup screen.
2. Enter server URL, for example:
   `http://192.168.10.20:5173/`
3. Enter ProspEl username and password.
4. Choose the default project.
5. Tap `Open scanner`.
6. Point the camera at the receipt QR code.
7. When the QR URL appears, tap `Send URL`.

## Notes

- The app uses the same backend and the same database as the main ProspEl system.
- Cleartext HTTP is currently allowed for LAN usage with `192.168.x.x`.
- If the server later moves to HTTPS, just change the server URL in app settings.
- If the scanner cannot access the camera, check Android camera permission for the app.
