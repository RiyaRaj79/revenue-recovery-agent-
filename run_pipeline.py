"""
run_pipeline.py

Runs the complete Revenue Recovery Agent pipeline.

1. Generate synthetic customer/payment data.
2. Run standard dunning baseline.
3. Run adaptive recovery agent.
4. Build dashboard data.
"""

import json
import os
import subprocess
import sys


BACKEND_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

ROOT_DIR = os.path.dirname(
    BACKEND_DIR
)

DATA_DIR = os.path.join(
    ROOT_DIR,
    "data",
)

DASHBOARD_DIR = os.path.join(
    ROOT_DIR,
    "dashboard",
)


def run(command, cwd):
    print(
        f"\n$ {' '.join(command)}"
    )

    subprocess.run(
        command,
        cwd=cwd,
        check=True,
    )


def main():

    transactions_csv = os.path.join(
        DATA_DIR,
        "transactions.csv",
    )

    # Always regenerate so experiments are reproducible.
    run(
        [
            sys.executable,
            "generate_data.py",
            "1000",
        ],
        DATA_DIR,
    )

    run(
        [
            sys.executable,
            "baseline.py",
        ],
        BACKEND_DIR,
    )

    run(
        [
            sys.executable,
            "agent.py",
        ],
        BACKEND_DIR,
    )

    with open(
        os.path.join(
            BACKEND_DIR,
            "baseline_results.json",
        ),
        encoding="utf-8",
    ) as f:
        baseline = json.load(f)

    with open(
        os.path.join(
            BACKEND_DIR,
            "agent_results.json",
        ),
        encoding="utf-8",
    ) as f:
        agent = json.load(f)

    baseline_summary = baseline[
        "summary"
    ]

    agent_summary = agent[
        "summary"
    ]

    reasons = sorted(
        baseline_summary[
            "by_reason"
        ].keys()
    )

    by_reason = []

    for reason in reasons:

        b = baseline_summary[
            "by_reason"
        ][reason]

        a = agent_summary[
            "by_reason"
        ][reason]

        by_reason.append({
            "reason": reason,
            "label": reason.replace(
                "_",
                " ",
            ).title(),
            "baseline_rate": b[
                "recovery_rate"
            ],
            "agent_rate": a[
                "recovery_rate"
            ],
            "baseline_amount": b[
                "amount_recovered"
            ],
            "agent_amount": a[
                "amount_recovered"
            ],
        })

    # Highest-priority accounts first.
    feed = sorted(
        agent["transactions"],
        key=lambda x: x[
            "recovery_priority"
        ],
        reverse=True,
    )[:12]

    activity_feed = []

    for transaction in feed:

        activity_feed.append({
            "transaction_id": transaction[
                "transaction_id"
            ],
            "customer_id": transaction[
                "customer_id"
            ],
            "customer_name": transaction[
                "customer_name"
            ],
            "decline_reason": transaction[
                "decline_reason"
            ],
            "decline_message": transaction[
                "decline_message"
            ],
            "action_label": transaction[
                "action_label"
            ],
            "action_taken": transaction[
                "action_taken"
            ],
            "reasoning": transaction[
                "action_details"
            ].get(
                "reasoning",
                "",
            ),
            "recovered": transaction[
                "recovered"
            ],
            "amount_recovered": transaction[
                "amount_recovered"
            ],
            "plan_value": transaction[
                "plan_value"
            ],
            "recoverable_value": transaction[
                "recoverable_value"
            ],
            "recovery_priority": transaction[
                "recovery_priority"
            ],
            "churn_risk": transaction[
                "churn_risk"
            ],
            "decision_source": transaction[
                "decision_source"
            ],
        })

    improvement = 0

    if baseline_summary[
        "total_recovered"
    ]:

        improvement = (
            (
                agent_summary[
                    "total_recovered"
                ]
                -
                baseline_summary[
                    "total_recovered"
                ]
            )
            /
            baseline_summary[
                "total_recovered"
            ]
            * 100
        )

    dashboard_data = {
        "baseline_total_recovered":
            baseline_summary[
                "total_recovered"
            ],

        "agent_total_recovered":
            agent_summary[
                "total_recovered"
            ],

        "total_at_risk":
            baseline_summary[
                "total_at_risk"
            ],

        "baseline_recovery_rate":
            baseline_summary[
                "overall_recovery_rate"
            ],

        "agent_recovery_rate":
            agent_summary[
                "overall_recovery_rate"
            ],

        "improvement_pct":
            round(
                improvement,
                1,
            ),

        "action_match_rate":
            agent_summary[
                "action_match_rate"
            ],

        "net_recovered":
            agent_summary[
                "net_recovered"
            ],

        "total_action_cost":
            agent_summary[
                "total_action_cost"
            ],

        "average_priority_score":
            agent_summary[
                "average_priority_score"
            ],

        "average_churn_risk":
            agent_summary[
                "average_churn_risk"
            ],

        "transaction_count":
            agent_summary[
                "total_transactions"
            ],

        "by_reason":
            by_reason,

        "activity_feed":
            activity_feed,

        "top_priority_accounts":
            agent_summary[
                "top_priority_accounts"
            ],
    }

    os.makedirs(
        DASHBOARD_DIR,
        exist_ok=True,
    )

    output_path = os.path.join(
        DASHBOARD_DIR,
        "dashboard_data.json",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            dashboard_data,
            f,
            indent=2,
        )

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(
        f"Revenue at risk: "
        f"${dashboard_data['total_at_risk']:,.2f}"
    )

    print(
        f"Baseline recovered: "
        f"${dashboard_data['baseline_total_recovered']:,.2f}"
    )

    print(
        f"Agent recovered: "
        f"${dashboard_data['agent_total_recovered']:,.2f}"
    )

    print(
        f"Improvement: "
        f"+{dashboard_data['improvement_pct']}%"
    )

    print(
        f"Action match rate: "
        f"{dashboard_data['action_match_rate'] * 100:.1f}%"
    )

    print(
        f"Average priority: "
        f"{dashboard_data['average_priority_score']:.1f}"
    )

    print(
        f"Dashboard written to: "
        f"{output_path}"
    )


if __name__ == "__main__":
    main()