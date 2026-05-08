import admin from "firebase-admin";

function initFirebase() {
  if (admin.apps?.length) return;

  const json = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (json) {
    const creds = JSON.parse(json);
    admin.initializeApp({ credential: admin.credential.cert(creds) });
    return;
  }

  // As a last resort, rely on GOOGLE_APPLICATION_CREDENTIALS or default creds.
  admin.initializeApp();
}

export function getDb() {
  initFirebase();
  return admin.firestore();
}

export { admin };

