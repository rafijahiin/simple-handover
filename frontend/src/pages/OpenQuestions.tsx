/**
 * Open Questions for the Wednesday meeting.
 *
 * UNFPA-only surface — read-only. Holds the questions Rafi needs Animesh
 * (and Sayeed where relevant) to answer before the next implementation
 * pass. Easier to pull up live in the meeting than scrolling through chat.
 */
import { useTranslation } from 'react-i18next'
import { AlertCircle, HelpCircle, MessageSquare } from 'lucide-react'

interface Question {
  id: string
  category: 'data-model' | 'metric-definition' | 'scope' | 'period' | 'permission'
  forWhom: 'Animesh' | 'Sayeed' | 'Both'
  question: string
  context: string
  blockingForWednesday: boolean
}

const QUESTIONS: Question[] = [
  {
    id: 'rrp-indicators',
    category: 'scope',
    forWhom: 'Animesh',
    question: 'Which 4 activity codes are PHD\'s "major RRP indicators"?',
    context:
      'You said the PHD page should surface "4 major indicators showing progress toward RRP objectives" at the top. We need the specific activity_code list (e.g. 1.1 / 1.4a / 1.7 / 2.2) so they can be highlighted instead of just being four of the 41 generic indicators.',
    blockingForWednesday: false,
  },
  {
    id: 'managed-vs-surgery',
    category: 'metric-definition',
    forWhom: 'Animesh',
    question: 'Is "Managed" the same as "Surgery Done", or a separate metric?',
    context:
      'Your indicator list mentions "Number of cases identified, diagnosed, managed, and referred." We currently track Suspected / Identified / Referred / Surgery Done. "Managed" could mean: (a) surgery completed, (b) any post-diagnosis intervention including counselling + referral, or (c) something else.',
    blockingForWednesday: false,
  },
  {
    id: 'rehab-pct',
    category: 'metric-definition',
    forWhom: 'Animesh',
    question: 'What does "Rehabilitation %" measure?',
    context:
      'Listed as a Fistula indicator. Patients reintegrated into community? Patients receiving counselling? Patients followed up after surgery? Need a definition we can compute against existing data.',
    blockingForWednesday: false,
  },
  {
    id: 'iatrogenic',
    category: 'data-model',
    forWhom: 'Animesh',
    question: 'Add "Iatrogenic fistula" as a distinct diagnosis category?',
    context:
      'You asked for the Fistula Corner pie to show "Obstetric vs Iatrogenic vs Other". Currently the model has VVF / RVF / BOTH / OTHER — no separate Iatrogenic field. If yes, the Kobo Fistula Corner form needs a new radio option and we add a fistula_subtype column to FistulaCornerCase.',
    blockingForWednesday: false,
  },
  {
    id: 'reporting-period',
    category: 'period',
    forWhom: 'Animesh',
    question: 'Default reporting period: contract dates (21 May → 20 Nov 2026) or annual cycle (Oct → Sep)?',
    context:
      'You mentioned annual reporting runs Oct → Sep. The platform currently uses the 6-month contract window (21 May → 20 Nov 2026) as the default for cumulative target math. Two valid options: (a) keep contract dates because that\'s when this funding ends, (b) flip to Oct → Sep so annual report cycles match. Both can coexist if we let the user pick.',
    blockingForWednesday: false,
  },
  {
    id: 'fistula-tile-grouping',
    category: 'scope',
    forWhom: 'Animesh',
    question: 'Fistula campaign metrics — six tiles in one row, or keep Reach (4 tiles) + Funnel (3 tiles) as two sections?',
    context:
      'Your campaign metrics list has six items: Upazilas, Districts, Households, Population, Suspected, Diagnosed. We currently show 4 of these in a "Campaign Reach" band and the other 2 inside the Patient Funnel below. Combining all 6 into one row is denser; keeping two sections is more visual.',
    blockingForWednesday: false,
  },
  // [RESOLVED 2026-06-01] phd-bandhu-mirror — Bandhu and PHD mirror the
  // UI exactly; data differs (different indicators per partner). The
  // shared OrgDashboard component already implements this.
  //
  // [RESOLVED 2026-06-01] manager-permissions — confirmed. Managers can
  // read + download, cannot edit IndicatorTargets or user accounts.
  // Developer + Supervisor manage users. Already implemented.
  {
    id: 'response-plan-form',
    category: 'data-model',
    forWhom: 'Both',
    question: 'When will the Kobo "Response Plan Activity Report" form exist?',
    context:
      'The MPDSR Response Plan Implementation Tracker is hidden right now because the only data source was Sayeed\'s Excel (50% placeholders across rows). We can re-enable the tracker the moment a Kobo form captures live executed-activity counts. Fields needed: district, level (DM/UM), planned_activity_type, executed_count, evidence_photo, date_of_activity.',
    blockingForWednesday: false,
  },
  {
    id: 'denominator-decimals',
    category: 'data-model',
    forWhom: 'Sayeed',
    question: 'Project Deaths 2026 denominators — what do the decimals (10.336, 68.19312, 18.768) represent?',
    context:
      'For Bandarban, Chandpur, Khagrachari your denominator is a fractional number. Other districts are whole (28, 62, 86, 73). Are the decimals (a) population × MMR / 100,000 calculated values that should be rounded to whole numbers, or (b) deaths-per-X rates that need a different display label?',
    blockingForWednesday: false,
  },
  {
    id: 'response-plan-50pct',
    category: 'data-model',
    forWhom: 'Sayeed',
    question: 'Action Plan summary — are the "executed = planned / 2" rows placeholders or real numbers?',
    context:
      '7 of 8 rows in your MPDSR Action Plan sheet show executed = exactly half of planned (Bhola DM 15/30, Bhola UM 60/120, etc.). Looks like placeholder data. Tracker is currently hidden until either (a) real numbers replace these or (b) a Kobo form starts writing live counts.',
    blockingForWednesday: false,
  },
  {
    id: 'monthly-targets',
    category: 'metric-definition',
    forWhom: 'Animesh',
    question: 'When will UNFPA fill in the monthly target splits for all 41 indicators?',
    context:
      'The Target Config page (/tracker → Programme Targets tab) now has a "Monthly Splits" column. Each indicator needs a per-month target for May–Nov 2026. Until UNFPA fills them, the "This month" tile on every indicator shows "Not Set". Sum-of-months should equal the overall target — UI warns if mismatched.',
    blockingForWednesday: false,
  },
]

const CATEGORY_LABELS: Record<Question['category'], string> = {
  'data-model': 'Data Model',
  'metric-definition': 'Metric Definition',
  'scope': 'Scope',
  'period': 'Period',
  'permission': 'Permission',
}

const CATEGORY_COLORS: Record<Question['category'], string> = {
  'data-model': '#F96000',
  'metric-definition': '#C44E00',
  'scope': '#FB904D',
  'period': '#7A2E00',
  'permission': '#F96000',
}

export default function OpenQuestions() {
  const { t: _t } = useTranslation()

  const byPerson: Record<string, Question[]> = { Animesh: [], Sayeed: [], Both: [] }
  for (const q of QUESTIONS) byPerson[q.forWhom].push(q)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32, paddingBottom: 80 }}>
      <section className="hero" style={{ paddingBottom: 0 }}>
        <div className="hero-eyebrow anim-rise">
          <span className="live-dot" />
          <span>MEETING PREP · OPEN QUESTIONS</span>
        </div>
        <h1
          className="hero-headline anim-rise d1"
          style={{
            marginBottom: 6,
            fontSize: 'clamp(40px, 6vw, 80px)',
            letterSpacing: '-0.025em',
            fontWeight: 800,
            color: '#F96000',
          }}
        >
          Open questions
        </h1>
        <p className="hero-lede anim-rise d2" style={{ maxWidth: 720 }}>
          Items needing your input before the next implementation pass.
          Walk through these in the Wednesday meeting. Once answered, the
          corresponding feature moves into the build queue.
        </p>
      </section>

      {(['Animesh', 'Sayeed', 'Both'] as const).map(person => {
        const items = byPerson[person]
        if (!items.length) return null
        return (
          <section key={person} className="section" style={{ marginTop: 8 }}>
            <div className="kicker" style={{ marginBottom: 12 }}>
              <span className="dot" style={{ background: '#F96000' }} />
              FOR {person.toUpperCase()}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {items.map(q => (
                <div key={q.id} className="card" style={{
                  padding: '18px 20px',
                  display: 'flex',
                  gap: 16,
                  alignItems: 'flex-start',
                }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 999,
                    background: `${CATEGORY_COLORS[q.category]}1A`,
                    color: CATEGORY_COLORS[q.category],
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    {q.blockingForWednesday
                      ? <AlertCircle size={18} />
                      : <HelpCircle size={18} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      fontSize: 11, color: 'var(--muted)',
                      textTransform: 'uppercase', letterSpacing: '0.06em',
                      fontWeight: 500, marginBottom: 6,
                    }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4,
                        background: `${CATEGORY_COLORS[q.category]}14`,
                        color: CATEGORY_COLORS[q.category],
                        letterSpacing: '0.04em',
                      }}>
                        {CATEGORY_LABELS[q.category]}
                      </span>
                      {q.blockingForWednesday && (
                        <span style={{
                          padding: '2px 8px', borderRadius: 4,
                          background: 'rgba(241,15,69,0.10)',
                          color: '#F10F45',
                        }}>
                          BLOCKING
                        </span>
                      )}
                    </div>
                    <h3 style={{
                      margin: '0 0 6px', fontSize: 16, fontWeight: 700,
                      color: 'var(--ink)', textWrap: 'pretty' as any,
                    }}>
                      {q.question}
                    </h3>
                    <p style={{
                      margin: 0, fontSize: 13.5, color: 'var(--ink-3)',
                      lineHeight: 1.55, textWrap: 'pretty' as any,
                    }}>
                      {q.context}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )
      })}

      <section className="section" style={{ marginTop: 8 }}>
        <div className="card" style={{
          padding: 20, display: 'flex', gap: 14, alignItems: 'flex-start',
          background: 'rgba(249,96,0,0.06)',
          border: '1px solid rgba(249,96,0,0.20)',
        }}>
          <MessageSquare size={20} color="#F96000" style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <h3 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
              How to use this page
            </h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.55 }}>
              Walk through each card with Animesh and Sayeed in the meeting.
              Capture answers in the Wednesday minutes — once an item is
              resolved, it gets edited out of this file
              (<code style={{ fontSize: 12 }}>frontend/src/pages/OpenQuestions.tsx</code>)
              and the corresponding feature moves into the implementation
              queue. The page is UNFPA-only and not visible to partner
              managers, so it can hold work-in-progress questions safely.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
