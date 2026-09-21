import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import Header from './components/Header'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { LangProvider, useLang } from './hooks/useLang'
import Admin from './pages/Admin'
import Citizen from './pages/Citizen'
import Government from './pages/Government'
import SignIn from './pages/SignIn'
import './styles.css'

const PATHS = { citizen: '/', admin: '/admin', government: '/government', signin: '/signin' }

function viewFor(pathname) {
  if (pathname.startsWith('/admin')) return 'admin'
  if (pathname.startsWith('/government')) return 'government'
  if (pathname.startsWith('/signin')) return 'signin'
  return 'citizen'
}

/** Four views, one URL each. The role gate below is a courtesy to the user, not
 *  a security boundary: the backend enforces the same rule on every request. */
function App() {
  const { t } = useLang()
  const { ready, signedIn, role } = useAuth()
  const [view, setView] = useState(() => viewFor(window.location.pathname))

  useEffect(() => {
    const onPop = () => setView(viewFor(window.location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function go(next) {
    if (next === view) return
    window.history.pushState({}, '', PATHS[next] || '/')
    setView(next)
  }

  let page
  if (view === 'signin') {
    page = <SignIn onDone={() => go('citizen')} />
  } else if (view === 'admin' || view === 'government') {
    const needed = view === 'admin' ? 'admin' : 'government'
    if (!ready) page = null
    else if (!signedIn) page = <SignIn onDone={() => go(view)} />
    else if (role !== needed)
      page = (
        <main className="stack">
          <div className="notice warn" role="alert">
            <div>
              <h3>{t('notAuthorised')}</h3>
              <p className="muted">{t('roleNeeded')}</p>
            </div>
          </div>
        </main>
      )
    else page = view === 'admin' ? <Admin /> : <Government />
  } else {
    page = <Citizen />
  }

  return (
    <>
      <Header view={view} onView={go} />
      {page}
    </>
  )
}

createRoot(document.getElementById('root')).render(
  <LangProvider>
    <AuthProvider>
      <App />
    </AuthProvider>
  </LangProvider>,
)
