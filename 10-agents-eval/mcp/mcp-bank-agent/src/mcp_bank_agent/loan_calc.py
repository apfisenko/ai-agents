from __future__ import annotations


def annuity_monthly_payment(
    principal: float,
    annual_rate_percent: float,
    term_months: int,
) -> tuple[float, float, float]:
    """Равномерный (аннуитетный) ежемесячный платёж и итоги.

    Формула: M = K * [r*(1+r)^n] / [(1+r)^n - 1], где r — месячная ставка.
    При нулевой ставке M = K / n.

    Returns:
        (monthly_payment, total_to_pay, overpayment_over_principal)
    """
    if principal <= 0:
        raise ValueError("principal must be positive")
    if term_months <= 0:
        raise ValueError("term_months must be positive")

    monthly_rate = annual_rate_percent / 100.0 / 12.0
    if monthly_rate <= 0:
        monthly = principal / float(term_months)
    else:
        pow_term = (1.0 + monthly_rate) ** term_months
        monthly = principal * (monthly_rate * pow_term) / (pow_term - 1.0)

    total = monthly * term_months
    overpayment = total - principal
    return monthly, total, overpayment
