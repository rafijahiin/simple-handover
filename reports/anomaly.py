"""
Anomaly detection for monthly submission counts using z-score method.
Requires scipy + numpy (already in requirements.txt).
"""
def detect_anomalies(monthly_counts: list[int], threshold: float = 2.0) -> list[dict]:
    """
    Given a list of monthly counts, return indices where the count is
    more than `threshold` standard deviations from the mean.

    Returns a list of dicts: {'index': int, 'value': int, 'z_score': float}
    Returns empty list if fewer than 3 data points.
    """
    if len(monthly_counts) < 3:
        return []

    # numpy+scipy stay lazy: this module is imported by reports/views.py at
    # boot, and a resident numpy costs every gunicorn worker ~45 MB of RAM
    # (87% of the Railway bill is memory-minutes).
    import numpy as np
    from scipy import stats

    arr = np.array(monthly_counts, dtype=float)
    z_scores = np.abs(stats.zscore(arr))

    anomalies = []
    for i, (value, z) in enumerate(zip(monthly_counts, z_scores)):
        if z > threshold:
            anomalies.append({
                'index': i,
                'value': int(value),
                'z_score': round(float(z), 2),
            })
    return anomalies


def submission_anomalies_for_partner(partner: str, form_type: str, year: int) -> list[dict]:
    """
    Fetch the 12 monthly approved submission counts for a partner/form_type/year
    and return any anomalous months.
    """
    from submissions.models import KoboSubmission, SubmissionStatus

    counts = []
    for month in range(1, 13):
        count = KoboSubmission.objects.filter(
            partner=partner,
            form_type=form_type,
            status=SubmissionStatus.APPROVED,
            submitted_at__year=year,
            submitted_at__month=month,
        ).count()
        counts.append(count)

    anomalies = detect_anomalies(counts)
    for a in anomalies:
        a['month'] = a['index'] + 1
        a['year'] = year
        a['partner'] = partner
        a['form_type'] = form_type
    return anomalies
