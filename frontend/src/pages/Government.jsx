import { useCallback, useEffect, useState } from 'react'
import {
  AlertHeader,
  AuditTrail,
  DeliveryReport,
  Evidence,
  TemplateComposer,
} from '../components/AlertCard'
import { Loading, Unavailable } from '../components/States'
import { useAuth } from '../hooks/useAuth'
import { useLang } from '../hooks/useLang'
import {
  govAdvisory,
  govApprove,
  govExpire,
  govIssue,
  govModify,
  govQueue,
  govReject,
  wardRegistry,
} from '../services/api'
import { stamp } from '../lib/fmt'

/** The approving authority's desk.
 *
 *  This is the only place in the product from which anything reaches a citizen,
 *  and it only does so for an alert that already carries an approval record.
 *  The server enforces that; this page simply refuses to pretend otherwise. */
export default function Government() {
  const { t } = useLang()
  const { profile } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [draftEdits, setDraftEdits] = useState({})
  const [result, setResult] = useState(null)
  const [wards, setWards] = useState([])
  const [standalone, setStandalone] = useState(null)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      setData(await govQueue())
      setError(null)
    } catch (err) {
      setError({ kind: err.kind, detail: err.detail })
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    load()
    wardRegistry()
      .then((r) => setWards(r.cities))
      .catch(() => setWards([]))
  }, [load])

  async function act(fn, ...args) {
    setError(null)
    try {
      const res = await fn(...args)
      if (res && res.delivery) setResult(res)
      await load()
    } catch (err) {
      setError({ kind: err.kind, detail: err.detail })
    }
  }

  function edits(a) {
    return draftEdits[a.id] || { template_id: a.template_id, variables: a.variables || {} }
  }

  if (error && error.kind === 'forbidden') {
    return (
      <main className="stack">
        <div className="notice warn">
          <div>
            <h3>{t('notAuthorised')}</h3>
            <p className="muted">{error.detail}</p>
          </div>
        </div>
      </main>
    )
  }

  const myCities = (data && data.cities) || []
  const allWards = wards
    .filter((c) => myCities.some((m) => m.toLowerCase() === c.name.toLowerCase()))
    .flatMap((c) => c.wards)

  return (
    <main className="stack">
      <div>
        <div className="wardline">
          <h2>{t('governmentDesk')}</h2>
          <span className="badge">{(profile && profile.jurisdiction.join(', ')) || '—'}</span>
        </div>
        <p className="muted" style={{ fontSize: 14 }}>
          {t('governmentIntro')}
        </p>
      </div>

      <div className="toolbar">
        <button className="btn ghost" onClick={load} disabled={busy}>
          {busy ? t('refreshing') : t('refresh')}
        </button>
        <button className="btn ghost" onClick={() => setStandalone(standalone ? null : {})}>
          {standalone ? t('cancel') : t('newAdvisory')}
        </button>
      </div>

      {error && error.kind !== 'forbidden' && (
        <Unavailable kind={error.kind} detail={error.detail} onRetry={load} />
      )}
      {!data && !error && <Loading rows={2} />}

      {standalone && data && (
        <StandaloneForm
          cities={myCities}
          wards={allWards}
          catalogue={data.templates}
          onCancel={() => setStandalone(null)}
          onSubmit={async (body) => {
            await act(govAdvisory, body)
            setStandalone(null)
          }}
        />
      )}

      {result && (
        <section className="panel">
          <h3>{t('issued')}</h3>
          <p>{result.alert.message_en}</p>
          <DeliveryReport delivery={result.delivery} />
          <button className="btn ghost small" onClick={() => setResult(null)}>
            {t('dismiss')}
          </button>
        </section>
      )}

      {data && (
        <>
          <Section
            title={t('awaitingReview')}
            hint={t('awaitingReviewHint')}
            empty={t('queueEmpty')}
            items={data.awaiting_review}
            render={(a) => (
              <>
                <Evidence alert={a} />
                {a.admin_notes && (
                  <p className="reason">
                    {t('adminNotes')}: “{a.admin_notes}”
                  </p>
                )}
                <p className="message">{a.message_en}</p>
                <p className="message ta">{a.message_ta}</p>
                <TemplateComposer
                  catalogue={data.templates}
                  templateId={edits(a).template_id}
                  variables={edits(a).variables}
                  onChange={(v) => setDraftEdits({ ...draftEdits, [a.id]: v })}
                />
                <div className="chips">
                  <button className="btn" onClick={() => act(govApprove, a.id, null)}>
                    {t('approve')}
                  </button>
                  {draftEdits[a.id] && (
                    <button
                      className="btn ghost"
                      onClick={() =>
                        act(govModify, a.id, {
                          ...draftEdits[a.id],
                          reason: t('revisedWording'),
                        })
                      }
                    >
                      {t('saveRevision')}
                    </button>
                  )}
                  <RejectButton onReject={(reason) => act(govReject, a.id, reason)} />
                </div>
                <AuditTrail audit={a.audit} />
              </>
            )}
          />

          <Section
            title={t('approvedNotIssued')}
            hint={t('approvedHint')}
            empty={t('nothingApproved')}
            items={data.approved_not_issued}
            render={(a) => (
              <>
                <p className="message">{a.message_en}</p>
                <div className="chips">
                  <button className="btn danger" onClick={() => act(govIssue, a.id)}>
                    {t('issueNow')}
                  </button>
                  <RejectButton onReject={(reason) => act(govReject, a.id, reason)} />
                </div>
                <AuditTrail audit={a.audit} />
              </>
            )}
          />

          <Section
            title={t('issuedAlerts')}
            hint={t('issuedHint')}
            empty={t('nothingIssued')}
            items={data.issued}
            render={(a) => (
              <>
                <p className="message">{a.message_en}</p>
                <p className="muted" style={{ fontSize: 13 }}>
                  {t('issuedAt')} {stamp(a.issued_at_utc)} UTC ·{' '}
                  {a.issued_by ? a.issued_by.name : ''}
                </p>
                <p className="basis">{a.label}</p>
                <DeliveryReport delivery={a.delivery} />
                <div className="chips">
                  <button className="btn ghost small" onClick={() => act(govExpire, a.id)}>
                    {t('withdraw')}
                  </button>
                </div>
                <AuditTrail audit={a.audit} />
              </>
            )}
          />
        </>
      )}
    </main>
  )
}

function Section({ title, hint, empty, items, render }) {
  return (
    <section>
      <div className="sec">
        <h3>
          {title} <span className="count">{items.length}</span>
        </h3>
        <span className="note">{hint}</span>
      </div>
      {items.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <div className="stack">
          {items.map((a) => (
            <article key={a.id} className="panel">
              <AlertHeader alert={a} />
              {render(a)}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function RejectButton({ onReject }) {
  const { t } = useLang()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  if (!open) {
    return (
      <button className="btn ghost" onClick={() => setOpen(true)}>
        {t('reject')}
      </button>
    )
  }
  return (
    <span className="chips">
      <input
        value={reason}
        placeholder={t('reasonRequired')}
        onChange={(e) => setReason(e.target.value)}
      />
      <button
        className="btn ghost"
        disabled={!reason.trim()}
        onClick={() => {
          onReject(reason.trim())
          setOpen(false)
          setReason('')
        }}
      >
        {t('confirmReject')}
      </button>
    </span>
  )
}

function StandaloneForm({ cities, wards, catalogue, onCancel, onSubmit }) {
  const { t } = useLang()
  const [city, setCity] = useState(cities[0] || '')
  const [wardIds, setWardIds] = useState([])
  const [templateId, setTemplateId] = useState('planned_event_advisory')
  const [variables, setVariables] = useState({})
  const inCity = wards.filter((w) => w.city === city)

  return (
    <section className="panel">
      <h3>{t('newAdvisory')}</h3>
      <p className="muted" style={{ fontSize: 13 }}>
        {t('newAdvisoryHint')}
      </p>
      <label className="field">
        {t('city')}
        <select value={city} onChange={(e) => setCity(e.target.value)}>
          {cities.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <fieldset className="wardpick">
        <legend>{t('affectedWards')}</legend>
        {inCity.map((w) => (
          <label key={w.id}>
            <input
              type="checkbox"
              checked={wardIds.includes(w.id)}
              onChange={(e) =>
                setWardIds(
                  e.target.checked ? [...wardIds, w.id] : wardIds.filter((x) => x !== w.id),
                )
              }
            />
            {w.name}
          </label>
        ))}
      </fieldset>
      <TemplateComposer
        catalogue={catalogue}
        templateId={templateId}
        variables={variables}
        onChange={(v) => {
          setTemplateId(v.template_id)
          setVariables(v.variables)
        }}
      />
      <div className="chips">
        <button
          className="btn"
          disabled={!city}
          onClick={() =>
            onSubmit({
              city,
              ward_ids: wardIds,
              template_id: templateId,
              variables,
              level: 'Advisory',
            })
          }
        >
          {t('createAdvisory')}
        </button>
        <button className="btn ghost" onClick={onCancel}>
          {t('cancel')}
        </button>
      </div>
    </section>
  )
}
