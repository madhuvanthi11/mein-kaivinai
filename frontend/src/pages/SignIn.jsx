import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useLang } from '../hooks/useLang'
import { wardRegistry } from '../services/api'

const ROLES = [
  { key: 'citizen', uid: 'citizen-1', needsArea: false },
  { key: 'admin', uid: 'admin-1', needsArea: true },
  { key: 'government', uid: 'gov-1', needsArea: true },
]

/**
 * Choose how you are signing in.
 *
 * The role picker is the quick path: pick Citizen, Admin or Government and the
 * app switches immediately. The server still enforces every role and
 * jurisdiction rule against that choice -- picking Admin does not let you issue
 * an alert, and an Admin for Madurai still gets 403 on Coimbatore. What it does
 * not do is *prove* who you are, which is exactly what the banner says.
 *
 * Verified sign-in with Firebase sits below it, and when a build has Firebase
 * configured that is the path to use.
 */
export default function SignIn({ onDone }) {
  const { t } = useLang()
  const { firebaseConfigured, signIn, register, google, setIdentity, identity } = useAuth()
  const [cities, setCities] = useState([])
  const [role, setRole] = useState(identity ? identity.role : 'citizen')
  const [name, setName] = useState(identity ? identity.name || '' : '')
  const [area, setArea] = useState(identity ? identity.jurisdiction || 'all' : 'all')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState('signin')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    wardRegistry()
      .then((r) => setCities(r.cities.map((c) => c.name)))
      .catch(() => setCities([]))
  }, [])

  const chosen = ROLES.find((r) => r.key === role) || ROLES[0]

  function enter() {
    setIdentity({
      uid: `${chosen.uid}`,
      role: chosen.key,
      jurisdiction: chosen.needsArea ? area : 'all',
      name: name.trim() || t(chosen.key),
    })
    if (onDone) onDone()
  }

  async function verified(fn) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      if (onDone) onDone()
    } catch (err) {
      setError(err.message || String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="stack">
      <div className="panel narrow">
        <h2>{t('chooseRole')}</h2>
        <p className="muted" style={{ fontSize: 14, marginTop: 4 }}>
          {t('chooseRoleWhy')}
        </p>

        <div className="rolecards">
          {ROLES.map((r) => (
            <button
              key={r.key}
              type="button"
              className="rolecard"
              aria-pressed={role === r.key}
              onClick={() => setRole(r.key)}
            >
              <b>{t(r.key)}</b>
              <span>{t(`${r.key}Blurb`)}</span>
            </button>
          ))}
        </div>

        <div className="stack" style={{ gap: 10, marginTop: 14 }}>
          <label className="field">
            {t('displayName')}
            <input
              value={name}
              placeholder={t(chosen.key)}
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          {chosen.needsArea && (
            <label className="field">
              {t('jurisdiction')}
              <select value={area} onChange={(e) => setArea(e.target.value)}>
                <option value="all">{t('allCities')}</option>
                {cities.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}

          <button className="btn" onClick={enter}>
            {t('continueAs')} {t(chosen.key)}
          </button>
        </div>

        <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
          {t('roleSwitchNote')}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          {t('demoIdentityBanner')}
        </p>

        {firebaseConfigured && (
          <details className="verified">
            <summary>{t('verifiedSignIn')}</summary>
            <p className="muted" style={{ fontSize: 13 }}>
              {t('verifiedSignInWhy')}
            </p>
            <form
              className="stack"
              style={{ gap: 10 }}
              onSubmit={(e) => {
                e.preventDefault()
                verified(() =>
                  mode === 'signin' ? signIn(email, password) : register(email, password),
                )
              }}
            >
              <label className="field">
                {t('email')}
                <input
                  type="email"
                  value={email}
                  autoComplete="email"
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                {t('password')}
                <input
                  type="password"
                  value={password}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={6}
                  required
                />
              </label>
              <div className="chips">
                <button className="btn" disabled={busy}>
                  {busy ? t('pleaseWait') : mode === 'signin' ? t('signIn') : t('createAccount')}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => setMode(mode === 'signin' ? 'register' : 'signin')}
                >
                  {mode === 'signin' ? t('createAccount') : t('haveAccount')}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => verified(google)}
                  disabled={busy}
                >
                  {t('continueGoogle')}
                </button>
              </div>
            </form>
            <p className="muted" style={{ fontSize: 13 }}>
              {t('roleNote')}
            </p>
          </details>
        )}

        {error && (
          <p className="muted" style={{ fontSize: 13 }}>
            {error}
          </p>
        )}
      </div>
    </main>
  )
}
