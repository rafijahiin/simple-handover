import { cn } from '@/utils/cn'

type Status = string

const STATUS_MAP: Record<string, { label: string; classes: string }> = {
  // Submission statuses
  pending: { label: 'Pending', classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' },
  approved: { label: 'Approved', classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' },
  rejected: { label: 'Rejected', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' },
  // Fistula statuses
  identified: { label: 'Identified', classes: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' },
  action_required: { label: 'Action Required', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' },
  followup_pending: { label: 'Follow-up Pending', classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' },
  referral_completed: { label: 'Referral Completed', classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' },
  // MPDSR statuses
  reported: { label: 'Reported', classes: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' },
  under_review: { label: 'Under Review', classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' },
  committee_review: { label: 'Committee Review', classes: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300' },
  action_plan_drafted: { label: 'Action Plan Drafted', classes: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300' },
  closed: { label: 'Closed', classes: 'bg-gray-100 text-gray-700 dark:bg-gray-700/40 dark:text-gray-300' },
  // Tracker
  on_track: { label: 'On Track', classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' },
  behind: { label: 'Behind', classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' },
  critical: { label: 'Critical', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' },
  // Pass/fail
  pass: { label: 'Pass', classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' },
  fail: { label: 'Fail', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' },
  overdue: { label: 'Overdue', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' },
}

interface Props {
  status: Status
  overrideLabel?: string
  className?: string
}

export function StatusBadge({ status, overrideLabel, className }: Props) {
  const config = STATUS_MAP[status] ?? {
    label: status.replace(/_/g, ' '),
    classes: 'bg-gray-100 text-gray-700 dark:bg-gray-700/40 dark:text-gray-300',
  }

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
        config.classes,
        className
      )}
    >
      {overrideLabel ?? config.label}
    </span>
  )
}
