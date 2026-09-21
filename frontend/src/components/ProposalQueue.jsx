import { useCallback, useEffect, useState } from 'react'
import { AlertHeader, AuditTrail, Evidence, TemplateComposer } from './AlertCard'
import { Unavailable } from './States'
import { useLang } from '../hooks/useLang'
import { adminProposals, rejectProposal, submitProposal, templates } from '../services/api'
import { stamp } from '../lib/fmt'

/**
 * The Admin's review queue.
 *
 * An Admin verifies and forwards. There is no path from this component to a
 * citizen: the only outward action is "submit to Government". The server would
 * refuse anything else even if a button existed.
 */
export default function ProposalQueue({ city, threshold }) {
  const { t } = useLang()
  const [data, setData] = useState(null)
  const [catalogue, setCatalogue] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [edits, setEdits] = useState({})
  const [notes, setNotes] = useState({})

  const load = useCallback(
    async (detect = true) => {
      setBusy(true)
      try {
        setData(await adminProposals(city === 'all' ? null : city, threshold, detect))
        setError(null)
      } catch (err) {
        setError({ kind: err.kind, detail: err.detail })
        setData(null)
      } finally {
        setBusy(false)
      }
    },
    [city, threshold],
  )

  useEffect(() => {
    load()
    templates()
      .then(setCatalogue)
      .catch(() => setCatalogue(null))
  }, [load])

  async function act(fn, ...args) {
    setError(null)
    try {
      await fn(...args)
      await load(false)
    } catch (err) {
      setError({ kind: err.kind, detail: err.detail })
    }
  }

  if (error && (error.kind === 'forbidden' || error.kind === 'unauthenticated')) {
    return (
      <div className="notice warn">
        <div>
          <h3>{t('notAuthorised')}</h3>
          <p className="muted">{error.detail}</p>
        </div>
      </div>
    )
  }

  return (
    <section>
      <div className="sec">
        <h3>
          {t('proposalQueue')}{' '}
          <span className="count">{data ? data.proposals.length : '—'}</span>
        </h3>
        <span className="note">{t('proposalHint')}</span>
      </div>

      {error && <Unavailable kind={error.kind} detail={error.detail} onRetry={load} />}

      {data && (
        <>
          <div className="toolbar">
            <button className="btn ghost" onClick={() => load(true)} disabled={busy}>
              {busy ? t('scanning') : t('scanNow')}
            </button>
            <span className="muted" style={{ fontSize: 13 }}>
              {t('jurisdiction')}: {data.cities.join(', ') || '—'}
            </span>
          </div>

          {data.detection_unavailable.length > 0 && (
            <p className="muted" style={{ fontSize: 13 }}>
              {t('detectionUnavailable')}: {data.detection_unavailable.join(', ')}
            </p>
          )}

          {data.proposals.length === 0 ? (
            <p className="muted">{t('noProposals')}</p>
          ) : (
            <div className="stack">
              {data.proposals.map((a) => {
                const e = edits[a.id] || {
                  template_id: a.template_id,
                  variables: a.variables || {},
                }
                return (
                  <article key={a.id} className="panel">
                    <AlertHeader alert={a} />
                    <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
                      {t('detected')} {stamp(a.created_at_utc)} UTC · {t('threshold')}{' '}
                      {a.threshold}
                    </p>
                    <Evidence alert={a} />
                    <p className="message">{a.message_en}</p>
                    <p className="message ta">{a.message_ta}</p>
                    <TemplateComposer
                      catalogue={catalogue}
                      templateId={e.template_id}
                      variables={e.variables}
                      onChange={(v) => setEdits({ ...edits, [a.id]: v })}
                    />
                    <label className="field">
                      {t('adminNotes')}
                      <input
                        value={notes[a.id] || ''}
                        placeholder={t('notesPlaceholder')}
                        onChange={(ev) => setNotes({ ...notes, [a.id]: ev.target.value })}
                      />
                    </label>
                    <div className="chips">
                      <button
                        className="btn"
                        onClick={() =>
                          act(submitProposal, a.id, {
                            ...(edits[a.id] || {}),
                            admin_notes: notes[a.id] || null,
                          })
                        }
                      >
                        {t('verifyAndSubmit')}
                      </button>
                      <RejectInline onReject={(reason) => act(rejectProposal, a.id, reason)} />
                    </div>
                    <p className="basis">{a.label}</p>
                    <AuditTrail audit={a.audit} />
                  </article>
                )
              })}
            </div>
          )}

          <div className="sec" style={{ marginTop: 22 }}>
            <h4>
              {t('withGovernment')} <span className="count">{data.awaiting_government.length}</span>
            </h4>
          </div>
          {data.awaiting_government.length === 0 ? (
            <p className="muted">{t('nothingPending')}</p>
          ) : (
            <ul className="plain">
              {data.awaiting_government.map((a) => (
                <li key={a.id}>
                  <b>{a.ward || a.city}</b> — {t('awaitingDecision')} ·{' '}
                  <span className="muted">{stamp(a.created_at_utc)} UTC</span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted" style={{ fontSize: 13 }}>
            {data.label}
          </p>
        </>
      )}
    </section>
  )
}

function RejectInline({ onReject }) {
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
        }}
      >
        {t('confirmReject')}
      </button>
    </span>
  )
}
