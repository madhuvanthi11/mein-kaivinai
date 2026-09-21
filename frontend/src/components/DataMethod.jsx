import { useLang } from '../hooks/useLang'

const ROWS = [
  ['live_weather', 'dmLive'],
  ['forecast', 'dmForecast'],
  ['thermal_metrics', 'dmThermal'],
  ['historical_baseline', 'dmHistorical'],
  ['hyperlocal_adjustment', 'dmLocal'],
  ['vulnerability_exposure', 'dmVuln'],
  ['health_outcomes', 'dmHealth'],
]

/** Data & Method: what is connected, what is modelled, what is unavailable. */
export default function DataMethod({ items, historical }) {
  const { t } = useLang()
  const by = Object.fromEntries((items || []).map((i) => [i.item, i]))
  return (
    <details className="panel datamethod">
      <summary>{t('dataMethod')}</summary>
      <dl>
        {ROWS.map(([id, key]) => (
          <div key={id}>
            <dt>{t(`${key}Label`)}</dt>
            <dd>
              {t(`${key}Value`)}
              {by[id] && by[id].status === 'unavailable' && <span className="tag na">{t('unavailable')}</span>}
              {by[id] && by[id].status === 'model-estimated' && <span className="tag">{t('modelEstimated')}</span>}
            </dd>
          </div>
        ))}
      </dl>
      {historical && historical.status === 'unavailable' && (
        <p className="muted small">
          {t('historicalUnavailable')} — {historical.reason}
        </p>
      )}
    </details>
  )
}
