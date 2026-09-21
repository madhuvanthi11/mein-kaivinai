import { num } from '../lib/fmt'
import { useLang } from '../hooks/useLang'

/** Wind speed, direction and 24-hour trend, all from Open-Meteo values. */
export default function WindPanel({ wind }) {
  const { t } = useLang()
  if (!wind) return null

  const trend = wind.trend.slice(0, 24)
  const peak = Math.max(1, ...trend.map((w) => w.speed_kmh || 0))
  const deg = wind.current_direction_deg

  return (
    <div className="panel">
      <h3>{t('windIntelligence')}</h3>

      <div className="wind-row">
        <div
          className="dial"
          role="img"
          aria-label={`${t('wind')} ${wind.current_direction || ''} ${num(wind.current_speed_kmh)} km/h`}
        >
          <span className="tick n">N</span>
          <span className="tick e">E</span>
          <span className="tick s">S</span>
          <span className="tick w">W</span>
          {/* Meteorological convention: the angle is where the wind comes FROM,
              so the arrow points along the direction of travel. */}
          <span className="arrow" style={{ '--deg': `${(deg ?? 0) + 180}deg` }} />
        </div>

        <div>
          <div style={{ fontSize: 27, fontWeight: 800, letterSpacing: '-0.03em' }}>
            {num(wind.current_speed_kmh)} <small style={{ fontSize: 15 }}>km/h</small>{' '}
            {wind.current_direction || ''}
          </div>
          <div className="muted" style={{ fontSize: 14 }}>
            {t('gusts')} {num(wind.gust_kmh)} km/h
          </div>
          <div className="muted" style={{ fontSize: 14 }}>
            {t('dominantDirection')}: <strong>{wind.dominant_direction || '—'}</strong>
          </div>
        </div>
      </div>

      <p className="muted" style={{ fontSize: 13, margin: '14px 0 6px' }}>
        {t('windTrend')} · {t('maxWind')} {num(wind.max_speed_kmh)} km/h
      </p>
      <div className="spark" aria-hidden="true">
        {trend.map((w) => (
          <i
            key={w.time}
            title={`${w.speed_kmh} km/h ${w.direction || ''}`}
            style={{ height: `${Math.max(3, ((w.speed_kmh || 0) / peak) * 100)}%` }}
          />
        ))}
      </div>

      <p style={{ marginTop: 12, marginBottom: 0, fontSize: 14 }}>
        {(wind.current_speed_kmh || 0) >= 12 ? t('windHelps') : t('windStill')}
      </p>
    </div>
  )
}
