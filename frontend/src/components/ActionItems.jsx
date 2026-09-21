import { useLang } from '../hooks/useLang'

/** Government recommendations: action, trigger, evidence, urgency, locality. */
export default function ActionItems({ items, general = true }) {
  const { t } = useLang()
  if (!items || items.length === 0) return <p className="muted">{t('noActions')}</p>
  return (
    <>
      <ul className="actions">
        {items.map((a, i) => (
          <li key={`${a.code}-${a.locality}-${i}`} className={`urg-${a.urgency}`}>
            <div className="ac-head">
              <b>{t(`act_${a.code}`) !== `act_${a.code}` ? t(`act_${a.code}`) : a.action}</b>
              <span className="urg">{t(`urg_${a.urgency}`)}</span>
            </div>
            <div className="ac-line">
              <span className="muted">{t('trigger')}:</span>{' '}
              {t(`trg_${a.code}`) !== `trg_${a.code}` ? t(`trg_${a.code}`) : a.trigger}
            </div>
            <div className="ac-line">
              <span className="muted">{t('evidence')}:</span> {a.evidence}
            </div>
            <div className="ac-line muted small">
              {t('locality')}: {a.locality}
            </div>
          </li>
        ))}
      </ul>
      {general && <p className="muted small">{t('generalActionNote')}</p>}
    </>
  )
}
