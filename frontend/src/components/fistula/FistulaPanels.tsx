/**
 * Fistula entry panels — replaces the "Awaiting register variables" placeholder
 * stubs on the /fistula page now that the FistulaCornerCase and
 * FistulaCampaignVisit models + API are live.
 *
 * Each panel has a table of recent rows + an "Add new" button that opens
 * a modal entry form. PII fields are entered as plaintext; the backend
 * encrypts on save via the EncryptedCharField pattern.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, X, MapPin } from 'lucide-react'
import { api, apiErrorMessage } from '@/api/client'
import { PageLoader, LoadingSpinner } from '@/components/ui/LoadingSpinner'

// ─── Types (shape mirrors fistula/serializers.py exactly) ──────────────────

interface FistulaCornerCase {
  id: string
  case_hash: string
  patient_name: string
  husband_name: string
  mobile_number: string
  age_years: number | null
  village: string
  union: string
  upazila: string
  district: string
  suspected_date: string | null
  identification_date: string | null
  diagnosis_date: string | null
  informant_name: string
  informant_designation: string
  suffering_duration: string
  fistula_cause: string
  fistula_type: 'VVF' | 'RVF' | 'BOTH' | 'OTHER' | ''
  service_provider_name: string
  service_provider_designation: string
  referral_date: string | null
  referral_place: string
  surgery_performed: 'yes' | 'no' | 'pending' | ''
  referral_outcome: string
  remarks: string
  created_at: string
}

interface FistulaCampaignVisit {
  id: string
  case_hash: string
  visit_date: string
  patient_name: string
  husband_name: string
  contact_number: string
  age_years: number | null
  education: string
  profession: string
  husband_profession: string
  village: string
  union: string
  upazila: string
  district: string
  from_haor: boolean | null
  delivery_mode: 'home' | 'facility' | 'other' | ''
  delivery_outcome: 'LB' | 'SB' | 'UNK' | ''
  suffering_duration: string
  info_source: string
  remarks: string
  created_at: string
}

// ─── Shared field input ────────────────────────────────────────────────────

function Field({
  label, value, onChange, type = 'text', required = false, options,
}: {
  label: string
  value: string | number | null
  onChange: (v: string) => void
  type?: 'text' | 'date' | 'number' | 'select' | 'textarea' | 'tel'
  required?: boolean
  options?: { value: string; label: string }[]
}) {
  const base: React.CSSProperties = {
    width: '100%', borderRadius: 8,
    border: '1px solid var(--hair-2)',
    background: 'var(--surface)', color: 'var(--ink)',
    padding: '8px 12px', fontSize: 13, outline: 'none',
    fontFamily: 'inherit',
  }
  return (
    <div>
      <label style={{
        display: 'block', fontSize: 11, fontWeight: 500,
        color: 'var(--ink-3)', marginBottom: 4,
        textTransform: 'uppercase', letterSpacing: '0.04em',
      }}>
        {label}{required && <span style={{ color: 'var(--coral-deep)' }}> *</span>}
      </label>
      {type === 'select' && options ? (
        <select value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}
                required={required} style={base}>
          <option value="">—</option>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ) : type === 'textarea' ? (
        <textarea value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}
                  required={required} rows={3}
                  style={{ ...base, resize: 'vertical', minHeight: 60 }} />
      ) : (
        <input type={type} value={value ?? ''}
               onChange={(e) => onChange(e.target.value)}
               required={required} style={base} />
      )}
    </div>
  )
}

// ─── Modal scrim ───────────────────────────────────────────────────────────

function Modal({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, background: 'rgba(0,0,0,0.45)',
      backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
    }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{
        width: '100%', maxWidth: 640, padding: 24,
        maxHeight: '90vh', overflowY: 'auto',
        boxShadow: 'var(--sh-3)',
      }}>
        {children}
      </div>
    </div>
  )
}

// ─── Corner panel ──────────────────────────────────────────────────────────

const CORNER_FORM_EMPTY: Partial<FistulaCornerCase> = {
  patient_name: '', husband_name: '', mobile_number: '',
  age_years: null,
  village: '', union: '', upazila: '', district: '',
  suspected_date: null, identification_date: null, diagnosis_date: null,
  informant_name: '', informant_designation: '',
  suffering_duration: '', fistula_cause: '', fistula_type: '',
  service_provider_name: '', service_provider_designation: '',
  referral_date: null, referral_place: '', surgery_performed: '',
  referral_outcome: '', remarks: '',
}

export function FistulaCornerPanel() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<FistulaCornerCase[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<Partial<FistulaCornerCase>>(CORNER_FORM_EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const refetch = () => {
    setLoading(true)
    api.get<{ results?: FistulaCornerCase[] } | FistulaCornerCase[]>('/fistula/corner-cases/')
      .then((r) => setRows(Array.isArray(r.data) ? r.data : (r.data.results ?? [])))
      .finally(() => setLoading(false))
  }
  useEffect(refetch, [])

  const set = (k: keyof FistulaCornerCase) => (v: string) =>
    setForm((f) => ({ ...f, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setError('')
    try {
      // Coerce empty strings to null for nullable date / numeric columns
      const payload = { ...form }
      for (const k of ['suspected_date','identification_date','diagnosis_date','referral_date'] as const) {
        if (payload[k] === '') payload[k] = null
      }
      if (payload.age_years === '' as unknown as number) payload.age_years = null
      await api.post('/fistula/corner-cases/', payload)
      setShowForm(false)
      setForm(CORNER_FORM_EMPTY)
      refetch()
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setSaving(false) }
  }

  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 16, marginBottom: 20,
      }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
            {t('fistula.cornerTitle', { defaultValue: 'Fistula Corner — Diagnosed Cases' })}
          </h2>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4 }}>
            {t('fistula.cornerSub', {
              defaultValue: 'Per-patient diagnostic record at District Hospital. PII encrypted at rest.',
            })}
          </p>
        </div>
        <button onClick={() => setShowForm(true)} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          borderRadius: 999, border: 'none', background: 'var(--unfpa)',
          color: '#fff', padding: '8px 16px', fontSize: 13, fontWeight: 600,
          cursor: 'pointer',
        }}>
          <Plus size={14} />
          {t('fistula.addCase', { defaultValue: 'Add Case' })}
        </button>
      </div>

      {loading && !rows ? <PageLoader /> : (
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                {['Case', 'Patient', 'District', 'Diagnosis Date', 'Type', 'Surgery']
                  .map((h) => <th key={h}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((r) => (
                <tr key={r.id}>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--muted)' }}>
                    {r.case_hash}
                  </td>
                  <td>{r.patient_name || '—'}{r.age_years && <span style={{ color: 'var(--muted)' }}>, {r.age_years}y</span>}</td>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--ink-3)' }}>
                      <MapPin size={11} style={{ color: 'var(--muted)' }} />
                      {[r.village, r.upazila, r.district].filter(Boolean).join(', ') || '—'}
                    </span>
                  </td>
                  <td>{r.diagnosis_date || '—'}</td>
                  <td>{r.fistula_type || '—'}</td>
                  <td>{r.surgery_performed || '—'}</td>
                </tr>
              ))}
              {(rows ?? []).length === 0 && (
                <tr><td colSpan={6} style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--muted)' }}>
                  {t('fistula.empty', { defaultValue: 'No cases recorded yet.' })}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <Modal onClose={() => setShowForm(false)}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
              {t('fistula.newCornerCase', { defaultValue: 'New Fistula Corner Case' })}
            </h3>
            <button onClick={() => setShowForm(false)} aria-label="Close" style={{
              width: 28, height: 28, borderRadius: 999, background: 'var(--surface-2)',
              border: '1px solid var(--hair)', color: 'var(--ink-3)', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <X size={14} />
            </button>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Patient Name" value={form.patient_name ?? ''} onChange={set('patient_name')} required />
              <Field label="Age (years)" value={form.age_years ?? ''} onChange={set('age_years')} type="number" />
              <Field label="Husband's Name" value={form.husband_name ?? ''} onChange={set('husband_name')} />
              <Field label="Mobile" value={form.mobile_number ?? ''} onChange={set('mobile_number')} type="tel" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
              <Field label="Village" value={form.village ?? ''} onChange={set('village')} />
              <Field label="Union" value={form.union ?? ''} onChange={set('union')} />
              <Field label="Upazila" value={form.upazila ?? ''} onChange={set('upazila')} />
              <Field label="District" value={form.district ?? ''} onChange={set('district')} required />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <Field label="Suspected Date" value={form.suspected_date ?? ''} onChange={set('suspected_date')} type="date" />
              <Field label="Identification Date" value={form.identification_date ?? ''} onChange={set('identification_date')} type="date" />
              <Field label="Diagnosis Date" value={form.diagnosis_date ?? ''} onChange={set('diagnosis_date')} type="date" required />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Informant Name" value={form.informant_name ?? ''} onChange={set('informant_name')} />
              <Field label="Informant Designation" value={form.informant_designation ?? ''} onChange={set('informant_designation')} />
            </div>
            <Field label="Suffering Duration" value={form.suffering_duration ?? ''} onChange={set('suffering_duration')} />
            <Field label="Fistula Cause" value={form.fistula_cause ?? ''} onChange={set('fistula_cause')} type="textarea" />
            <Field label="Fistula Type" value={form.fistula_type ?? ''} onChange={set('fistula_type')} type="select"
                   options={[
                     { value: 'VVF', label: 'V.V.F (Vesico-Vaginal)' },
                     { value: 'RVF', label: 'R.V.F (Recto-Vaginal)' },
                     { value: 'BOTH', label: 'V.V.F + R.V.F (Combined)' },
                     { value: 'OTHER', label: 'Other' },
                   ]} required />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Provider Name" value={form.service_provider_name ?? ''} onChange={set('service_provider_name')} />
              <Field label="Provider Designation" value={form.service_provider_designation ?? ''} onChange={set('service_provider_designation')} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <Field label="Referral Date" value={form.referral_date ?? ''} onChange={set('referral_date')} type="date" />
              <Field label="Referral Place" value={form.referral_place ?? ''} onChange={set('referral_place')} />
              <Field label="Surgery Performed" value={form.surgery_performed ?? ''} onChange={set('surgery_performed')} type="select"
                     options={[
                       { value: 'yes', label: 'Yes' },
                       { value: 'no', label: 'No' },
                       { value: 'pending', label: 'Pending' },
                     ]} />
            </div>
            <Field label="Referral Outcome" value={form.referral_outcome ?? ''} onChange={set('referral_outcome')} type="textarea" />
            <Field label="Remarks" value={form.remarks ?? ''} onChange={set('remarks')} type="textarea" />

            {error && <p style={{ fontSize: 12.5, color: 'var(--coral-deep)', margin: 0 }}>{error}</p>}

            <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
              <button type="button" onClick={() => setShowForm(false)} style={{
                flex: 1, borderRadius: 8, border: '1px solid var(--hair-2)',
                background: 'var(--surface-2)', color: 'var(--ink-3)',
                padding: '10px 14px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
              }}>
                {t('fistula.cancel', { defaultValue: 'Cancel' })}
              </button>
              <button type="submit" disabled={saving} style={{
                flex: 1, borderRadius: 8, border: 'none',
                background: 'var(--unfpa)', color: '#fff',
                padding: '10px 14px', fontSize: 13, fontWeight: 600,
                cursor: saving ? 'wait' : 'pointer', opacity: saving ? 0.6 : 1,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}>
                {saving ? <LoadingSpinner size="sm" className="text-white" /> :
                  t('fistula.save', { defaultValue: 'Save Case' })}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

// ─── Campaign panel ────────────────────────────────────────────────────────

const VISIT_FORM_EMPTY: Partial<FistulaCampaignVisit> = {
  visit_date: new Date().toISOString().slice(0, 10),
  patient_name: '', husband_name: '', contact_number: '',
  age_years: null, education: '', profession: '', husband_profession: '',
  village: '', union: '', upazila: '', district: '',
  from_haor: null,
  delivery_mode: '', delivery_outcome: '',
  suffering_duration: '', info_source: '', remarks: '',
}

export function FistulaCampaignPanel() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<FistulaCampaignVisit[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<Partial<FistulaCampaignVisit>>(VISIT_FORM_EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const refetch = () => {
    setLoading(true)
    api.get<{ results?: FistulaCampaignVisit[] } | FistulaCampaignVisit[]>('/fistula/campaign-visits/')
      .then((r) => setRows(Array.isArray(r.data) ? r.data : (r.data.results ?? [])))
      .finally(() => setLoading(false))
  }
  useEffect(refetch, [])

  const set = (k: keyof FistulaCampaignVisit) => (v: string) =>
    setForm((f) => ({ ...f, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setError('')
    try {
      const payload: any = { ...form }
      if (payload.age_years === '') payload.age_years = null
      if (payload.from_haor === '') payload.from_haor = null
      else if (payload.from_haor === 'true' || payload.from_haor === true) payload.from_haor = true
      else if (payload.from_haor === 'false' || payload.from_haor === false) payload.from_haor = false
      await api.post('/fistula/campaign-visits/', payload)
      setShowForm(false)
      setForm(VISIT_FORM_EMPTY)
      refetch()
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setSaving(false) }
  }

  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 16, marginBottom: 20,
      }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
            {t('fistula.campaignTitle', { defaultValue: 'Fistula Campaign — House-Visit Screening' })}
          </h2>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4 }}>
            {t('fistula.campaignSub', {
              defaultValue: 'Per-suspected-case record from house-to-house screening.',
            })}
          </p>
        </div>
        <button onClick={() => setShowForm(true)} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          borderRadius: 999, border: 'none', background: 'var(--unfpa)',
          color: '#fff', padding: '8px 16px', fontSize: 13, fontWeight: 600,
          cursor: 'pointer',
        }}>
          <Plus size={14} />
          {t('fistula.addVisit', { defaultValue: 'Add Visit' })}
        </button>
      </div>

      {loading && !rows ? <PageLoader /> : (
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                {['Case', 'Patient', 'Address', 'Visit Date', 'Delivery', 'Haor']
                  .map((h) => <th key={h}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((r) => (
                <tr key={r.id}>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--muted)' }}>
                    {r.case_hash}
                  </td>
                  <td>{r.patient_name || '—'}{r.age_years && <span style={{ color: 'var(--muted)' }}>, {r.age_years}y</span>}</td>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--ink-3)' }}>
                      <MapPin size={11} style={{ color: 'var(--muted)' }} />
                      {[r.village, r.union, r.upazila].filter(Boolean).join(', ') || '—'}
                    </span>
                  </td>
                  <td>{r.visit_date || '—'}</td>
                  <td>{r.delivery_mode || '—'} / {r.delivery_outcome || '—'}</td>
                  <td>{r.from_haor === true ? 'Yes' : r.from_haor === false ? 'No' : '—'}</td>
                </tr>
              ))}
              {(rows ?? []).length === 0 && (
                <tr><td colSpan={6} style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--muted)' }}>
                  {t('fistula.empty', { defaultValue: 'No visits recorded yet.' })}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <Modal onClose={() => setShowForm(false)}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
              {t('fistula.newCampaignVisit', { defaultValue: 'New House-Visit Record' })}
            </h3>
            <button onClick={() => setShowForm(false)} aria-label="Close" style={{
              width: 28, height: 28, borderRadius: 999, background: 'var(--surface-2)',
              border: '1px solid var(--hair)', color: 'var(--ink-3)', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <X size={14} />
            </button>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Field label="Visit Date" value={form.visit_date ?? ''} onChange={set('visit_date')} type="date" required />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Patient Name" value={form.patient_name ?? ''} onChange={set('patient_name')} required />
              <Field label="Age (years)" value={form.age_years ?? ''} onChange={set('age_years')} type="number" />
              <Field label="Husband's Name" value={form.husband_name ?? ''} onChange={set('husband_name')} />
              <Field label="Contact" value={form.contact_number ?? ''} onChange={set('contact_number')} type="tel" />
              <Field label="Education" value={form.education ?? ''} onChange={set('education')} />
              <Field label="Profession" value={form.profession ?? ''} onChange={set('profession')} />
              <Field label="Husband's Profession" value={form.husband_profession ?? ''} onChange={set('husband_profession')} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
              <Field label="Village" value={form.village ?? ''} onChange={set('village')} />
              <Field label="Union" value={form.union ?? ''} onChange={set('union')} />
              <Field label="Upazila" value={form.upazila ?? ''} onChange={set('upazila')} />
              <Field label="District" value={form.district ?? ''} onChange={set('district')} required />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <Field label="Delivery Mode" value={form.delivery_mode ?? ''} onChange={set('delivery_mode')} type="select"
                     options={[
                       { value: 'home', label: 'Home' },
                       { value: 'facility', label: 'Facility' },
                       { value: 'other', label: 'Other' },
                     ]} />
              <Field label="Delivery Outcome" value={form.delivery_outcome ?? ''} onChange={set('delivery_outcome')} type="select"
                     options={[
                       { value: 'LB', label: 'Live Birth' },
                       { value: 'SB', label: 'Still Birth' },
                       { value: 'UNK', label: 'Unknown' },
                     ]} />
              <Field label="From Haor" value={form.from_haor === null ? '' : String(form.from_haor)} onChange={set('from_haor' as never)} type="select"
                     options={[
                       { value: 'true', label: 'Yes' },
                       { value: 'false', label: 'No' },
                     ]} />
            </div>
            <Field label="Suffering Duration" value={form.suffering_duration ?? ''} onChange={set('suffering_duration')} />
            <Field label="Info Source" value={form.info_source ?? ''} onChange={set('info_source')}
                   />
            <Field label="Remarks" value={form.remarks ?? ''} onChange={set('remarks')} type="textarea" />

            {error && <p style={{ fontSize: 12.5, color: 'var(--coral-deep)', margin: 0 }}>{error}</p>}

            <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
              <button type="button" onClick={() => setShowForm(false)} style={{
                flex: 1, borderRadius: 8, border: '1px solid var(--hair-2)',
                background: 'var(--surface-2)', color: 'var(--ink-3)',
                padding: '10px 14px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
              }}>
                {t('fistula.cancel', { defaultValue: 'Cancel' })}
              </button>
              <button type="submit" disabled={saving} style={{
                flex: 1, borderRadius: 8, border: 'none',
                background: 'var(--unfpa)', color: '#fff',
                padding: '10px 14px', fontSize: 13, fontWeight: 600,
                cursor: saving ? 'wait' : 'pointer', opacity: saving ? 0.6 : 1,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}>
                {saving ? <LoadingSpinner size="sm" className="text-white" /> :
                  t('fistula.save', { defaultValue: 'Save Visit' })}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
