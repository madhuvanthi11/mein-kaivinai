import { useCallback, useEffect, useRef, useState } from 'react'
import CitizenAlerts from '../components/CitizenAlerts'
import DayRibbon from '../components/DayRibbon'
import ActionItems from '../components/ActionItems'
import DataMethod from '../components/DataMethod'
import ForecastDays from '../components/ForecastDays'
import HourlyChart from '../components/HourlyChart'
import ThermalPanel from '../components/ThermalPanel'
import LocationSearch from '../components/LocationSearch'
import RiskMap from '../components/RiskMap'
import WindPanel from '../components/WindPanel'
import { Loading, Unavailable } from '../components/States'
import { useLang } from '../hooks/useLang'
import { useSaved } from '../hooks/useSaved'
import { monitorCity, reverseGeocode, summary } from '../services/api'
import { COLORS, hourLabel, num, stamp } from '../lib/fmt'

/** Initial location only. The user can move anywhere from here. */
const START = { name: 'Chennai', latitude: 13.0827, longitude: 80.2707, timezone: 'Asia/Kolkata' }

export default function Citizen() {
  const { t, lang } = useLang()
  const saved = useSaved()

  const [place, setPlace] = useState(START)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [cityPoints, setCityPoints] = useState([])
  const [locating, setLocating] = useState(false)
  // The browser prompt is preceded by our own explanation of why we are asking
  // and what happens to the fix, so the user is never surprised by it.
  const [gpsAsk, setGpsAsk] = useState(false)
  // Name resolved for a GPS fix, so the heading says where you are rather than
  // "my location". Null whenever OpenStreetMap has no name for the point.
  const [resolved, setResolved] = useState(null)
  const reqId = useRef(0)

  // ---- live weather for the selected place -------------------------------
  const load = useCallback(async () => {
    const id = ++reqId.current
    setError(null)
    setData(null)
    try {
      const d = await summary(place)
      if (id === reqId.current) setData(d)
    } catch (err) {
      if (id === reqId.current) setError({ kind: err.kind, detail: err.detail })
    }
  }, [place.latitude, place.longitude, place.name])

  useEffect(() => {
    load()
  }, [load])

  // ---- the other wards of the same city, for comparison and the map ------
  const city = data && data.ward ? data.ward.city : null
  useEffect(() => {
    if (!city) {
      setCityPoints([])
      return undefined
    }
    let live = true
    monitorCity(city)
      .then((m) => {
        if (live) setCityPoints(m.points)
      })
      .catch(() => {
        if (live) setCityPoints([])
      })
    return () => {
      live = false
    }
  }, [city])

  function useMyLocation() {
    setGpsAsk(false)
    if (!navigator.geolocation) {
      setError({ kind: 'geo', detail: t('locationUnsupported') })
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords
        // Held in memory for this lookup only. Nothing is persisted unless the
        // user presses save or subscribes to a ward.
        setResolved(null)
        let label = null
        try {
          const r = await reverseGeocode(latitude, longitude)
          label = r.place.label
          setResolved(r.place)
        } catch {
          // OpenStreetMap had no name, or was unreachable. The coordinates are
          // shown instead; nothing is invented to fill the gap.
          setResolved(null)
        }
        setLocating(false)
        setPlace({
          name: label || `${latitude.toFixed(3)}, ${longitude.toFixed(3)}`,
          latitude,
          longitude,
        })
      },
      () => {
        setLocating(false)
        setError({ kind: 'geo', detail: t('locationDenied') })
      },
      { timeout: 10000, maximumAge: 60000 },
    )
  }

  const risk = data && data.risk
  const current = data && data.current
  const ward = data && data.ward

  const raising = risk
    ? risk.drivers.filter((d) => d.effect === 'raise').map((d) => t(d.code, 'driver'))
    : []
  const relief = risk && risk.drivers.find((d) => d.effect === 'reduce')

  const displayName = ward ? ward.name : data ? data.location.name : place.name
  const mine = cityPoints.find((p) => ward && p.ward.id === ward.id)
  const hottest = cityPoints[0]
  const coolest = cityPoints[cityPoints.length - 1]

  return (
    <main className="stack">
      {/* ---------------------------------------------------------- search */}
      <div>
        <LocationSearch
          onPick={(p) => {
            setResolved(null)
            setPlace(p)
          }}
          onError={setError}
        />
        <div className="chips">
          <button className="chip" onClick={() => setGpsAsk(true)} disabled={locating}>
            {locating ? t('locating') : t('useMyLocation')}
          </button>
          {data && (
            <button
              className="chip"
              aria-pressed={saved.has({ name: displayName })}
              onClick={() =>
                saved.save({
                  name: displayName,
                  latitude: data.location.latitude,
                  longitude: data.location.longitude,
                  timezone: data.location.timezone,
                  ward_id: ward ? ward.id : null,
                })
              }
            >
              ★ {t('saveWard')}
            </button>
          )}
          {saved.items.map((s) => (
            <span key={s.name} className="chip">
              <button
                style={{ border: 0, background: 'none', cursor: 'pointer', padding: 0, font: 'inherit' }}
                onClick={() => setPlace(s)}
              >
                {s.name}
              </button>
              <button
                className="x"
                aria-label={`${t('remove')} ${s.name}`}
                style={{ border: 0, background: 'none', cursor: 'pointer' }}
                onClick={() => saved.remove(s.name)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        {saved.items.length > 0 && (
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            {t('savedHint')}
          </p>
        )}
      </div>

      {/* ------------------------------------------- GPS permission explainer */}
      {gpsAsk && (
        <div className="notice" role="dialog" aria-label={t('gpsTitle')}>
          <div>
            <h3>{t('gpsTitle')}</h3>
            <p className="muted" style={{ fontSize: 14 }}>
              {t('gpsWhy')}
            </p>
            <p className="muted" style={{ fontSize: 13 }}>
              {t('gpsPrivacy')}
            </p>
            <div className="chips">
              <button className="btn" onClick={useMyLocation}>
                {t('gpsContinue')}
              </button>
              <button className="btn ghost" onClick={() => setGpsAsk(false)}>
                {t('gpsSkip')}
              </button>
            </div>
            <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
              {t('gpsFallback')}
            </p>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------- states */}
      {error && error.kind === 'geo' && (
        <div className="notice" role="status">
          <p>{error.detail}</p>
        </div>
      )}
      {error && error.kind !== 'geo' && (
        <Unavailable kind={error.kind} detail={error.detail} onRetry={load} />
      )}
      {!data && !error && <Loading />}

      {data && risk && (
        <>
          {/* ------------------------------------------------ ward identity */}
          <div>
            <div className="wardline">
              <h2>{displayName}</h2>
              {ward && <span className="badge">{ward.city}</span>}
              <span className="badge">
                {data.resolution === 'ward' ? t('hyperlocal') : t('areaLevel')}
              </span>
            </div>
            {resolved && (
              <p className="placeline muted">
                {t('yourLocation')}: <b>{resolved.label}</b>
              </p>
            )}
            {data.resolution !== 'ward' && (
              <p className="muted" style={{ fontSize: 14 }}>
                {t('areaExplainer')}
              </p>
            )}
          </div>

          {/* --------------------------------------------------- risk hero */}
          <section className="hero" style={{ '--lvl': COLORS[risk.level] }}>
            <div className="score">
              <b>{risk.score}</b>
              <i>{t('outOf')}</i>
            </div>

            <div>
              <div className="basis" style={{ fontWeight: 800, textTransform: 'uppercase' }}>
                {t('impactTitle')}
              </div>
              <div className="level">{t(risk.level)}</div>
              <p className="why">
                {raising.length > 0
                  ? `${t('riskNow')} ${t('drivenBy')} ${raising.join(` ${t('and')} `)}.`
                  : `${t('riskNow')}: ${t(risk.level)}.`}
                {relief ? ` ${t('easedBy')} ${t(relief.code, 'driver')}.` : ''}
              </p>
              <span className="basis">{t('impactBasis')}</span>
            </div>

            <dl className="stats">
              <div>
                <dt>{t('temperature')}</dt>
                <dd>
                  {num(current.temperature_c, 1)}
                  <small>°C</small>
                </dd>
              </div>
              <div>
                <dt>{t('humidity')}</dt>
                <dd>
                  {num(current.relative_humidity_pct)}
                  <small>%</small>
                </dd>
              </div>
              <div>
                <dt>{t('wind')}</dt>
                <dd>
                  {num(current.wind_speed_kmh)}
                  <small> km/h {data.wind.current_direction || ''}</small>
                </dd>
              </div>
              <div>
                <dt>{t('solarRadiation')}</dt>
                <dd>
                  {num(current.solar_radiation_wm2)}
                  <small> W/m²</small>
                </dd>
              </div>
            </dl>
          </section>

          {/* ---------------------------------- human thermal stress + why */}
          <ThermalPanel thermal={data.thermal && data.thermal.current} window={data.thermal && data.thermal.window_24h} impact={data.impact} />

          {/* ------------------------------------------- 5-day forecast */}
          <ForecastDays days={data.forecast} />

          {/* -------------------------------------------------- advisory */}
          <div className="cols">
            <div className="panel">
              <h3>{t('safety')}</h3>
              <ul>
                {data.recommendations.map((code) => (
                  <li key={code}>{t(code)}</li>
                ))}
              </ul>
              <p className="muted" style={{ fontSize: 13, marginTop: 12, marginBottom: 0 }}>
                {t('guidanceNote')}
              </p>
            </div>
            <CitizenAlerts ward={ward} lang={lang} />
            <WindPanel wind={data.wind} />
          </div>

          {/* --------------------------------------------- the next 24 hrs */}
          <section>
            <div className="sec">
              <h3>{t('today')}</h3>
            </div>
            <DayRibbon
              hourly={data.hourly}
              updatedAt={data.updated_at}
              peakStart={risk.peak_start}
              peakEnd={risk.peak_end}
            />
          </section>

          <div className="peak">
            <span className="muted">{t('peakWindow')}</span>
            {risk.peak_start ? (
              <>
                <b>
                  {hourLabel(risk.peak_start)} – {hourLabel(risk.peak_end)}
                </b>
                <span className="muted">
                  {t('peakScore')} {risk.peak_score}
                  {t('outOf')}
                </span>
              </>
            ) : (
              <b>{t('noPeak')}</b>
            )}
          </div>

          {/* ------------------------------------------- across the city */}
          {mine && hottest && coolest && hottest.ward.id !== coolest.ward.id && (
            <section>
              <div className="sec">
                <h3>{t('acrossCity')}</h3>
                <span className="note">{t('compareHint')}</span>
              </div>
              <dl className="compare">
                <div>
                  <dt>{t('hottestWard')}</dt>
                  <dd>{hottest.ward.name}</dd>
                  <span className="muted" style={{ fontSize: 14 }}>
                    {hottest.risk.score}{t('outOf')} · {t(hottest.risk.level)}
                  </span>
                </div>
                <div>
                  <dt>{t('yourWard')}</dt>
                  <dd>{mine.ward.name}</dd>
                  <span className="muted" style={{ fontSize: 14 }}>
                    {mine.risk.score}{t('outOf')} · {t(mine.risk.level)}
                  </span>
                </div>
                <div>
                  <dt>{t('coolestWard')}</dt>
                  <dd>{coolest.ward.name}</dd>
                  <span className="muted" style={{ fontSize: 14 }}>
                    {coolest.risk.score}{t('outOf')} · {t(coolest.risk.level)}
                  </span>
                </div>
              </dl>
            </section>
          )}

          {/* ------------------------------------------------------- chart */}
          <section>
            <div className="sec">
              <h3>{t('hourlyChart')}</h3>
              <span className="note">{t('chartHint')}</span>
            </div>
            <div className="panel">
              <HourlyChart
                hourly={data.hourly}
                peakStart={risk.peak_start}
                peakEnd={risk.peak_end}
              />
            </div>
          </section>

          {/* --------------------------------------------------------- map */}
          <section>
            <div className="sec">
              <h3>{t('mapTitle')}</h3>
            </div>
            <RiskMap
              center={[data.location.latitude, data.location.longitude]}
              zoom={cityPoints.length ? 11 : 12}
              points={cityPoints}
              selectedId={ward ? ward.id : null}
              onSelect={(id) => {
                const p = cityPoints.find((x) => x.ward.id === id)
                if (p) {
                  setPlace({
                    name: p.ward.name,
                    latitude: p.ward.latitude,
                    longitude: p.ward.longitude,
                  })
                }
              }}
            />
          </section>

          <DataMethod items={data.data_method} historical={data.historical} />

          {/* ------------------------------------------------------ footer */}
          <footer className="foot">
            <span>
              {t('updated')}: <b>{stamp(data.updated_at)}</b>
              {data.location.timezone ? ` (${data.location.timezone})` : ''}
            </span>
            <span>
              <b>{t('source')}</b>
            </span>
            <span>{t('disclaimer')}</span>
            {data.local_context && data.local_context.attribution && (
              <span>{data.local_context.attribution}</span>
            )}
            {resolved && <span>{resolved.attribution}</span>}
            <span>{t('notOfficial')}</span>
          </footer>
        </>
      )}
    </main>
  )
}
