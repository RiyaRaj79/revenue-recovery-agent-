"""
baseline.py

Simulates a conventional fixed dunning strategy.

The baseline does not adapt to:
- customer value
- customer history
- decline type
- churn risk

It simply attempts a retry and generic outreach.
"""

import csv
import json
import random

from scoring import (
    baseline_probability,
    recoverable_value,
)

random.seed(7)


def run_baseline(
    transactions_path="../data/transactions.csv",
):
    results = []

    with open(
        transactions_path,
        encoding="utf-8",
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:
            reason = row["decline_reason"]
            plan_value = float(row["plan_value"])
            tenure = int(row["tenure_months"])

            probability = baseline_probability(reason)

            recovered = random.random() < probability

            results.append({
                "transaction_id": row["transaction_id"],
                "customer_id": row["customer_id"],
                "decline_reason": reason,
                "plan_value": plan_value,
                "recoverable_value": recoverable_value(
                    plan_value,
                    tenure,
                ),
                "recovery_probability": probability,
                "recovered": recovered,
                "amount_recovered": (
                    round(plan_value, 2)
                    if recovered
                    else 0.0
                ),
                "action_taken": "standard_dunning",
            })

    return results


def summarize(results):
    total_at_risk = sum(
        r["plan_value"]
        for r in results
    )

    total_recovered = sum(
        r["amount_recovered"]
        for r in results
    )

    by_reason = {}

    for result in results:
        reason = result["decline_reason"]

        bucket = by_reason.setdefault(
            reason,
            {
                "attempted": 0,
                "recovered": 0,
                "amount_recovered": 0.0,
            },
        )

        bucket["attempted"] += 1

        if result["recovered"]:
            bucket["recovered"] += 1

        bucket["amount_recovered"] += (
            result["amount_recovered"]
        )

    for bucket in by_reason.values():
        bucket["recovery_rate"] = round(
            bucket["recovered"]
            / bucket["attempted"],
            3,
        )

        bucket["amount_recovered"] = round(
            bucket["amount_recovered"],
            2,
        )

    return {
        "total_transactions": len(results),
        "total_at_risk": round(
            total_at_risk,
            2,
        ),
        "total_recovered": round(
            total_recovered,
            2,
        ),
        "overall_recovery_rate": round(
            total_recovered / total_at_risk,
            3,
        ) if total_at_risk else 0,
        "by_reason": by_reason,
    }


def main():
    results = run_baseline()

    summary = summarize(results)

    output = {
        "summary": summary,
        "transactions": results,
    }

    with open(
        "baseline_results.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
        )

    print(
        f"Baseline recovered "
        f"${summary['total_recovered']:,.2f} "
        f"of ${summary['total_at_risk']:,.2f} "
        f"at risk "
        f"({summary['overall_recovery_rate'] * 100:.1f}%)"
    )


if __name__ == "__main__":
    main()