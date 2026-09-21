import { useLang } from '../hooks/useLang'

/** Failure and empty states explain what happened and offer the way out.
 *  They never stand in for weather data. */
export function Unavailable({ kind, onRetry, detail }) {
  const { t } = useLang()
  const message =
    kind === 'notfound' ? t('notFound') : kind === 'search' ? t('searchFailed') : t('unavailable')
  return (
    <div className="notice warn" role="alert">
      <div>
        <h3>{message}</h3>
        {detail && kind !== 'notfound' && (
          <p className="muted" style={{ fontSize: 13 }}>
            {detail}
          </p>
        )}
      </div>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          {t('retry')}
        </button>
      )}
    </div>
  )
}

export function Loading({ rows = 3 }) {
  const { t } = useLang()
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <p className="muted">{t('loading')}</p>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 150 : 100 }} />
      ))}
    </div>
  )
}
