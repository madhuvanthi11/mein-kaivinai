import { useEffect, useRef, useState } from 'react'
import { geocode } from '../services/api'
import { useLang } from '../hooks/useLang'

/** Geocoding search over the Open-Meteo geocoding API, proxied by the backend.
 *  There is no hardcoded city list anywhere in this component. */
export default function LocationSearch({ onPick, onError }) {
  const { t } = useLang()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  const box = useRef(null)

  useEffect(() => {
    const close = (e) => {
      if (box.current && !box.current.contains(e.target)) setResults(null)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  async function run(e) {
    e.preventDefault()
    const q = query.trim()
    if (q.length < 2) return
    setBusy(true)
    setResults(null)
    onError(null)
    try {
      const { results: found } = await geocode(q)
      setResults(found)
    } catch (err) {
      if (err.kind === 'notfound') setResults([])
      else onError({ kind: 'search', detail: err.detail })
    } finally {
      setBusy(false)
    }
  }

  function choose(r) {
    setResults(null)
    setQuery('')
    onPick({
      name: r.name,
      latitude: r.latitude,
      longitude: r.longitude,
      timezone: r.timezone,
      admin1: r.admin1,
      country: r.country,
    })
  }

  return (
    <div className="finder" ref={box}>
      <form className="search" onSubmit={run} role="search">
        <label className="visually-hidden" htmlFor="place" style={{ position: 'absolute', left: -9999 }}>
          {t('searchLabel')}
        </label>
        <input
          id="place"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('searchPlaceholder')}
          autoComplete="off"
        />
        <button className="btn" disabled={busy || query.trim().length < 2}>
          {busy ? t('searching') : t('searchAction')}
        </button>
      </form>

      {results !== null && (
        <ul className="results">
          {results.length === 0 ? (
            <li>
              <span style={{ display: 'block', padding: '11px 13px' }} className="muted">
                {t('noResults')}
              </span>
            </li>
          ) : (
            results.map((r, i) => (
              <li key={`${r.latitude},${r.longitude},${i}`}>
                <button onClick={() => choose(r)}>
                  <span>{r.name}</span>
                  <span className="where">
                    {[r.admin1, r.country].filter(Boolean).join(', ')}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
