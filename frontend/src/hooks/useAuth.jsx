import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  idToken,
  isConfigured,
  signInWithEmail,
  signInWithGoogle,
  signOut as fbSignOut,
  registerWithEmail,
  watchAuth,
} from '../lib/firebase'
import { me, setAuthHeaderSource } from '../services/api'

const Ctx = createContext(null)
const KEY = 'mk.identity'

function stored() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || 'null')
  } catch {
    return null
  }
}

/**
 * Identity in the browser, role from the server.
 *
 * Two ways in, and the app is explicit about which one is in use:
 *
 *  - **Verified sign-in.** A Firebase ID token, checked server-side against
 *    Google's certificates. Available when the build has Firebase config.
 *  - **Demo identity.** You pick a role and the client asserts it in a header.
 *    The server still enforces every role and jurisdiction rule -- a citizen
 *    identity still gets 403 on an officer route -- but the identity itself is
 *    claimed rather than proved, so anyone could claim any role. Fine for a
 *    demo, not for production, and the banner says so.
 *
 * In both cases the role rendered here comes from `GET /api/me`, never from a
 * local guess, and every privileged route re-checks it.
 */
export function AuthProvider({ children }) {
  const [fbUser, setFbUser] = useState(null)
  const [identity, setIdentityState] = useState(stored)
  const [profile, setProfile] = useState(null)
  const [ready, setReady] = useState(!isConfigured)
  const [error, setError] = useState(null)

  // The credential supplier the API client uses on every request.
  useEffect(() => {
    setAuthHeaderSource(async () => {
      if (isConfigured) {
        const token = await idToken()
        if (token) return { Authorization: `Bearer ${token}` }
      }
      if (identity) {
        const { uid, role, jurisdiction, name } = identity
        return {
          'X-Dev-User': [uid, role, jurisdiction || 'all', name || uid].join('|'),
        }
      }
      return {}
    })
  }, [identity, fbUser])

  useEffect(() => {
    if (!isConfigured) return undefined
    let stop = () => {}
    watchAuth((u) => {
      setFbUser(u)
      setReady(true)
    }).then((fn) => {
      if (typeof fn === 'function') stop = fn
    })
    return () => stop()
  }, [])

  const signedIn = Boolean(fbUser) || Boolean(identity)
  const verified = Boolean(fbUser)

  const refresh = useCallback(async () => {
    if (!signedIn) {
      setProfile(null)
      return null
    }
    try {
      const p = await me()
      setProfile(p)
      setError(null)
      return p
    } catch (err) {
      setProfile(null)
      setError(err.detail || 'Could not confirm your role with the server.')
      return null
    }
  }, [signedIn, identity, fbUser])

  useEffect(() => {
    refresh()
  }, [refresh])

  const setIdentity = useCallback((next) => {
    if (next) localStorage.setItem(KEY, JSON.stringify(next))
    else localStorage.removeItem(KEY)
    setIdentityState(next)
  }, [])

  const value = useMemo(
    () => ({
      ready,
      signedIn,
      verified,
      firebaseConfigured: isConfigured,
      identity,
      setIdentity,
      user: fbUser,
      profile,
      role: profile ? profile.role : null,
      error,
      refresh,
      signIn: (email, password) => signInWithEmail(email, password),
      register: (email, password) => registerWithEmail(email, password),
      google: () => signInWithGoogle(),
      signOut: async () => {
        if (isConfigured) await fbSignOut()
        localStorage.removeItem(KEY)
        setIdentityState(null)
        setProfile(null)
      },
    }),
    [ready, signedIn, verified, identity, setIdentity, fbUser, profile, error, refresh],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used inside AuthProvider')
  return v
}
