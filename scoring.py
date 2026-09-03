"""
scoring.py

Shared scoring and evaluation logic for the revenue recovery system.

IMPORTANT:
All recovery outcomes in this project are simulated.
They should never be presented as production payment results.
"""

RECOVERY_RATES = {
    "expired_card": {
        "baseline": 0.34,
        "agent": 0.68,
    },
    "insufficient_funds": {
        "baseline": 0.21,
        "agent": 0.38,
    },
    "fraud_flag": {
        "baseline": 0.15,
        "agent": 0.52,
    },
    "network_error": {
        "baseline": 0.55,
        "agent": 0.80,
    },
}

IDEAL_ACTION = {
    "expired_card": "request_card_update",
    "insufficient_funds": "schedule_retry",
    "fraud_flag": "send_email",
    "network_error": "schedule_retry",
}

ACTION_LABELS = {
    "schedule_retry": "Retry scheduled",
    "send_email": "Personalized email sent",
    "send_sms": "SMS sent",
    "offer_discount": "Retention discount offered",
    "request_card_update": "Card-update request sent",
    "escalate_to_human": "Escalated to billing specialist",
}

ACTION_COSTS = {
    "schedule_retry": 0.20,
    "send_email": 0.05,
    "send_sms": 0.08,
    "offer_discount": 5.00,
    "request_card_update": 0.05,
    "escalate_to_human": 8.00,
}


def ltv_multiplier(tenure_months):
    """
    Approximate customer value multiplier.

    This is a synthetic scoring assumption, not a financial model.
    """
    return round(
        min(1.0 + tenure_months / 24.0, 3.0),
        2,
    )


def recoverable_value(plan_value, tenure_months):
    """
    Estimate revenue at risk using plan value and tenure.
    """
    return round(
        plan_value * ltv_multiplier(tenure_months),
        2,
    )


def customer_value_score(plan_value, tenure_months):
    """
    Normalize customer value to approximately 0-100.
    """
    value = recoverable_value(
        plan_value,
        tenure_months,
    )

    score = min(
        100,
        (value / 1500.0) * 100,
    )

    return round(score, 1)


def churn_risk_score(
    previous_failures,
    previous_recovery_attempts,
    decline_reason,
):
    """
    Synthetic churn-risk score.

    Higher repeated failures and fraud-related issues increase risk.
    """
    score = 15

    score += min(previous_failures * 8, 35)
    score += min(previous_recovery_attempts * 6, 24)

    if decline_reason == "fraud_flag":
        score += 15

    if decline_reason == "expired_card":
        score += 8

    if decline_reason == "insufficient_funds":
        score += 5

    return round(min(score, 100), 1)


def urgency_score(decline_reason):
    """
    How urgently the account needs intervention.
    """
    values = {
        "expired_card": 75,
        "insufficient_funds": 55,
        "fraud_flag": 90,
        "network_error": 35,
    }

    return values.get(decline_reason, 50)


def recovery_priority_score(
    plan_value,
    tenure_months,
    previous_failures,
    previous_recovery_attempts,
    decline_reason,
):
    """
    Overall account priority.

    40% = revenue at risk
    30% = churn risk
    20% = urgency
    10% = previous failure history
    """

    value_score = customer_value_score(
        plan_value,
        tenure_months,
    )

    churn_score = churn_risk_score(
        previous_failures,
        previous_recovery_attempts,
        decline_reason,
    )

    urgency = urgency_score(decline_reason)

    history_score = min(
        100,
        previous_failures * 15
        + previous_recovery_attempts * 10,
    )

    score = (
        value_score * 0.40
        + churn_score * 0.30
        + urgency * 0.20
        + history_score * 0.10
    )

    return round(min(score, 100), 1)


def baseline_probability(reason):
    return RECOVERY_RATES[reason]["baseline"]


def agent_probability(reason, action_taken):
    """
    Simulated probability used by the evaluation environment.

    A correct action gets the reason-specific agent rate.

    A wrong action gets baseline performance.

    Escalation intentionally has a lower immediate recovery rate because
    human review is slower, but it can be the safer decision for risky cases.
    """

    if action_taken == IDEAL_ACTION.get(reason):
        return RECOVERY_RATES[reason]["agent"]

    if action_taken == "escalate_to_human":
        return min(
            RECOVERY_RATES[reason]["baseline"] + 0.08,
            0.70,
        )

    return RECOVERY_RATES[reason]["baseline"]


def action_is_reasonable(reason, action):
    """
    Whether an action is semantically reasonable for a failure.
    """

    reasonable = {
        "expired_card": {
            "request_card_update",
        },
        "insufficient_funds": {
            "schedule_retry",
            "send_sms",
        },
        "fraud_flag": {
            "send_email",
            "escalate_to_human",
        },
        "network_error": {
            "schedule_retry",
        },
    }

    return action in reasonable.get(reason, set())


def action_cost(action):
    return ACTION_COSTS.get(action, 0.0)


def expected_net_revenue(
    plan_value,
    probability,
    action,
):
    """
    Expected recovered revenue minus action cost.
    """
    return round(
        plan_value * probability - action_cost(action),
        2,
    )