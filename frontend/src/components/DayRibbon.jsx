import { COLORS, inWindow, sameHour, shortHour } from '../lib/fmt'
import { useLang } from '../hooks/useLang'

/**
 * The next 24 hours as one strip you can read at a glance.
 *
 * Twenty-four bars laid on a fixed grid, so the whole day fits the width with
 * no sideways scrolling: bar height is the risk score, colour is the level.
 * Three reference lines behind the bars give the height a scale, the current
 * hour is marked, and the peak window is drawn as a shaded band rather than a
 * detached rule, so you can see which hours it covers.
 *
 * Colour never carries meaning alone: the peak band is labelled, the current
 * hour is labelled, the legend names every level and each bar has a text title.
 */
export default function DayRibbon({ hourly, updatedAt, peakStart, peakEnd }) {
  const { t } = useLang()

  const start = Math.max(0, hourly.findIndex((h) => sameHour(h.time, updatedAt)))
  const day = hourly.slice(start, start + 24)
  if (day.length === 0) return null

  const levels = ['Low', 'Moderate', 'High', 'Very High', 'Extreme']
  // Written as a plain loop rather than findLastIndex: the latter is recent
  // enough that a mid-range phone browser may not have it.
  let peakFrom = -1
  let peakTo = -1
  day.forEach((h, i) => {
    if (!inWindow(h.time, peakStart, peakEnd)) return
    if (peakFrom < 0) peakFrom = i
    peakTo = i
  })

  return (
    <div className="ribbon-wrap">
      <figure className="ribbon-figure">
        {/* Reference lines. Labelled, because an unlabelled gridline is decoration. */}
        <div className="ribbon-scale" aria-hidden="true">
          {[100, 75, 50, 25, 0].map((v) => (
            <span key={v} style={{ '--v': v }}>
              {v}
            </span>
          ))}
        </div>

        <div className="ribbon-plot">
          {peakFrom >= 0 && (
            <div
              className="peakband"
              style={{ '--from': peakFrom, '--to': peakTo + 1 }}
              aria-hidden="true"
            >
              <span>{t('peakWindow')}</span>
            </div>
          )}

          <ol className="ribbon">
            {day.map((h, i) => {
              const score = h.risk_score
              const level = h.level || levelFromScore(score)
              const isNow = i === 0 || sameHour(h.time, updatedAt)
              return (
                <li
                  key={h.time}
                  className={isNow ? 'now' : undefined}
                  title={`${shortHour(h.time)} — ${t(level)} ${score ?? ''}`}
                >
                  <span
                    className="bar"
                    style={{
                      height: `${Math.max(3, score ?? 0)}%`,
                      '--c': COLORS[level] || 'var(--rule-strong)',
                    }}
                  >
                    <b className="bar-value">{score ?? ''}</b>
                  </span>
                </li>
              )
            })}
          </ol>

          {/* Every third hour is labelled: enough to navigate, sparse enough to read. */}
          <ol className="ribbon-hours" aria-hidden="true">
            {day.map((h, i) => (
              <li key={h.time} className={i === 0 ? 'now' : undefined}>
                {i === 0 ? t('now') : i % 3 === 0 ? shortHour(h.time) : ''}
              </li>
            ))}
          </ol>
        </div>
      </figure>

      <div className="legend">
        {levels.map((l) => (
          <span key={l}>
            <i style={{ '--c': COLORS[l] }} />
            {t(l)}
          </span>
        ))}
      </div>
      <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
        {t('ribbonHint')}
      </p>
    </div>
  )
}

function levelFromScore(s) {
  if (s == null) return 'Low'
  if (s < 25) return 'Low'
  if (s < 45) return 'Moderate'
  if (s < 65) return 'High'
  if (s < 80) return 'Very High'
  return 'Extreme'
}
