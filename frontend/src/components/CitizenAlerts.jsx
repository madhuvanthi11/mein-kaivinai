import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useLang } from '../hooks/useLang'
import { inbox, markRead, mySubscription, subscribe, unsubscribe, wardFeed } from '../services/api'
import { stamp } from '../lib/fmt'

/**
 * What a citizen actually receives.
 *
 * Two distinct things, deliberately kept apart in the UI:
 *
 *  - The **public feed** for the ward being viewed. Issued advisories are a
 *    safety notice, so they are readable without an account.
 *  - The **inbox**, which needs sign-in and an explicit ward subscription.
 *
 * Only the ward ids the user subscribed to are stored. The GPS fix used to find
 * the ward is not persisted, and the panel says what is held and offers to
 * delete it.
 */
export default function CitizenAlerts({ ward, lang }) {
  const { t } = useLang()
  const { signedIn, profile } = useAuth()
  const [feed, setFeed] = useState([])
  const [items, setItems] = useState([])
  const [sub, setSub] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const wardId = ward ? ward.id : null

  useEffect(() => {
    if (!wardId) {
      setFeed([])
      return undefined
    }
    let live = true
    wardFeed(wardId)
      .then((r) => live && setFeed(r.issued))
      .catch(() => live && setFeed([]))
    return () => {
      live = false
    }
  }, [wardId])

  const refresh = useCallback(async () => {
    if (!signedIn) {
      setItems([])
      setSub(null)
      return
    }
    try {
      const [box, s] = await Promise.all([inbox(), mySubscription()])
      setItems(box.items)
      setSub(s.subscription)
      setError(null)
    } catch (err) {
      setError(err.detail || null)
    }
  }, [signedIn, profile])

  useEffect(() => {
    refresh()
  }, [refresh])

  const subscribed = Boolean(sub && wardId && sub.ward_ids.includes(wardId))

  async function toggle() {
    if (!wardId) return
    setBusy(true)
    try {
      const next = subscribed
        ? (sub.ward_ids || []).filter((w) => w !== wardId)
        : [...((sub && sub.ward_ids) || []), wardId]
      if (next.length === 0) await unsubscribe()
      else await subscribe(next)
      await refresh()
    } catch (err) {
      setError(err.detail || null)
    } finally {
      setBusy(false)
    }
  }

  const body = (a) => (lang === 'ta' && a.message_ta ? a.message_ta : a.message_en)

  return (
    <div className="panel">
      <h3>{t('alertsTitle')}</h3>

      {/* ------------------------------------------------- public ward feed */}
      {feed.length === 0 ? (
        <p className="muted" style={{ fontSize: 14 }}>
          {wardId ? t('noActiveAdvisory') : t('advisoriesWardOnly')}
        </p>
      ) : (
        <ul className="advisories">
          {feed.map((a) => (
            <li key={a.id}>
              <span className="pill issued">{t('officialAdvisory')}</span>
              <p>{body(a)}</p>
              <span className="muted" style={{ fontSize: 12 }}>
                {a.issued_by ? `${a.issued_by.name} · ` : ''}
                {stamp(a.issued_at_utc)} UTC
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* ------------------------------------------------- subscription */}
      {!signedIn ? (
        <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
          {t('signInForAlerts')}
        </p>
      ) : (
        <>
          <div className="chips" style={{ marginTop: 12 }}>
            <button className="btn ghost small" onClick={toggle} disabled={!wardId || busy}>
              {subscribed ? t('unsubscribeWard') : t('subscribeWard')}
            </button>
            {sub && sub.ward_ids.length > 0 && (
              <button
                className="btn ghost small"
                onClick={async () => {
                  await unsubscribe()
                  refresh()
                }}
              >
                {t('deleteMyData')}
              </button>
            )}
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            {t('storedNote')}
            {sub && sub.ward_ids.length > 0 ? ` ${sub.ward_ids.join(', ')}` : ` ${t('nothingStored')}`}
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            {t('inAppOnlyNote')}
          </p>

          {/* --------------------------------------------- inbox */}
          <h4 style={{ margin: '14px 0 6px' }}>
            {t('inbox')} <span className="count">{items.filter((i) => !i.read_at_utc).length}</span>
          </h4>
          {items.length === 0 ? (
            <p className="muted" style={{ fontSize: 14, marginBottom: 0 }}>
              {t('inboxEmpty')}
            </p>
          ) : (
            <ul className="advisories">
              {items.map((n) => (
                <li key={n.id} className={n.read_at_utc ? 'read' : 'unread'}>
                  <p>{body(n)}</p>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {stamp(n.created_at_utc)} UTC · {t(`status_${n.status}`)}
                  </span>
                  {!n.read_at_utc && (
                    <button
                      className="btn ghost small"
                      onClick={async () => {
                        await markRead(n.id)
                        refresh()
                      }}
                    >
                      {t('markRead')}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {error && (
        <p className="muted" style={{ fontSize: 12 }}>
          {error}
        </p>
      )}
    </div>
  )
}
