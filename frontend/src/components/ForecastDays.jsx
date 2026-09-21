import { useLang } from '../hooks/useLang'
import { COLORS, DASH, dayLabel, hm, num } from '../lib/fmt'

/** 5-day thermal-stress forecast. The bar is Human Thermal Stress, not temperature. */
export default function ForecastDays({ days }) {
  const { t, lang } = useLang()
  if (!days || days.length === 0) return null
  return (
    <section>
      <div className="sec">
        <h3>{t('forecastTitle')}</h3>
        <span className="note">{t('forecastNote')}</span>
      </div>
      <div className="fdays">
        {days.map((d) => {
          const lvl = d.level
          const s = d.max_human_thermal_stress
          const n = d.night_heat || {}
          const p = d.persistence || {}
          return (
            <article key={d.date} className="fday" style={{ '--lvl': lvl ? COLORS[lvl] : 'var(--rule-strong)' }}>
              <header>
                <span className="fd-n">
                  {t('day')} {d.day}
                </span>
                <span className="fd-date">{dayLabel(d.date, lang)}</span>
              </header>
              <div className="fd-bar" role="img" aria-label={`${t('htsName')} ${s ?? ''}`}>
                <i style={{ height: `${Math.max(4, Math.min(100, s || 0))}%` }} />
              </div>
              <div className="fd-score">
                <b>{s === null || s === undefined ? DASH : Math.round(s)}</b>
                <small>{t('outOf')}</small>
              </div>
              <div className="fd-level">{lvl ? t(lvl) : t('unavailable')}</div>
              <dl>
                <div>
                  <dt>{t('peakStress')}</dt>
                  <dd>{d.peak_time ? hm(d.peak_time) : DASH}</dd>
                </div>
                <div>
                  <dt>UTCI</dt>
                  <dd>{num(d.max_utci, 1)}°</dd>
                </div>
                <div>
                  <dt>WBGT*</dt>
                  <dd>{num(d.max_wbgt, 1)}°</dd>
                </div>
                <div>
                  <dt>{t('heatIndexShort')}</dt>
                  <dd>{num(d.max_heat_index, 1)}°</dd>
                </div>
                <div>
                  <dt>{t('stressDuration')}</dt>
                  <dd>
                    {p.high_stress_hours ?? 0} h / {p.very_high_stress_hours ?? 0} h
                  </dd>
                </div>
                <div>
                  <dt>{t('nightMin')}</dt>
                  <dd>{n.min_temperature_c != null ? `${num(n.min_temperature_c, 1)}°` : DASH}</dd>
                </div>
              </dl>
            </article>
          )
        })}
      </div>
      <p className="muted small">{t('forecastLegend')}</p>
    </section>
  )
}
