"""Editable target function for optimization experiments."""

from __future__ import annotations

from typing import Any, Tuple
from datetime import date


def months_rounded_up(date_start: date, date_end: date) -> int:
    year_diff = date_end.year - date_start.year
    month_diff = date_end.month - date_start.month
    total_months = (year_diff * 12) + month_diff

    if date_end.day > date_start.day:
        total_months += 1

    return max(1, total_months)


def candidate_portfolio_return_gross_net(
    date_start: date,
    date_end: date,
    profit_loss_ptd: float,
    profit_loss_ytd: float,
    fees_ptd: float,
    nav_begin: float,
    nav_end: float,
    subscriptions: float,
    redemptions: float,
) -> tuple[float, float]:
    """Calculates the gross and net returns for a portfolio over a specific period.

    This function adjusts the NAV denominator based on the start year and 
    accounts for management and performance fees to arrive at a net return.

    Args:
        date_start (date): The start date of the period.
        date_end (date): The end date of the period.
        profit_loss_ptd (float): Profit and Loss for the Period to Date (Net of fees).
        profit_loss_ytd (float): Profit and Loss for the Year to Date.
        fees_ptd (float): Total fees paid during the period.
        nav_begin (float): Net Asset Value at the start of the period.
        nav_end (float): Net Asset Value at the end of the period.
        subscriptions (float): Capital inflows during the period.
        redemptions (float): Capital outflows during the period.

    Returns:
        Tuple[float, float]: A tuple containing (return_gross, return_net).
            - return_gross: The portfolio return before fees.
            - return_net: The portfolio return after management and performance fees.

    Note:
    - management fees are calculated as a percentage of the ending NAV, pro-rated for the time period (number of months).
    - performance fees are calculated as a percentage of the gross profit if the year-to-date profit is positive. 
    - When year-to-date gross profit and loss after management fees is negative, the portfolio is considered under high water mark ("HWM"). 
    - Performance fees are only charged on profits above the high water mark, meaning that if the portfolio is in a loss position, no performance fees are charged until the losses are recovered and the portfolio returns to a profit position.
    - returns are either positive, negative, or zero, and rounded to 5 decimal places.
    
    The current implementation follows the finance-shaped scenario contract in
    `scenarios/scenarios.json`. It is intentionally self-contained and CPU-only.
    """

    YEAR_FEE_FREE_SERIES_START = 2025
    MANAGEMENT_FEE_RATE = 0.015
    PERFORMANCE_FEE_RATE = 0.2

    profit_loss_ptd_gross = profit_loss_ptd + fees_ptd
    profit_loss_ytd_gross = profit_loss_ytd + fees_ptd

    if date_start.year < YEAR_FEE_FREE_SERIES_START:
        nav_denominator = nav_begin + subscriptions
    else:
        nav_denominator = nav_end + profit_loss_ptd + redemptions

    if nav_denominator == 0:
        raise ValueError("nav denominator must be non-zero")

    return_gross = profit_loss_ptd_gross / nav_denominator

    management_fee_ptd = nav_end * MANAGEMENT_FEE_RATE * (months_rounded_up(date_start, date_end) / 12)
    performance_fee_ptd = 0.0

    if profit_loss_ytd_gross > 0:
        performance_fee_ptd = PERFORMANCE_FEE_RATE * profit_loss_ptd_gross

    profit_loss_ptd_net = profit_loss_ptd_gross - management_fee_ptd - performance_fee_ptd
    return_net = profit_loss_ptd_net / nav_denominator

    return round(return_gross, 5), round(return_net, 5)
