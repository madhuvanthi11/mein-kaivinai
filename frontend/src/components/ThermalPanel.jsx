import { useLang } from '../hooks/useLang'
import { COLORS, DASH, fill, hm, num } from '../lib/fmt'

/** One thermal metric. The category comes from the API, never computed here. */
function Metric({ id, m }) {
  const { t } = useLang()
  const missing = !m || m.value === null || m.value === undefined
  return (
    <div className="tmetric" style={{ '--lvl': m && m.category ? COLORS[m.category] : 'var(--rule-strong)' }}>
      <div className="tm-head">
        <span>{t(`${id}Name`)}</span>
        <span className="tip" tabIndex={0} role="note" title={t(`${id}Tip`)} aria-label={t(`${id}Tip`)}>
          ⓘ
        </span>
      </div>
      <div className="tm-val">
        {missing ? DASH : num(m.value, 1)}
        {!missing && <small>{m.unit}</small>}
      </div>
      {missing ? (
        <div className="tm-cat muted">
          {t(m && m.quality === 'not_applicable' ? 'notApplicable' : 'unavailable')}
        </div>
      ) : (
        <div className="tm-cat">{m.category ? t(m.category) : DASH}</div>
      )}
      <div className="tm-kind muted">{t(id === 'wbgt' ? 'estimatedKind' : 'modelledKind')}</div>
    </div>
  )
}

/** HUMAN THERMAL STRESS: score, the three metrics, and the reasons. */
export default function ThermalPanel({ thermal, window: win, impact }) {
  const { t } = useLang()
  if (!thermal) return null
  const hts = thermal.human_thermal_stress || {}
  const stmts = [
    ...(win && win.persistence ? win.persistence.statements : []),
    ...(win && win.night_heat ? win.night_heat.statements : []),
  ]
  const lvl = hts.level

  return (
    <section>
      <div className="sec">
        <h3>{t('thermalTitle')}</h3>
        <span className="note">{t('thermalNote')}</span>
      </div>

      <div className="hts" style={{ '--lvl': lvl ? COLORS[lvl] : 'var(--rule-strong)' }}>
        <div className="hts-score">
          <b>{hts.score === null || hts.score === undefined ? DASH : Math.round(hts.score)}</b>
          <i>{t('outOf')}</i>
          <span className="hts-level">{lvl ? t(lvl) : t('unavailable')}</span>
        </div>
        <div className="hts-bar" role="img" aria-label={`${t('htsName')} ${hts.score ?? ''}`}>
          <i style={{ width: `${Math.max(0, Math.min(100, hts.score || 0))}%` }} />
          {[25, 45, 65, 80].map((p) => (
            <u key={p} style={{ left: `${p}%` }} />
          ))}
        </div>
        <p className="muted hts-desc">
          {t('htsName')} — {t('htsTip')}
        </p>
      </div>

      <div className="tmetrics">
        <Metric id="utci" m={thermal.utci} />
        <Metric id="wbgt" m={thermal.wbgt} />
        <Metric id="heatIndex" m={thermal.heat_index} />
      </div>

      {/* WHY */}
      <div className="panel why-panel">
        <h3>{t('whyTitle')}</h3>
        <dl className="whylist">
          {[
            ['utci', thermal.utci && thermal.utci.category],
            ['wbgt', thermal.wbgt && thermal.wbgt.category],
            ['heatIndex', thermal.heat_index && thermal.heat_index.category],
          ].map(([id, c]) => (
            <div key={id}>
              <dt>{t(`${id}Short`)}</dt>
              <dd style={{ color: c ? COLORS[c] : undefined }}>{c ? t(c) : t('unavailable')}</dd>
            </div>
          ))}
          {impact && impact.drivers &&
            impact.drivers
              .filter((d) => d.code !== 'thermal_stress')
              .map((d) => (
                <div key={d.code}>
                  <dt>{t(d.code === 'persistence' ? 'persistenceLabel' : 'nightHeatLabel')}</dt>
                  <dd style={{ color: d.level ? COLORS[d.level] : undefined }}>
                    {d.level ? t(d.level) : t('unavailable')}
                  </dd>
                </div>
              ))}
        </dl>
        {stmts.length > 0 && (
          <ul className="stmts">
            {stmts.map((s) => (
              <li key={s.code}>
                {fill(t(`stmt_${s.code}`), {
                  hours: s.hours,
                  from: s.from,
                  to: s.to,
                  days: s.days,
                  stressed_hours: s.stressed_hours,
                  min_temperature_c: s.min_temperature_c,
                })}
              </li>
            ))}
          </ul>
        )}
        {win && win.peak_time && (
          <p className="peakline">
            {t('peakStress')}: <b>{hm(win.peak_time)}</b> · {t('htsName')} {win.max_human_thermal_stress}
            {t('outOf')}
            {win.max_utci !== null && win.max_utci !== undefined ? ` · UTCI ${num(win.max_utci, 1)}°C` : ''}
          </p>
        )}
        {impact && impact.vulnerability_data !== 'available' && (
          <p className="muted small">{t('vulnUnavailable')}</p>
        )}
        <p className="muted small">{t('outcomeNote')}</p>
      </div>
    </section>
  )
}
