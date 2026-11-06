"""
Simple linear-trend forecasting for monthly submission counts.
Uses numpy least-squares fit over the last N months to project future months.
"""
def linear_forecast(monthly_counts: list[int], periods_ahead: int = 3) -> list[float]:
    """
    Given a list of monthly counts (oldest first), return `periods_ahead` forecasted values.
    Returns zeros if there are fewer than 2 data points.
    """
    n = len(monthly_counts)
    if n < 2:
        return [0.0] * periods_ahead

    # Lazy: tracker/views.py imports this module at boot; keeping numpy out
    # of the boot path keeps it out of the worker's resident memory.
    import numpy as np

    x = np.arange(n, dtype=float)
    y = np.array(monthly_counts, dtype=float)

    # Least-squares linear fit: y = slope * x + intercept
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = coeffs

    forecasts = []
    for i in range(1, periods_ahead + 1):
        value = slope * (n - 1 + i) + intercept
        forecasts.append(max(0.0, round(float(value), 1)))
    return forecasts


def attainment_percent(actual: int, target: int) -> float | None:
    """Return actual/target as a percentage, or None if target is zero."""
    if target <= 0:
        return None
    return round(actual / target * 100, 1)
