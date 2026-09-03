"""
generate_data.py

Generates a synthetic SaaS failed-payment dataset with realistic
customer history.

Each customer can have multiple payment events, allowing the
revenue recovery agent to use historical behavior when deciding
what action to take.

This is SYNTHETIC data for demonstration/evaluation only.
"""

import csv
import random
import sys
from datetime import datetime, timedelta, timezone

random.seed(42)

DECLINE_REASONS = {
    "expired_card": 0.27,
    "insufficient_funds": 0.36,
    "fraud_flag": 0.14,
    "network_error": 0.23,
}

DECLINE_MESSAGES = {
    "expired_card": [
        "Card expiration date does not match records on file.",
        "Your card ending in {last4} has expired.",
        "Decline code 54: expired card.",
        "Issuer rejected payment because the card has expired.",
    ],
    "insufficient_funds": [
        "Payment declined: insufficient funds available.",
        "Decline code 51: not sufficient funds.",
        "Your bank declined the charge due to low account balance.",
        "Issuer reported insufficient available balance.",
    ],
    "fraud_flag": [
        "Transaction flagged for manual review by issuing bank.",
        "Decline code 59: suspected fraud.",
        "Card issuer blocked this charge as a suspected fraud risk.",
        "Issuer requires additional verification before approving this payment.",
    ],
    "network_error": [
        "Payment gateway timeout, no response from processor.",
        "Decline code 91: issuer unavailable.",
        "Temporary network error while processing your card.",
        "Payment processor returned a temporary issuer-unavailable response.",
    ],
}

PLAN_TIERS = [
    ("Starter", 19),
    ("Growth", 49),
    ("Scale", 149),
    ("Enterprise", 499),
]

PAYMENT_METHODS = [
    "visa",
    "mastercard",
    "amex",
    "debit_card",
]

CHANNELS = [
    "email",
    "sms",
    "email",
    "email",
    "none",
]

FIRST_NAMES = [
    "Alex", "Priya", "Jordan", "Mei", "Sam", "Nina",
    "Diego", "Owen", "Fatima", "Leo", "Grace", "Kenji",
    "Ines", "Marcus", "Yara", "Theo"
]

LAST_NAMES = [
    "Rao", "Chen", "Novak", "Silva", "Okafor", "Kim",
    "Petrov", "Diaz", "Nguyen", "Haas", "Ito", "Brooks",
    "Vargas", "Lund", "Osei", "Park"
]


def make_customer(customer_number):
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    tier, price = random.choice(PLAN_TIERS)

    tenure_months = random.choices(
        population=[2, 4, 6, 12, 18, 24, 36, 48, 60],
        weights=[8, 10, 12, 18, 15, 12, 10, 4, 1],
    )[0]

    previous_successes = max(
        1,
        int(tenure_months * random.uniform(0.6, 1.0))
    )

    previous_failures = random.choices(
        population=[0, 1, 2, 3, 4, 5],
        weights=[40, 30, 15, 8, 5, 2],
    )[0]

    return {
        "customer_id": f"CUST-{1000 + customer_number}",
        "customer_name": name,
        "plan_tier": tier,
        "plan_value": price,
        "tenure_months": tenure_months,
        "payment_method": random.choice(PAYMENT_METHODS),
        "previous_successes": previous_successes,
        "previous_failures": previous_failures,
    }


def make_transaction(transaction_number, customer, event_number):
    reason = random.choices(
        population=list(DECLINE_REASONS.keys()),
        weights=list(DECLINE_REASONS.values()),
    )[0]

    message = random.choice(
        DECLINE_MESSAGES[reason]
    ).format(last4=random.randint(1000, 9999))

    # Small random variation in account history for each event.
    previous_attempts = customer["previous_failures"] + event_number

    days_since_last_payment = random.randint(1, 45)

    last_successful_payment = (
        datetime.now(timezone.utc)
        - timedelta(days=days_since_last_payment)
    ).isoformat(timespec="seconds")

    days_ago = random.randint(0, 29)

    timestamp = (
        datetime.now(timezone.utc)
        - timedelta(
            days=days_ago,
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
    ).isoformat(timespec="seconds")

    # Communication history
    previous_contact = random.choice(CHANNELS)

    if previous_contact == "none":
        previous_response = "none"
    else:
        previous_response = random.choices(
            ["opened", "clicked", "ignored", "responded"],
            weights=[30, 15, 40, 15],
        )[0]

    return {
        "transaction_id": f"TXN-{100000 + transaction_number}",
        "customer_id": customer["customer_id"],
        "customer_name": customer["customer_name"],
        "plan_tier": customer["plan_tier"],
        "plan_value": customer["plan_value"],
        "tenure_months": customer["tenure_months"],
        "payment_method": customer["payment_method"],
        "previous_successes": customer["previous_successes"],
        "previous_failures": customer["previous_failures"],
        "previous_recovery_attempts": event_number,
        "days_since_last_payment": days_since_last_payment,
        "last_successful_payment": last_successful_payment,
        "previous_contact_channel": previous_contact,
        "previous_contact_response": previous_response,
        "decline_reason": reason,
        "decline_message": message,
        "timestamp": timestamp,
    }


def main(num_transactions=1000):
    customers = []

    # Create roughly 300 customers.
    num_customers = max(150, num_transactions // 3)

    for i in range(num_customers):
        customers.append(make_customer(i))

    rows = []

    for i in range(num_transactions):
        customer = random.choice(customers)

        # Calculate how many previous events this customer has had
        event_number = sum(
            1 for r in rows
            if r["customer_id"] == customer["customer_id"]
        )

        rows.append(
            make_transaction(
                transaction_number=i,
                customer=customer,
                event_number=event_number,
            )
        )

    out_path = "transactions.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)

    unique_customers = len(
        set(row["customer_id"] for row in rows)
    )

    print(
        f"Wrote {len(rows)} synthetic payment failures "
        f"across {unique_customers} customers to {out_path}"
    )


if __name__ == "__main__":
    number = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    main(number)