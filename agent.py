"""
agent.py

Revenue Recovery Agent.

The agent:
1. Reads raw payment information.
2. Considers customer history and value.
3. Selects one recovery action.
4. Explains the decision.
5. Calculates recovery priority.
6. Simulates an outcome for evaluation.

All payment outcomes are synthetic.
"""

import csv
import json
import os
import random

from scoring import (
    agent_probability,
    recoverable_value,
    recovery_priority_score,
    churn_risk_score,
    ACTION_LABELS,
    IDEAL_ACTION,
    action_cost,
    expected_net_revenue,
)

random.seed(11)

MAX_LIVE_CALLS = int(
    os.environ.get(
        "MAX_LIVE_CALLS",
        "50",
    )
)

API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY"
)


TOOLS = [
    {
        "name": "schedule_retry",
        "description": (
            "Schedule another payment attempt. "
            "Best for temporary issues such as insufficient funds "
            "or network/issuer availability problems."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "delay_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 14,
                },
                "reasoning": {
                    "type": "string",
                },
            },
            "required": [
                "delay_days",
                "reasoning",
            ],
        },
    },

    {
        "name": "send_email",
        "description": (
            "Send a personalized email explaining the payment issue "
            "and the next step."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tone": {
                    "type": "string",
                    "enum": [
                        "reassuring",
                        "urgent",
                        "friendly_reminder",
                    ],
                },
                "reasoning": {
                    "type": "string",
                },
            },
            "required": [
                "tone",
                "reasoning",
            ],
        },
    },

    {
        "name": "send_sms",
        "description": (
            "Send a concise SMS reminder when the customer needs "
            "a quick low-friction action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                },
            },
            "required": [
                "reasoning",
            ],
        },
    },

    {
        "name": "offer_discount",
        "description": (
            "Offer a temporary retention discount. "
            "Use sparingly for valuable customers at elevated churn risk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "percent_off": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 25,
                },
                "reasoning": {
                    "type": "string",
                },
            },
            "required": [
                "percent_off",
                "reasoning",
            ],
        },
    },

    {
        "name": "request_card_update",
        "description": (
            "Ask the customer to update their payment card. "
            "Best when the payment instrument is expired or invalid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                },
            },
            "required": [
                "reasoning",
            ],
        },
    },

    {
        "name": "escalate_to_human",
        "description": (
            "Escalate the account to a billing specialist. "
            "Use when the issue is risky, repeated, ambiguous, "
            "or should not be handled automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                },
            },
            "required": [
                "reasoning",
            ],
        },
    },
]


SYSTEM_PROMPT = """
You are an autonomous revenue recovery agent for a subscription business.

Your goal is to recover legitimate revenue while minimizing unnecessary
customer friction and avoiding inappropriate actions.

You will receive:
- the raw payment processor message
- customer value
- tenure
- previous payment history
- previous recovery attempts
- previous communication response

IMPORTANT:
Do not assume that the raw payment message has already been classified.
Infer the likely payment problem yourself.

Choose EXACTLY ONE tool.

Decision principles:
1. Match the action to the actual payment problem.
2. Consider customer history, not just the current failure.
3. Avoid repeated retries when they are unlikely to work.
4. Protect high-value customers from unnecessary churn.
5. Escalate when automatic recovery is inappropriate.
6. Do not offer discounts unless the retention value justifies them.
7. Give a concise explanation for your choice.
"""


def _client():
    import anthropic

    return anthropic.Anthropic(
        api_key=API_KEY
    )


def decide_action_live(client, txn):
    prompt = f"""
PAYMENT EVENT

Raw decline message:
"{txn['decline_message']}"

Customer:
- Plan: {txn['plan_tier']}
- Monthly value: ${txn['plan_value']}
- Tenure: {txn['tenure_months']} months
- Payment method: {txn['payment_method']}

History:
- Previous successful payments: {txn['previous_successes']}
- Previous failed payments: {txn['previous_failures']}
- Previous recovery attempts: {txn['previous_recovery_attempts']}
- Days since last successful payment: {txn['days_since_last_payment']}

Previous communication:
- Channel: {txn['previous_contact_channel']}
- Response: {txn['previous_contact_response']}

Choose the single best action.
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_choice={
            "type": "any"
        },
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use":
            return (
                block.name,
                block.input,
            )

    return (
        "schedule_retry",
        {
            "delay_days": 3,
            "reasoning": (
                "Temporary recovery attempt selected "
                "because no specific tool decision was returned."
            ),
        },
    )


def decide_action_mock(txn):
    """
    Deterministic intelligent fallback.

    This is intentionally NOT given the final answer by the dataset.
    It uses the raw message + customer context just like the live agent.
    """

    message = txn["decline_message"].lower()

    plan_value = float(
        txn["plan_value"]
    )

    tenure = int(
        txn["tenure_months"]
    )

    failures = int(
        txn["previous_failures"]
    )

    attempts = int(
        txn["previous_recovery_attempts"]
    )

    # High-risk repeated customers should be escalated.
    if (
        failures >= 4
        and attempts >= 3
        and plan_value >= 149
    ):
        return (
            "escalate_to_human",
            {
                "reasoning": (
                    "Repeated payment failures on a high-value account "
                    "make human review preferable to repeated automation."
                )
            },
        )

    # Expired / invalid card.
    if (
        "expired" in message
        or "expiration" in message
        or "code 54" in message
    ):
        return (
            "request_card_update",
            {
                "reasoning": (
                    "The payment instrument appears expired, "
                    "so requesting updated card details is more useful "
                    "than retrying the same card."
                )
            },
        )

    # Insufficient funds.
    if (
        "insufficient" in message
        or "low account balance" in message
        or "code 51" in message
        or "available balance" in message
    ):
        if (
            txn["previous_contact_response"] == "responded"
            or txn["previous_contact_response"] == "clicked"
        ):
            return (
                "schedule_retry",
                {
                    "delay_days": 3,
                    "reasoning": (
                        "The issue appears temporary and the customer "
                        "has previously engaged, so a delayed retry is appropriate."
                    ),
                },
            )

        return (
            "schedule_retry",
            {
                "delay_days": 5,
                "reasoning": (
                    "Insufficient funds usually represent a temporary "
                    "balance issue, so retrying later avoids unnecessary friction."
                ),
            },
        )

    # Fraud / manual review.
    if (
        "fraud" in message
        or "manual review" in message
        or "code 59" in message
        or "verification" in message
    ):
        if plan_value >= 149 and tenure >= 12:
            return (
                "send_email",
                {
                    "tone": "reassuring",
                    "reasoning": (
                        "The issuer flagged the transaction, so a reassuring "
                        "message provides context before another payment attempt."
                    ),
                },
            )

        return (
            "send_email",
            {
                "tone": "reassuring",
                "reasoning": (
                    "The payment was flagged by the issuer, so customer "
                    "communication should come before another charge attempt."
                ),
            },
        )

    # Network / issuer unavailable.
    if (
        "timeout" in message
        or "network" in message
        or "unavailable" in message
        or "code 91" in message
    ):
        return (
            "schedule_retry",
            {
                "delay_days": 1,
                "reasoning": (
                    "The processor indicates a temporary availability issue, "
                    "so retrying shortly is appropriate."
                ),
            },
        )

    # Fallback based on customer value.
    if plan_value >= 149 and tenure >= 24:
        return (
            "send_email",
            {
                "tone": "friendly_reminder",
                "reasoning": (
                    "The account has meaningful customer value, "
                    "so a low-friction personalized intervention is preferred."
                ),
            },
        )

    return (
        "send_sms",
        {
            "reasoning": (
                "A short low-friction reminder is appropriate "
                "when the payment problem is ambiguous."
            ),
        },
    )


def main():
    with open(
        "transactions.csv",
        encoding="utf-8",
    ) as f:

        transactions = list(
            csv.DictReader(f)
        )

    live_mode = API_KEY is not None

    client = (
        _client()
        if live_mode
        else None
    )

    live_calls_used = 0

    if live_mode:
        print(
            "Claude API enabled. "
            f"Using live calls for up to {MAX_LIVE_CALLS} transactions."
        )
    else:
        print(
            "No ANTHROPIC_API_KEY found. "
            "Using the local intelligent fallback agent."
        )

    results = []

    for row in transactions:

        plan_value = float(
            row["plan_value"]
        )

        tenure = int(
            row["tenure_months"]
        )

        failures = int(
            row["previous_failures"]
        )

        attempts = int(
            row["previous_recovery_attempts"]
        )

        priority = recovery_priority_score(
            plan_value,
            tenure,
            failures,
            attempts,
            row["decline_reason"],
        )

        churn_risk = churn_risk_score(
            failures,
            attempts,
            row["decline_reason"],
        )

        use_live = (
            live_mode
            and live_calls_used < MAX_LIVE_CALLS
        )

        if use_live:
            try:
                action, inputs = decide_action_live(
                    client,
                    row,
                )

                live_calls_used += 1
                source = "claude"

            except Exception as error:
                print(
                    f"Live call failed for "
                    f"{row['transaction_id']}: {error}"
                )

                action, inputs = decide_action_mock(
                    row
                )

                source = "local_fallback"

        else:
            action, inputs = decide_action_mock(
                row
            )

            source = "local_agent"

        probability = agent_probability(
            row["decline_reason"],
            action,
        )

        recovered = (
            random.random()
            < probability
        )

        amount_recovered = (
            round(plan_value, 2)
            if recovered
            else 0.0
        )

        matched_ideal = (
            action
            == IDEAL_ACTION.get(
                row["decline_reason"]
            )
        )

        results.append({
            "transaction_id": row["transaction_id"],
            "customer_id": row["customer_id"],
            "customer_name": row["customer_name"],
            "decline_reason": row["decline_reason"],
            "decline_message": row["decline_message"],
            "plan_tier": row["plan_tier"],
            "plan_value": plan_value,
            "tenure_months": tenure,
            "previous_successes": int(
                row["previous_successes"]
            ),
            "previous_failures": failures,
            "previous_recovery_attempts": attempts,
            "days_since_last_payment": int(
                row["days_since_last_payment"]
            ),
            "payment_method": row["payment_method"],
            "previous_contact_channel": row[
                "previous_contact_channel"
            ],
            "previous_contact_response": row[
                "previous_contact_response"
            ],
            "recoverable_value": recoverable_value(
                plan_value,
                tenure,
            ),
            "recovery_priority": priority,
            "churn_risk": churn_risk,
            "action_taken": action,
            "action_label": ACTION_LABELS.get(
                action,
                action,
            ),
            "action_details": inputs,
            "matched_ideal_action": matched_ideal,
            "decision_source": source,
            "recovery_probability": probability,
            "action_cost": action_cost(action),
            "expected_net_revenue": expected_net_revenue(
                plan_value,
                probability,
                action,
            ),
            "recovered": recovered,
            "amount_recovered": amount_recovered,
            "timestamp": row["timestamp"],
        })

    summary = summarize(
        results
    )

    output = {
        "summary": summary,
        "transactions": results,
    }

    with open(
        "agent_results.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
        )

    print(
        f"\nAgent recovered "
        f"${summary['total_recovered']:,.2f}"
        f" / "
        f"${summary['total_at_risk']:,.2f}"
        f" at risk"
    )

    print(
        f"Recovery rate: "
        f"{summary['overall_recovery_rate'] * 100:.1f}%"
    )

    print(
        f"Ideal-action match: "
        f"{summary['action_match_rate'] * 100:.1f}%"
    )

    print(
        f"Average priority score: "
        f"{summary['average_priority_score']:.1f}"
    )


def summarize(results):
    total_at_risk = sum(
        r["plan_value"]
        for r in results
    )

    total_recovered = sum(
        r["amount_recovered"]
        for r in results
    )

    matched = sum(
        1
        for r in results
        if r["matched_ideal_action"]
    )

    total_cost = sum(
        r["action_cost"]
        for r in results
    )

    by_reason = {}

    for result in results:

        reason = result[
            "decline_reason"
        ]

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

        bucket[
            "amount_recovered"
        ] += result[
            "amount_recovered"
        ]

    for bucket in by_reason.values():

        bucket["recovery_rate"] = round(
            bucket["recovered"]
            / bucket["attempted"],
            3,
        )

        bucket[
            "amount_recovered"
        ] = round(
            bucket["amount_recovered"],
            2,
        )

    top_priority = sorted(
        results,
        key=lambda x: x[
            "recovery_priority"
        ],
        reverse=True,
    )[:10]

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
        "total_action_cost": round(
            total_cost,
            2,
        ),
        "net_recovered": round(
            total_recovered - total_cost,
            2,
        ),
        "overall_recovery_rate": round(
            total_recovered
            / total_at_risk,
            3,
        ) if total_at_risk else 0,
        "action_match_rate": round(
            matched / len(results),
            3,
        ) if results else 0,
        "average_priority_score": round(
            sum(
                r["recovery_priority"]
                for r in results
            )
            / len(results),
            1,
        ) if results else 0,
        "average_churn_risk": round(
            sum(
                r["churn_risk"]
                for r in results
            )
            / len(results),
            1,
        ) if results else 0,
        "by_reason": by_reason,
        "top_priority_accounts": top_priority,
    }


if __name__ == "__main__":
    main()