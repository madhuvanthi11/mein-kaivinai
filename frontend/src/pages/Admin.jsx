import { useCallback, useEffect, useState } from 'react'
import ProposalQueue from '../components/ProposalQueue'
import ActionItems from '../components/ActionItems'
import DataMethod from '../components/DataMethod'
import ForecastDays from '../components/ForecastDays'
import RiskMap from '../components/RiskMap'
import ThermalPanel from '../components/ThermalPanel'
import { Loading, Unavailable } from '../components/States'
import { useLang } from '../hooks/useLang'
import { monitorCity, wardRegistry } from '../services/api'
import { COLORS, num, signed, stamp } from '../lib/fmt'

/** Map centres per city so the view frames the wards rather than the state. */
const CENTRE = {
  Chennai: [13.05, 80.23],
  Madurai: [9.92, 78.12],
  Coimbatore: [11.01, 76.96],
  Tiruchirappalli: [10.81, 78.7],
  all: [11.2, 78.2],
}

export default function Admin() {
  const { t } = useLang()
  const [cities, setCities] = useState([])
  const [city, setCity] = useState('Madurai')
  const [threshold, setThreshold] = useState(65)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    wardRegistry()
      .then((r) => setCities(r.cities.map((c) => c.name)))
      .catch(() => setCities([]))
  }, [])

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const d = await monitorCity(city, threshold)
      setData(d)
    } catch (err) {
      setError({ kind: err.kind, detail: err.detail })
      setData(null)
    } finally {
      setBusy(false)
    }
  }, [city, threshold])

  useEffect(() => {
    load()
  }, [load])

  // There is deliberately no "send alert" action on this page. An Admin
  // verifies and forwards; only a Government user can issue to citizens, and
  // the server enforces that regardless of what this UI renders.

  const points = data ? data.points : []
  const spread = data && data.spread

  return (
    <main className="stack">
      <div>
        <div className="wardline">
          <h2>{t('controlRoom')}</h2>
          <span className="badge">{city === 'all' ? t('allCities') : city}</span>
        </div>
      </div>

      <div className="toolbar">
        <label>
          {t('city')}
          <select value={city} onChange={(e) => setCity(e.target.value)}>
            {cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
            <option value="all">{t('allCities')}</option>
          </select>
        </label>

        <label>
          {t('threshold')}
          <input
            type="number"
            min="0"
            max="100"
            step="5"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            style={{ width: 84 }}
          />
        </label>

        <button className="btn ghost" onClick={load} disabled={busy}>
          {busy ? t('refreshing') : t('refresh')}
        </button>
      </div>

      <ProposalQueue city={city} threshold={threshold} />

      {error && <Unavailable kind={error.kind} detail={error.detail} onRetry={load} />}
      {!data && !error && <Loading rows={2} />}

      {data && (
        <>
          {/* ------------------------------------------- headline statistic */}
          {spread && spread.feels_like_spread_c != null && (
            <div className="headline">
              <span className="big">
                {spread.hottest_ward} {t('spreadHeadline')} {spread.feels_like_spread_c}°C{' '}
                {t('spreadHotter')} {spread.coolest_ward}
              </span>
              <span className="muted">
                {t('feelsLike')} {spread.feels_like_range_c[0]}°C – {spread.feels_like_range_c[1]}°C
                {' · '}
                {t('score')} {spread.score_range[0]}–{spread.score_range[1]}
              </span>
            </div>
          )}

          {/* ------------------------------------------------- above threshold */}
          <div className={`notice ${data.wards_above_threshold.length ? 'warn' : ''}`}>
            <div>
              <h3>
                {t('wardsAbove')} ({threshold}
                {t('outOf')})
              </h3>
              {data.wards_above_threshold.length === 0 ? (
                <p className="muted">{t('noneAbove')}</p>
              ) : (
                <p>
                  {data.wards_above_threshold
                    .map((w) => `${w.ward} (${w.score})`)
                    .join(', ')}
                </p>
              )}
            </div>
          </div>

          {/* --------------------------------------------------------- map */}
          <section>
            <div className="sec">
              <h3>{t('mapTitle')}</h3>
              <span className="note">{data.label}</span>
            </div>
            <RiskMap
              center={CENTRE[city] || CENTRE.all}
              zoom={city === 'all' ? 7 : 11}
              points={points}
              selectedId={selected}
              onSelect={setSelected}
            />
          </section>

          {/* ------------------------------------------------------- table */}
          <section>
            <div className="sec">
              <h3>{t('hotspots')}</h3>
              <span className="note">{points.length} wards</span>
            </div>
            <div className="panel scroll-x" style={{ padding: '4px 10px' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th className="rank">{t('rank')}</th>
                    <th>{t('ward')}</th>
                    <th>{t('impactTitle')}</th>
                    <th className="num">{t('score')}</th>
                    <th className="num">UTCI</th>
                    <th className="num">{t('wbgtShort')}</th>
                    <th className="num">{t('heatIndexShort')}</th>
                    <th className="num">{t('stressCol')}</th>
                    <th className="num">{t('temperature')}</th>
                    <th className="num">{t('feelsLike')}</th>
                    <th className="num">{t('offsetCol')}</th>
                    <th className="num">{t('humidity')}</th>
                    <th>{t('wind')}</th>
                    <th>{t('peakWindow')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {points.map((p) => (
                    <tr
                      key={p.ward.id}
                      onClick={() => setSelected(p.ward.id)}
                      style={{
                        background: selected === p.ward.id ? 'var(--paper)' : undefined,
                        cursor: 'pointer',
                      }}
                    >
                      <td className="rank">
                        {p.rank}
                        {p.tied && (
                          <span className="muted" style={{ fontWeight: 400 }}>
                            {' '}
                            {t('tied')}
                          </span>
                        )}
                      </td>
                      <td className="name">
                        {p.ward.name}
                        {city === 'all' && (
                          <span className="muted" style={{ fontWeight: 400 }}>
                            {' '}
                            · {p.ward.city}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className="pill" style={{ '--c': COLORS[p.risk.level] }}>
                          <i />
                          {t(p.risk.level)}
                        </span>
                      </td>
                      <td className="num">
                        <strong>{p.risk.score}</strong>
                      </td>
                      <td className="num">{num(p.thermal && p.thermal.utci.value, 1)}°</td>
                      <td className="num">{num(p.thermal && p.thermal.wbgt.value, 1)}°</td>
                      <td className="num">{num(p.thermal && p.thermal.heat_index.value, 1)}°</td>
                      <td className="num">{num(p.thermal && p.thermal.human_thermal_stress.score)}</td>
                      <td className="num">{num(p.current.temperature_c, 1)}°</td>
                      <td className="num">{num(p.current.apparent_temperature_c, 1)}°</td>
                      <td className="num">{signed(p.uhi_offset_c)}°</td>
                      <td className="num">{num(p.current.relative_humidity_pct)}%</td>
                      <td>
                        {num(p.current.wind_speed_kmh)} {p.wind_direction || ''}
                      </td>
                      <td>
                        {p.risk.peak_start
                          ? `${p.risk.peak_start.slice(11, 16)}–${p.risk.peak_end.slice(11, 16)}`
                          : '—'}
                      </td>
                      <td>
                        <span className="muted" style={{ fontSize: 13 }}>
                          {p.risk.score >= threshold ? t('aboveThreshold') : '—'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.unavailable.length > 0 && (
              <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                {t('noDataFor')} {data.unavailable.join(', ')}
              </p>
            )}
          </section>

          {/* ------------------------------- why is this locality at risk */}
          {(() => {
            const sel = points.find((p) => p.ward.id === selected) || points[0]
            if (!sel) return null
            return (
              <div className="stack">
                <div className="sec">
                  <h3>
                    {t('whyArea')} — {sel.ward.name}
                  </h3>
                  <span className="note">
                    {t('pilotLocality')} · {t('impactTitle')}: {t(sel.risk.level)} {sel.risk.score}
                    {t('outOf')}
                  </span>
                </div>
                <ThermalPanel thermal={sel.thermal} window={sel.thermal && sel.thermal.window_24h} impact={sel.impact} />
                <ForecastDays
                  days={sel.forecast_brief}
                />
                <div className="panel">
                  <h3>{t('actionPlan')}</h3>
                  <ActionItems items={sel.actions} />
                </div>
              </div>
            )
          })()}

          {/* ---------------------------------------------- city action plan */}
          <div className="cols">
            <div className="panel">
              <h3>
                {t('officerActions')} — {t('actionPlan')}
              </h3>
              <ActionItems items={data.action_plan} />
              <p className="muted" style={{ fontSize: 13, marginTop: 12, marginBottom: 0 }}>
                {t('govLabel')}
              </p>
            </div>
          </div>

          <DataMethod
            items={[
              { item: 'historical_baseline', status: 'unavailable' },
              { item: 'hyperlocal_adjustment', status: 'model-estimated' },
              { item: 'vulnerability_exposure', status: 'unavailable' },
              { item: 'health_outcomes', status: 'unavailable' },
            ]}
            historical={{ status: 'unavailable', reason: 'Historical dataset not connected' }}
          />

          <footer className="foot">
            <span>
              {t('updated')}: <b>{points[0] ? stamp(points[0].updated_at) : '—'}</b>
            </span>
            <span>
              <b>{t('source')}</b>
            </span>
            <span>{t('disclaimer')}</span>
            <span>{data.land_cover_note}</span>
            <span>{t('notOfficial')}</span>
          </footer>
        </>
      )}
    </main>
  )
}
