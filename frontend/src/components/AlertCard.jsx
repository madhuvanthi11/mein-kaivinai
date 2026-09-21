import { useState } from 'react'
import { useLang } from '../hooks/useLang'
import { COLORS, num, stamp } from '../lib/fmt'

/** The weather that justified the proposal. Shown to the reviewer rather than
 *  summarised away, because the reviewer is being asked to take a public-safety
 *  decision and needs the underlying numbers. */
export function Evidence({ alert }) {
  const { t } = useLang()
  const e = alert.evidence || {}
  const rows = [
    [t('temperature'), num(e.temperature_c, 1), '°C'],
    [t('feelsLike'), num(e.apparent_temperature_c, 1), '°C'],
    [t('uhiOffset'), e.uhi_offset_c == null ? '—' : `${e.uhi_offset_c > 0 ? '+' : ''}${e.uhi_offset_c}`, '°C'],
    [t('humidity'), num(e.relative_humidity_pct), '%'],
    [t('wind'), num(e.wind_speed_kmh), 'km/h'],
  ].filter(([, v]) => v !== '—' || true)

  if (!Object.keys(e).length) return null
  return (
    <div className="evidence">
      <dl className="stats compact">
        {rows.map(([k, v, unit]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>
              {v}
              <small>{unit}</small>
            </dd>
          </div>
        ))}
      </dl>
      <p className="muted" style={{ fontSize: 12, margin: '6px 0 0' }}>
        {t('evidenceSource')}: {e.source || 'Open-Meteo'} · {t('confidence')}: {e.confidence} ·{' '}
        {t('observed')} {stamp(e.observed_at)}
      </p>
    </div>
  )
}

/** Who did what, when, and why. An advisory is an accountable act, so the
 *  chain is surfaced rather than buried in a log file. */
export function AuditTrail({ audit }) {
  const { t } = useLang()
  if (!audit || audit.length === 0) {
    return (
      <p className="muted" style={{ fontSize: 13 }}>
        {t('noAuditYet')}
      </p>
    )
  }
  return (
    <ol className="audit">
      {audit.map((x) => (
        <li key={x.id}>
          <span className={`state ${x.to_state}`}>{t(`state_${x.to_state}`)}</span>
          <div>
            <b>{t(`action_${x.action}`)}</b>{' '}
            <span className="muted">
              — {x.actor_name || x.actor_uid} ({t(x.actor_role)}) · {stamp(x.at_utc)} UTC
            </span>
            {x.reason && <p className="reason">“{x.reason}”</p>}
            {Object.keys(x.changes || {}).length > 0 && (
              <p className="muted" style={{ fontSize: 12, margin: '4px 0 0' }}>
                {t('changed')}: {Object.keys(x.changes).join(', ')}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

export function StateBadge({ state }) {
  const { t } = useLang()
  return <span className={`state ${state}`}>{t(`state_${state}`)}</span>
}

export function AlertHeader({ alert }) {
  const { t } = useLang()
  return (
    <div className="wardline">
      <h3 style={{ margin: 0 }}>{alert.ward || alert.city}</h3>
      {alert.city && alert.ward && <span className="badge">{alert.city}</span>}
      {alert.level && (
        <span className="badge" style={{ background: COLORS[alert.level] || undefined }}>
          {t(alert.level)}
        </span>
      )}
      {alert.score != null && <span className="badge">{alert.score}/100</span>}
      <StateBadge state={alert.state} />
    </div>
  )
}

/**
 * Template + variable composer.
 *
 * Advisory text is not free-typed. It is chosen from the catalogue and filled
 * into the slots the template declares. That is a hard requirement for Indian
 * transactional SMS (DLT-registered templates only), and keeping it for in-app
 * delivery means the wording stays reviewable and translated.
 */
export function TemplateComposer({ catalogue, templateId, variables, onChange }) {
  const { t } = useLang()
  const list = (catalogue && catalogue.templates) || []
  const tpl = list.find((x) => x.id === templateId) || list[0]
  const [open, setOpen] = useState(false)
  if (!tpl) return null

  return (
    <div className="composer">
      <button className="btn ghost small" onClick={() => setOpen(!open)}>
        {open ? t('hideEditor') : t('editAdvisory')}
      </button>
      {open && (
        <div className="stack" style={{ gap: 8, marginTop: 10 }}>
          <label className="field">
            {t('template')}
            <select
              value={tpl.id}
              onChange={(e) => onChange({ template_id: e.target.value, variables })}
            >
              {list.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.title}
                </option>
              ))}
            </select>
          </label>
          <div className="slots">
            {tpl.variables.map((name) => (
              <label key={name} className="field">
                {name}
                <input
                  value={variables[name] == null ? '' : variables[name]}
                  onChange={(e) =>
                    onChange({
                      template_id: tpl.id,
                      variables: { ...variables, [name]: e.target.value },
                    })
                  }
                />
              </label>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            {t('templateNote')}
          </p>
        </div>
      )}
    </div>
  )
}

/** Per-channel delivery outcome. Deliberately verbose: the difference between
 *  "written to an inbox" and "a person read it" is the whole point. */
export function DeliveryReport({ delivery }) {
  const { t } = useLang()
  if (!delivery) return null
  return (
    <>
      <h4 style={{ margin: '14px 0 6px' }}>{t('delivery')}</h4>
      <ul className="delivery">
        {delivery.map((d) => (
          <li key={d.channel}>
            <b>{t(`channel_${d.channel}`)}</b>
            <span className={`pill ${d.status}`}>{t(`status_${d.status}`)}</span>
            <span className="muted">{d.detail}</span>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: 12 }}>
        {t('deliveryHonesty')}
      </p>
    </>
  )
}
