import { LANGS } from '../i18n'
import { useAuth } from '../hooks/useAuth'
import { useLang } from '../hooks/useLang'

const UIDS = { citizen: 'citizen-1', admin: 'admin-1', government: 'gov-1' }

/** Navigation reflects the role the *server* reported. Tabs for roles the
 *  account does not hold are not rendered -- and if one were, the route behind
 *  it would still return 403. */
export default function Header({ view, onView }) {
  const { lang, setLang, t } = useLang()
  const { signedIn, verified, profile, role, signOut, identity, setIdentity } = useAuth()

  const tabs = [['citizen', t('citizenView')]]
  if (role === 'admin') tabs.push(['admin', t('adminView')])
  if (role === 'government') tabs.push(['government', t('governmentView')])

  function switchTo(next) {
    setIdentity({
      uid: UIDS[next],
      role: next,
      jurisdiction: (identity && identity.jurisdiction) || 'all',
      name: t(next),
    })
    onView(next === 'citizen' ? 'citizen' : next)
  }

  return (
    <header className="top">
      <div className="top-in">
        <h1 className="mark">
          Mein Kaivinai <span>{t('tagline')}</span>
        </h1>
        <nav>
          {tabs.map(([key, label]) => (
            <button
              key={key}
              className="tab"
              aria-current={view === key ? 'page' : undefined}
              onClick={() => onView(key)}
            >
              {label}
            </button>
          ))}

          {signedIn && !verified && (
            <label className="roleswitch">
              <span className="visually-hidden">{t('switchRole')}</span>
              <select value={role || 'citizen'} onChange={(e) => switchTo(e.target.value)}>
                <option value="citizen">{t('citizen')}</option>
                <option value="admin">{t('admin')}</option>
                <option value="government">{t('government')}</option>
              </select>
            </label>
          )}

          {signedIn && verified && (
            <span className="who" title={(profile && profile.email) || ''}>
              {t(role || 'citizen')}
            </span>
          )}

          {signedIn &&
            profile &&
            profile.jurisdiction.length > 0 &&
            profile.role !== 'citizen' && (
              <span className="who">
                <i>{profile.jurisdiction.join(', ')}</i>
              </span>
            )}

          {signedIn ? (
            <button className="tab" onClick={signOut}>
              {t('signOut')}
            </button>
          ) : (
            <button
              className="tab"
              aria-current={view === 'signin' ? 'page' : undefined}
              onClick={() => onView('signin')}
            >
              {t('signIn')}
            </button>
          )}

          <select
            className="lang"
            value={lang}
            aria-label={t('language')}
            onChange={(e) => setLang(e.target.value)}
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </nav>
      </div>

      {/* No banner here: it sat on top of the page content. The same disclosure
          lives on the sign-in page and in GET /api/status (auth.mode). */}
    </header>
  )
}
