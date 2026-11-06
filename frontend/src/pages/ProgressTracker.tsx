/**
 * /tracker — Programme Targets (SIDA framework target editor).
 *
 * History: this route once hosted a second "Submission Compliance" tab, but
 * that was retired per Animesh (the Daily Reporting Update on the home page
 * and the per-org "what's being submitted" sections cover the same ground,
 * and its 48h-gap labels contradicted the home 24h rule). The compliance
 * tab and its ~580 lines of supporting code were removed in the audit
 * cleanup sweep; the page now renders ProgrammeTargetsTab only.
 */
import { ProgrammeTargetsTab } from './TargetConfig'

export default function ProgressTracker() {
  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6 lg:px-8">
      <ProgrammeTargetsTab />
    </div>
  )
}
