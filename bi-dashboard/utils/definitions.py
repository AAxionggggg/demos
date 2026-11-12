"""Definitions behind the certified metrics and charts of the Nimbus BI demo.

Cards show them in their "What's measured" and "SQL query" menu items, and
section headers show the section's query in a popover. The SQL describes the
warehouse model the synthetic data in ``utils/data.py`` stands in for.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Definition:
    title: str
    measures: str
    sql: str
    owner: str = "Revenue operations"
    refresh: str = "Hourly"


DEFINITIONS = {
    "revenue": Definition(
        "Revenue KPIs",
        "Recurring revenue, retention, and churn of active subscriptions.",
        """\
SELECT month,
       SUM(mrr) * 12 AS arr,
       SUM(mrr) - LAG(SUM(mrr)) OVER (ORDER BY month) AS net_new_mrr
FROM revenue.mrr_monthly
WHERE region IN (:regions) AND plan IN (:plans)
GROUP BY month
ORDER BY month""",
    ),
    "arr": Definition(
        "Annual recurring revenue",
        "Monthly recurring revenue of all active subscriptions, times 12.",
        """\
SELECT month, SUM(mrr) * 12 AS arr
FROM revenue.mrr_monthly
GROUP BY month""",
    ),
    "net_new_mrr": Definition(
        "Net new MRR",
        "New plus expansion MRR, minus contraction and churned MRR, in the month.",
        """\
SELECT month, SUM(mrr) - LAG(SUM(mrr)) OVER (ORDER BY month) AS net_new_mrr
FROM revenue.mrr_monthly
GROUP BY month""",
    ),
    "nrr": Definition(
        "Net revenue retention",
        "MRR today from customers active 12 months ago, divided by their MRR back then.",
        """\
SELECT cur.month, SUM(cur.mrr) / SUM(prev.mrr) AS nrr
FROM revenue.mrr_monthly AS cur
JOIN revenue.mrr_monthly AS prev
  ON prev.account_id = cur.account_id
 AND prev.month = DATEADD(month, -12, cur.month)
WHERE prev.mrr > 0
GROUP BY cur.month""",
    ),
    "gross_churn": Definition(
        "Monthly gross churn",
        "Churned plus contracted MRR as a share of the previous month's MRR.",
        """\
SELECT month, SUM(churned_mrr + contraction_mrr) / SUM(prev_mrr) AS gross_churn
FROM revenue.mrr_movements
GROUP BY month""",
    ),
    "mrr_by_plan": Definition(
        "MRR by plan",
        "Monthly recurring revenue of active subscriptions, split by plan. The "
        "forecast extends each plan by its average growth over the last six months.",
        """\
SELECT month, plan, SUM(mrr) AS mrr
FROM revenue.mrr_monthly
WHERE region IN (:regions)
GROUP BY month, plan
ORDER BY month""",
    ),
    "mrr_bridge": Definition(
        "MRR bridge",
        "How MRR moved between the start and the end of the period: new customers, "
        "expansion, contraction, and churn.",
        """\
SELECT movement, SUM(mrr_change) AS mrr_change
FROM revenue.mrr_movements
WHERE month BETWEEN :period_start AND :period_end
GROUP BY movement""",
    ),
    "usage": Definition(
        "Product sessions",
        "Signed-in product sessions by weekday and hour, in UTC.",
        """\
SELECT DAYOFWEEK(started_at) AS weekday,
       HOUR(started_at) AS hour,
       COUNT(*) AS sessions
FROM product.sessions
WHERE region IN (:regions)
GROUP BY weekday, hour""",
        owner="Product analytics",
    ),
    "industry_mix": Definition(
        "Revenue by industry",
        "Current MRR of active customers, grouped by their industry.",
        """\
SELECT industry, SUM(mrr) AS mrr
FROM revenue.accounts
WHERE mrr > 0
GROUP BY industry""",
    ),
    "accounts": Definition(
        "Customer accounts",
        "Every customer account with its plan, MRR, health score, and renewal date.",
        """\
SELECT account_id, name, plan, region, industry, mrr, seats,
       health_score, status, owner, renewal_date
FROM revenue.accounts
WHERE region IN (:regions) AND plan IN (:plans)""",
        owner="Customer success",
    ),
    "health_scatter": Definition(
        "Health vs. revenue",
        "Each account's health score (0 to 100, from product usage, support "
        "tickets, and NPS) against its current MRR.",
        """\
SELECT account_id, health_score, mrr, seats, plan
FROM revenue.accounts
WHERE mrr > 0""",
        owner="Customer success",
        refresh="Daily",
    ),
    "pipeline": Definition(
        "Pipeline KPIs",
        "Open and closed sales opportunities from the CRM.",
        """\
SELECT stage, COUNT(*) AS deals, SUM(amount) AS amount,
       SUM(amount * stage_probability) AS weighted
FROM sales.opportunities
WHERE region IN (:regions) AND plan IN (:plans)
GROUP BY stage""",
        owner="Sales operations",
        refresh="Every 15 minutes",
    ),
    "bookings": Definition(
        "Bookings by month",
        "Value of closed-won deals by close month. The current month is "
        "projected from its pace so far.",
        """\
SELECT DATE_TRUNC(month, close_date) AS month, SUM(amount) AS bookings
FROM sales.opportunities
WHERE stage = 'Closed won'
GROUP BY month
ORDER BY month""",
        owner="Sales operations",
        refresh="Every 15 minutes",
    ),
    "quota": Definition(
        "Quarter bookings",
        "Closed-won value this quarter against quota. Quota is the trailing "
        "average quarterly bookings plus 15%.",
        """\
SELECT SUM(amount) AS bookings
FROM sales.opportunities
WHERE stage = 'Closed won'
  AND close_date >= DATE_TRUNC(quarter, CURRENT_DATE)""",
        owner="Sales operations",
        refresh="Every 15 minutes",
    ),
    "pipeline_flow": Definition(
        "Pipeline flow",
        "Deal value from lead source, through plan, to its outcome: won, lost, or still open.",
        """\
SELECT source, plan,
       CASE stage WHEN 'Closed won' THEN 'Won'
                  WHEN 'Closed lost' THEN 'Lost'
                  ELSE 'Open' END AS outcome,
       SUM(amount) AS amount
FROM sales.opportunities
GROUP BY source, plan, outcome""",
        owner="Sales operations",
        refresh="Every 15 minutes",
    ),
    "stage_funnel": Definition(
        "Stage conversion",
        "Number of deals that reached each sales stage. Lost deals count as "
        "having reached the proposal stage.",
        """\
SELECT stage_reached, COUNT(*) AS deals
FROM sales.opportunity_stage_history
GROUP BY stage_reached""",
        owner="Sales operations",
        refresh="Every 15 minutes",
    ),
}
