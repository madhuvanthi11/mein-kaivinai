/**
 * Optional Firebase.
 *
 * The app is fully usable with none of this configured: weather, risk, the map
 * and the control room all work without an account. Firebase adds sign-in and
 * cross-device syncing of saved places on top.
 *
 * Nothing here runs at import time. `initFirebase()` returns null when the
 * config is absent, and every caller treats null as "run in local mode".
 *
 * Firestore collections used: users, saved_locations, alerts, admin_users.
 * Raw weather is never written to Firestore -- it is fetched live from
 * Open-Meteo on every request and would be stale the moment it was stored.
 */

const cfg = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

export const isConfigured = Boolean(cfg.apiKey && cfg.projectId && cfg.appId)

let cached = null

/** Lazily loads the SDK so an unconfigured build never pays for it. */
export async function initFirebase() {
  if (!isConfigured) return null
  if (cached) return cached

  const [{ initializeApp, getApps }, auth, store] = await Promise.all([
    import('firebase/app'),
    import('firebase/auth'),
    import('firebase/firestore'),
  ])

  const app = getApps().length ? getApps()[0] : initializeApp(cfg)
  cached = { app, auth: auth.getAuth(app), db: store.getFirestore(app), sdk: { auth, store } }
  return cached
}

export async function signInWithEmail(email, password) {
  const fb = await initFirebase()
  if (!fb) throw new Error('Firebase is not configured')
  return fb.sdk.auth.signInWithEmailAndPassword(fb.auth, email, password)
}

export async function registerWithEmail(email, password) {
  const fb = await initFirebase()
  if (!fb) throw new Error('Firebase is not configured')
  return fb.sdk.auth.createUserWithEmailAndPassword(fb.auth, email, password)
}

export async function signInWithGoogle() {
  const fb = await initFirebase()
  if (!fb) throw new Error('Firebase is not configured')
  const provider = new fb.sdk.auth.GoogleAuthProvider()
  return fb.sdk.auth.signInWithPopup(fb.auth, provider)
}

export async function signOut() {
  const fb = await initFirebase()
  if (!fb) return
  return fb.sdk.auth.signOut(fb.auth)
}

export async function watchAuth(cb) {
  const fb = await initFirebase()
  if (!fb) {
    cb(null)
    return () => {}
  }
  return fb.sdk.auth.onAuthStateChanged(fb.auth, cb)
}

/** Saved places sync. Stores a label and coordinates -- never weather. */
export async function pushSavedLocations(uid, places) {
  const fb = await initFirebase()
  if (!fb || !uid) return
  const { doc, setDoc } = fb.sdk.store
  await setDoc(
    doc(fb.db, 'saved_locations', uid),
    {
      places: places.map((p) => ({
        name: p.name,
        latitude: p.latitude,
        longitude: p.longitude,
        timezone: p.timezone || null,
        ward_id: p.ward_id || null,
      })),
      updated_at: new Date().toISOString(),
    },
    { merge: true },
  )
}

export async function pullSavedLocations(uid) {
  const fb = await initFirebase()
  if (!fb || !uid) return []
  const { doc, getDoc } = fb.sdk.store
  const snap = await getDoc(doc(fb.db, 'saved_locations', uid))
  return snap.exists() ? snap.data().places || [] : []
}

export async function isAdmin(uid) {
  const fb = await initFirebase()
  if (!fb || !uid) return false
  const { doc, getDoc } = fb.sdk.store
  const snap = await getDoc(doc(fb.db, 'admin_users', uid))
  return snap.exists()
}

/** Current user's Firebase ID token, or null when signed out / unconfigured.
 *  The backend verifies this against Google's public certificates; the browser
 *  never asserts its own role. */
export async function idToken() {
  const fb = await initFirebase()
  if (!fb || !fb.auth.currentUser) return null
  return fb.auth.currentUser.getIdToken()
}
