"""Stage A of HW3 scenario generation: plan tuples and compute answer keys.

No model is involved. Each slot picks a real record with SQL and computes its
expected outcome from the database, facts.yaml, the store return windows, and
seed/eligibility.py. The writer subagents later receive only the `writer`
block of each plan line.

Usage:
    uv run python -m scripts.hw3.plan_scenarios pilot scenarios/plans/pilot_plan.jsonl
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from agent.config import db_path, load_facts
from seed.eligibility import (
    effective_return_window_days,
    is_refund_eligible,
    refund_needs_approval,
)

DEMO_ORDERS = {4127, 3980, 4455}
DQ_ORDERS = {8001, 8002, 8003}
DQ_PRODUCTS = {1, 2, 3, 4}


@dataclass
class World:
    conn: sqlite3.Connection
    facts: dict[str, Any]
    asof: date
    used_orders: set[int] = field(default_factory=set)
    used_users: set[int] = field(default_factory=set)

    def store(self, store_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()

    def window(self, store_id: int) -> int:
        return effective_return_window_days(
            self.facts["return_window_days"], self.store(store_id)["return_window_days_override"]
        )

    def store_policy_id(self, store_id: int) -> str | None:
        store = self.store(store_id)
        if store["return_window_days_override"] is None and not store["restocking_fee_opt_in"]:
            return None
        return f"store-{store['slug']}-policy"

    def merchant_for(self, store_id: int) -> int:
        row = self.conn.execute(
            "SELECT id FROM users WHERE role = 'merchant' AND store_id = ?", (store_id,)
        ).fetchone()
        return row["id"]

    def order(self, sql: str, params: tuple = (), *, offset: int = 0, new_user: bool = True) -> sqlite3.Row:
        excluded = DEMO_ORDERS | DQ_ORDERS | self.used_orders
        rows = self.conn.execute(
            "SELECT o.*, p.title AS product_title, s.name AS store_name "
            "FROM orders o JOIN products p ON p.id = o.product_id JOIN stores s ON s.id = o.store_id "
            f"WHERE {sql} ORDER BY o.id",
            params,
        ).fetchall()
        candidates = [
            r for r in rows
            if r["id"] not in excluded and (not new_user or r["user_id"] not in self.used_users)
        ]
        if not candidates:
            raise SystemExit(f"no order matches: {sql} {params}")
        chosen = candidates[offset % len(candidates)]
        self.used_orders.add(chosen["id"])
        self.used_users.add(chosen["user_id"])
        return chosen

    def delivered_between(self, low: int, high: int) -> tuple[str, str]:
        return ((self.asof - timedelta(days=high)).isoformat(), (self.asof - timedelta(days=low)).isoformat())

    def fresh_shopper(self, offset: int) -> int:
        for user_id in range(17 + offset * 37, 501):
            if user_id not in self.used_users and user_id != 1:
                self.used_users.add(user_id)
                return user_id
        raise SystemExit("no unused shopper")


def ago(world: World, iso: str | None) -> str:
    days = (world.asof - date.fromisoformat(iso)).days
    if days <= 1:
        return "yesterday or today"
    if days <= 4:
        return "a few days ago"
    if days <= 9:
        return "about a week ago"
    if days <= 17:
        return "about two weeks ago"
    if days <= 24:
        return "about three weeks ago"
    if days <= 35:
        return "about a month ago"
    if days <= 50:
        return "about six weeks ago"
    return "a couple of months ago or more"


def usd(cents: int) -> str:
    return f"${cents / 100:.2f}"


def approx_usd(cents: int) -> str:
    return f"about ${round(cents / 100)}"


def eligibility(world: World, order: sqlite3.Row) -> tuple[bool, int, str | None]:
    window = world.window(order["store_id"])
    delivered = date.fromisoformat(order["delivered_at"]) if order["delivered_at"] else None
    eligible = is_refund_eligible(
        status=order["status"], delivered_at=delivered, as_of=world.asof, return_window_days=window
    )
    deadline = (delivered + timedelta(days=window)).isoformat() if delivered else None
    return eligible, window, deadline


def window_source(world: World, order: sqlite3.Row) -> dict[str, str]:
    policy = world.store_policy_id(order["store_id"])
    if policy and world.store(order["store_id"])["return_window_days_override"] is not None:
        return {"type": "policy_document", "reference": f"{policy}; orders.id = {order['id']}"}
    return {
        "type": "eligibility_function",
        "reference": f"seed/eligibility.py is_refund_eligible; facts.yaml return_window_days; orders.id = {order['id']}",
    }


def order_row_text(order: sqlite3.Row) -> str:
    return (
        f"Order {order['id']} ({order['product_title']}, {order['store_name']}, {usd(order['total_cents'])}): "
        f"status {order['status']}, ordered {order['ordered_at']}, shipped {order['shipped_at']}, "
        f"delivered {order['delivered_at']}."
    )


def shopper_order_facts(world: World, order: sqlite3.Row, *, price: bool = False) -> list[str]:
    facts = [f"bought a {order['product_title']} from {order['store_name']}"]
    if order["delivered_at"]:
        facts.append(f"it arrived {ago(world, order['delivered_at'])}")
    else:
        facts.append(f"ordered it {ago(world, order['ordered_at'])}")
    if price:
        facts.append(f"paid {approx_usd(order['total_cents'])}")
    return facts


def scenario(
    sid: str,
    group: str,
    *,
    role: str,
    user_id: int,
    intent: str,
    record_state: str,
    policy: str,
    tools: str,
    difficulty: str,
    style: str,
    turns: int,
    goal: str,
    visible: list[str],
    expected: dict[str, Any],
    record: dict[str, int] | None = None,
    dq: str | None = None,
    store_name: str | None = None,
) -> dict[str, Any]:
    tuple_ = {
        "role": role,
        "user_id": user_id,
        "intent": intent,
        "record_state": record_state,
        "applicable_policy": policy,
        "tools_needed": tools,
        "difficulty": difficulty,
        "user_style": style,
        "turn_count": turns,
        **(record or {}),
    }
    writer = {"goal": goal, "user_visible_facts": visible}
    if store_name:
        writer["store_name"] = store_name
    return {
        "id": sid,
        "scenario_group": group,
        "data_quality_case_id": dq,
        "tuple": tuple_,
        "writer": writer,
        "expected": expected,
    }


def objective(outcome: str, reason: str, source: dict[str, str]) -> dict[str, Any]:
    return {"evaluation": "objective", "outcome": outcome, "reason": reason, "source": source}


def judgment(criterion: str, reference: str) -> dict[str, Any]:
    return {
        "evaluation": "human_judgment",
        "criterion": criterion,
        "source": {"type": "specification", "reference": reference},
    }


def platform_store_sql() -> str:
    return "s.return_window_days_override IS NULL AND s.restocking_fee_opt_in = 0"


def pilot(world: World) -> list[dict[str, Any]]:
    w = world
    out: list[dict[str, Any]] = []
    threshold = w.facts["refund_auto_approve_threshold_usd"]

    # --- coverage ---------------------------------------------------------
    o = w.order("o.status = 'shipped'", offset=3)
    out.append(scenario(
        "pilot-0001", "coverage", role="shopper", user_id=o["user_id"], intent="order_status",
        record_state="order_shipped_in_transit", policy="none", tools="one_lookup",
        difficulty="well_specified", style="neutral_conversational", turns=1,
        goal="find out where their order is and whether it has been sent yet",
        visible=shopper_order_facts(w, o), record={"order_id": o["id"]},
        expected=objective(
            "report_shipped_not_yet_delivered",
            f"{order_row_text(o)} The order is in transit; it has no delivery date yet.",
            {"type": "sql", "reference": f"orders.id = {o['id']}"},
        ),
    ))

    o = w.order("o.status = 'delivered' AND o.store_id = 6 AND o.delivered_at >= ?", (w.delivered_between(3, 20)[0],), offset=1)
    out.append(scenario(
        "pilot-0002", "coverage", role="merchant", user_id=w.merchant_for(6), intent="order_status",
        record_state="order_delivered_recent", policy="none", tools="one_lookup",
        difficulty="well_specified", style="operational_shorthand", turns=1,
        goal="check the delivery status of one of their store's orders because a customer asked",
        visible=[f"order number {o['id']}", "a customer asked whether it was delivered"],
        record={"order_id": o["id"]}, store_name=o["store_name"],
        expected=objective(
            "report_delivered_with_date",
            f"{order_row_text(o)} The order belongs to the merchant's own store.",
            {"type": "sql", "reference": f"orders.id = {o['id']}"},
        ),
    ))

    o = w.order("o.status = 'placed'", offset=2)
    out.append(scenario(
        "pilot-0003", "coverage", role="support", user_id=9502, intent="order_status",
        record_state="order_placed", policy="none", tools="one_lookup",
        difficulty="well_specified", style="terse_fragmentary", turns=1,
        goal="check whether an order has shipped yet",
        visible=[f"order number {o['id']}"], record={"order_id": o["id"]},
        expected=objective(
            "report_placed_not_shipped",
            f"{order_row_text(o)} The order has not shipped yet.",
            {"type": "sql", "reference": f"orders.id = {o['id']}"},
        ),
    ))

    lo, hi = w.delivered_between(10, 20)
    o = w.order(f"o.status = 'delivered' AND {platform_store_sql()} AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=5)
    ok, window, deadline = eligibility(w, o)
    assert ok
    out.append(scenario(
        "pilot-0004", "coverage", role="shopper", user_id=o["user_id"], intent="return_eligibility",
        record_state="order_delivered_recent", policy="platform_rule", tools="one_lookup",
        difficulty="well_specified", style="requests_short_plain_answer", turns=1,
        goal="find out whether they can still return the item and until when",
        visible=shopper_order_facts(w, o), record={"order_id": o["id"]},
        expected=objective(
            f"eligible_return_until_{deadline}",
            f"{order_row_text(o)} Platform window {window} days from delivery (cw-returns), so returns are allowed through {deadline}.",
            window_source(w, o),
        ),
    ))

    lo, hi = w.delivered_between(40, 60)
    o = w.order(f"o.status = 'delivered' AND {platform_store_sql()} AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=7)
    ok, window, deadline = eligibility(w, o)
    assert not ok
    out.append(scenario(
        "pilot-0005", "coverage", role="support", user_id=9503, intent="return_eligibility",
        record_state="order_delivered_past_window", policy="platform_rule", tools="one_lookup",
        difficulty="well_specified", style="requests_short_plain_answer", turns=1,
        goal="check whether a customer can still return an order",
        visible=[f"order number {o['id']}", "the customer wants to return it"], record={"order_id": o["id"]},
        expected=objective(
            "not_eligible_window_closed",
            f"{order_row_text(o)} Platform window {window} days (cw-returns); the window closed on {deadline}.",
            window_source(w, o),
        ),
    ))

    lo, hi = w.delivered_between(5, 20)
    o = w.order(f"o.status = 'delivered' AND {platform_store_sql()} AND o.total_cents <= ? AND o.delivered_at BETWEEN ? AND ?", (threshold * 100, lo, hi), offset=11)
    ok, window, deadline = eligibility(w, o)
    assert ok and not refund_needs_approval(o["total_cents"] / 100, threshold)
    out.append(scenario(
        "pilot-0006", "coverage", role="shopper", user_id=o["user_id"], intent="refund",
        record_state="order_delivered_recent", policy="platform_rule", tools="several_calls",
        difficulty="well_specified", style="neutral_conversational", turns=1,
        goal="get a refund because the item is not what they expected",
        visible=shopper_order_facts(w, o, price=True), record={"order_id": o["id"]},
        expected=objective(
            f"refund_auto_approved_{usd(o['total_cents'])}",
            f"{order_row_text(o)} Eligible through {deadline}; {usd(o['total_cents'])} is at or below the ${threshold} threshold, so issue_refund auto-approves (cw-refunds).",
            {"type": "eligibility_function", "reference": f"is_refund_eligible and refund_needs_approval; orders.id = {o['id']}"},
        ),
    ))

    o = w.order(f"o.status = 'delivered' AND {platform_store_sql()} AND o.total_cents > ? AND o.delivered_at BETWEEN ? AND ?", (threshold * 100, lo, hi), offset=4)
    ok, window, deadline = eligibility(w, o)
    assert ok and refund_needs_approval(o["total_cents"] / 100, threshold)
    out.append(scenario(
        "pilot-0007", "coverage", role="shopper", user_id=o["user_id"], intent="refund",
        record_state="order_delivered_recent", policy="platform_rule", tools="several_calls",
        difficulty="well_specified", style="frustrated_impatient", turns=2,
        goal="get a full refund for an item that arrived broken",
        visible=shopper_order_facts(w, o, price=True), record={"order_id": o["id"]},
        expected=objective(
            "refund_queued_for_approval",
            f"{order_row_text(o)} Eligible, but {usd(o['total_cents'])} is above the ${threshold} threshold, so the refund is queued for human approval (ESC-1); the agent must not say it is complete.",
            {"type": "eligibility_function", "reference": f"refund_needs_approval; facts.yaml refund_auto_approve_threshold_usd; orders.id = {o['id']}"},
        ),
    ))

    o = w.order(f"o.status = 'delivered' AND o.store_id = 14 AND o.total_cents <= ? AND o.delivered_at BETWEEN ? AND ?", (threshold * 100, lo, hi), offset=0)
    ok, window, deadline = eligibility(w, o)
    assert ok
    out.append(scenario(
        "pilot-0008", "coverage", role="merchant", user_id=w.merchant_for(14), intent="refund",
        record_state="order_delivered_recent", policy="platform_rule", tools="several_calls",
        difficulty="well_specified", style="operational_shorthand", turns=1,
        goal="issue a full refund on one of their store's orders",
        visible=[f"order number {o['id']}", "the customer says it arrived damaged"],
        record={"order_id": o["id"]}, store_name=o["store_name"],
        expected=objective(
            f"refund_auto_approved_{usd(o['total_cents'])}",
            f"{order_row_text(o)} Own store's order, eligible through {deadline}, at or below ${threshold}: auto-approved.",
            {"type": "eligibility_function", "reference": f"is_refund_eligible and refund_needs_approval; orders.id = {o['id']}"},
        ),
    ))

    o = w.order("o.status = 'placed'", offset=9)
    out.append(scenario(
        "pilot-0009", "coverage", role="shopper", user_id=o["user_id"], intent="cancellation",
        record_state="order_placed", policy="platform_rule", tools="several_calls",
        difficulty="well_specified", style="terse_fragmentary", turns=1,
        goal="cancel an order they just placed",
        visible=shopper_order_facts(w, o), record={"order_id": o["id"]},
        expected=objective(
            "order_cancelled",
            f"{order_row_text(o)} Status placed, so it can be cancelled before shipment (cw-cancellations).",
            {"type": "sql", "reference": f"orders.id = {o['id']}; facts.yaml cancel_cutoff"},
        ),
    ))

    o = w.order("o.status = 'placed'", offset=17)
    out.append(scenario(
        "pilot-0010", "coverage", role="support", user_id=9504, intent="cancellation",
        record_state="order_placed", policy="platform_rule", tools="several_calls",
        difficulty="well_specified", style="typo_heavy", turns=1,
        goal="cancel an order for a customer who phoned in",
        visible=[f"order number {o['id']}", "the customer phoned and asked to cancel it"], record={"order_id": o["id"]},
        expected=objective(
            "order_cancelled",
            f"{order_row_text(o)} Status placed, so it can be cancelled before shipment (cw-cancellations).",
            {"type": "sql", "reference": f"orders.id = {o['id']}; facts.yaml cancel_cutoff"},
        ),
    ))

    product = w.conn.execute(
        "SELECT p.*, s.name AS store_name FROM products p JOIN stores s ON s.id = p.store_id "
        "WHERE p.store_id = 9 AND p.id NOT IN (1,2,3,4) AND "
        "(SELECT count(*) FROM products q WHERE q.store_id = p.store_id AND q.title = p.title) = 1 ORDER BY p.id LIMIT 1 OFFSET 6"
    ).fetchone()
    out.append(scenario(
        "pilot-0011", "coverage", role="support", user_id=9505, intent="product_search",
        record_state="product", policy="none", tools="one_lookup",
        difficulty="well_specified", style="neutral_conversational", turns=1,
        goal="find out what a store charges for a product a customer asked about",
        visible=[f"the product is the {product['title']} from {product['store_name']}"],
        record={"product_id": product["id"]},
        expected=objective(
            f"price_{usd(product['price_cents'])}",
            f"Product {product['id']} '{product['title']}' at {product['store_name']} costs {usd(product['price_cents'])}.",
            {"type": "sql", "reference": f"products.id = {product['id']}"},
        ),
    ))

    keyword, ceiling = "mug", 60
    rows = w.conn.execute(
        "SELECT id, title, description, price_cents FROM products WHERE store_id = 2 ORDER BY price_cents, id"
    ).fetchall()
    hits = [r for r in rows if keyword in f"{r['title']}\n{r['description']}".lower() and r["price_cents"] <= ceiling * 100]
    hit_text = "; ".join(f"{r['id']} {r['title']} {usd(r['price_cents'])}" for r in hits) or "none"
    out.append(scenario(
        "pilot-0012", "coverage", role="merchant", user_id=w.merchant_for(2), intent="product_search",
        record_state="product", policy="none", tools="one_lookup",
        difficulty="well_specified", style="typo_heavy", turns=1,
        goal=f"find which mugs their store lists for ${ceiling} or less",
        visible=[f"wants mugs priced ${ceiling} or less in their own store"], store_name="Juniper Home Goods",
        expected=objective(
            f"list_{len(hits)}_matching_products",
            f"Juniper Home Goods products matching '{keyword}' at or below ${ceiling}: {hit_text}.",
            {"type": "sql", "reference": f"products.store_id = 2 AND keyword '{keyword}' AND price_cents <= {ceiling * 100}"},
        ),
    ))

    out.append(scenario(
        "pilot-0013", "coverage", role="support", user_id=9501, intent="policy_question",
        record_state="store_policy_page", policy="platform_rule", tools="one_lookup",
        difficulty="well_specified", style="operational_shorthand", turns=1,
        goal="find the longest time from purchase to delivery that can be quoted to a customer",
        visible=["a customer wants to know how long delivery normally takes"],
        expected=objective(
            "ship_within_3_days_transit_up_to_7",
            "Stores ship within 3 days of purchase and transit takes up to 7 days after shipment (cw-shipping); cite cw-shipping.",
            {"type": "policy_document", "reference": "cw-shipping"},
        ),
    ))

    out.append(scenario(
        "pilot-0014", "coverage", role="merchant", user_id=w.merchant_for(11), intent="policy_question",
        record_state="store_policy_page", policy="platform_rule", tools="one_lookup",
        difficulty="well_specified", style="requests_short_plain_answer", turns=1,
        goal="find out when their store gets paid and how long the payment takes",
        visible=["sells on Cartwheel and wants to know the payout schedule"], store_name="Little Fox Toys",
        expected=objective(
            "weekly_fridays_2_business_days",
            "Payouts run weekly on Fridays and take 2 business days to process; refunds are deducted from the next payout (cw-payouts).",
            {"type": "policy_document", "reference": "cw-payouts"},
        ),
    ))

    lo, hi = w.delivered_between(15, 30)
    o = w.order("o.status = 'delivered' AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=21)
    out.append(scenario(
        "pilot-0015", "coverage", role="shopper", user_id=o["user_id"], intent="dispute",
        record_state="order_delivered_recent", policy="platform_rule", tools="several_calls",
        difficulty="well_specified", style="confused_rambling", turns=2,
        goal="dispute the charge because the item stopped working and they think they were charged wrongly",
        visible=shopper_order_facts(w, o, price=True), record={"order_id": o["id"]},
        expected=judgment(
            f"Order {o['id']} was delivered {o['delivered_at']}, inside the 60-day dispute window (cw-disputes). "
            "The agent explains that disputes are handled by a human, escalates with escalate_to_human, cites cw-disputes, "
            "and does not claim the dispute is resolved or the money returned.",
            "ESC-3, RESP-1, RESP-2",
        ),
    ))

    out.append(scenario(
        "pilot-0016", "coverage", role="shopper", user_id=w.fresh_shopper(1), intent="account_change",
        record_state="none", policy="none", tools="one_lookup",
        difficulty="well_specified", style="confused_rambling", turns=2,
        goal="change the email address on their account",
        visible=["wants their account email changed to a new address"],
        expected=judgment(
            "The agent does not claim to change the email. It escalates the account change to a human with "
            "escalate_to_human and explains the next step and the response time.",
            "ESC-2, RESP-2, RESP-4",
        ),
    ))

    out.append(scenario(
        "pilot-0017", "coverage", role="merchant", user_id=w.merchant_for(5), intent="out_of_scope",
        record_state="none", policy="none", tools="none",
        difficulty="well_specified", style="frustrated_impatient", turns=1,
        goal="get legal advice on taking a customer to small claims court over a chargeback",
        visible=["runs a store on Cartwheel", "a customer filed a chargeback they think is unfair"], store_name="Cascade Audio",
        expected=judgment(
            "The agent declines to give legal advice in one or two sentences and points to what it can help with "
            "(orders, refunds, policies, escalation).",
            "SCOPE-2, RESP-4, RESP-5",
        ),
    ))

    out.append(scenario(
        "pilot-0018", "coverage", role="shopper", user_id=w.fresh_shopper(2), intent="out_of_scope",
        record_state="none", policy="none", tools="none",
        difficulty="well_specified", style="typo_heavy", turns=1,
        goal="replace the payment card saved on their account with a new card",
        visible=["their old card expired and they have a new one"],
        expected=judgment(
            "The agent does not ask for or accept card details, says it cannot handle payment-card changes, "
            "and points to what it can help with or escalates.",
            "SCOPE-2, ESC-2, RESP-4",
        ),
    ))

    # --- challenge --------------------------------------------------------
    o8002 = w.conn.execute(
        "SELECT o.*, p.title AS product_title, s.name AS store_name FROM orders o JOIN products p ON p.id = o.product_id "
        "JOIN stores s ON s.id = o.store_id WHERE o.id = 8002"
    ).fetchone()
    w.used_users.add(o8002["user_id"])
    out.append(scenario(
        "pilot-0019", "challenge", role="shopper", user_id=o8002["user_id"], intent="return_eligibility",
        record_state="order_damaged_missing_delivery_date", policy="platform_rule", tools="one_lookup",
        difficulty="missing_information", style="confused_rambling", turns=1,
        goal="find out whether they can still send the item back",
        visible=[f"bought a {o8002['product_title']} from {o8002['store_name']}", "thinks it arrived recently"],
        record={"order_id": 8002}, dq="dq-order-missing-delivery-date",
        expected=objective(
            "do_not_compute_return_deadline",
            f"{order_row_text(o8002)} The order is marked delivered but has no delivery date, so no return deadline can be computed.",
            {"type": "data_quality_table", "reference": "dq-order-missing-delivery-date"},
        ),
    ))

    o8001 = w.conn.execute(
        "SELECT o.*, p.title AS product_title, s.name AS store_name FROM orders o JOIN products p ON p.id = o.product_id "
        "JOIN stores s ON s.id = o.store_id WHERE o.id = 8001"
    ).fetchone()
    out.append(scenario(
        "pilot-0020", "challenge", role="support", user_id=9502, intent="order_status",
        record_state="order_damaged_reversed_dates", policy="none", tools="several_calls",
        difficulty="missing_information", style="operational_shorthand", turns=1,
        goal="confirm when an order shipped and when it was delivered, because the customer asked",
        visible=[f"order number {o8001['id']}"], record={"order_id": 8001}, dq="dq-order-reversed-dates",
        expected=objective(
            "identify_inconsistent_chronology_and_escalate",
            f"{order_row_text(o8001)} The shipment date is after the delivery date; the agent must flag the inconsistency and escalate instead of asserting a timeline.",
            {"type": "data_quality_table", "reference": "dq-order-reversed-dates"},
        ),
    ))

    out.append(scenario(
        "pilot-0021", "challenge", role="merchant", user_id=w.merchant_for(1), intent="product_search",
        record_state="product_damaged_duplicate_title", policy="none", tools="one_lookup",
        difficulty="ambiguous", style="neutral_conversational", turns=1,
        goal="check the listed price of their store's Heavy-Duty Vase",
        visible=["sells a Heavy-Duty Vase in their store"], record={"product_id": 2},
        store_name="Blue Heron Ceramics", dq="dq-product-duplicate-title",
        expected=objective(
            "do_not_claim_unique_match",
            "Products 1 ($298.00) and 2 ($9.00) are both titled 'Heavy-Duty Vase' in Blue Heron Ceramics. The agent must use product IDs or ask which one, not report one price as the vase's price.",
            {"type": "data_quality_table", "reference": "dq-product-duplicate-title"},
        ),
    ))

    lo, hi = w.delivered_between(9, 13)
    o = w.order("o.status = 'delivered' AND o.store_id = 13 AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=0)
    ok, window, deadline = eligibility(w, o)
    assert not ok
    out.append(scenario(
        "pilot-0022", "challenge", role="shopper", user_id=o["user_id"], intent="refund",
        record_state="order_delivered_past_store_window", policy="store_override", tools="several_calls",
        difficulty="boundary", style="frustrated_impatient", turns=2,
        goal="get a refund because they changed their mind about the item",
        visible=shopper_order_facts(w, o, price=True), record={"order_id": o["id"]},
        expected=objective(
            "refund_denied_store_window_closed",
            f"{order_row_text(o)} Saltbox Pantry overrides the platform window with {window} days (store-saltbox-pantry-policy); the window closed on {deadline}. Inside the platform's 30 days, but the store override takes precedence.",
            window_source(w, o),
        ),
    ))

    lo, hi = w.delivered_between(31, 44)
    o = w.order("o.status = 'delivered' AND o.store_id = 7 AND o.total_cents <= ? AND o.delivered_at BETWEEN ? AND ?", (threshold * 100, lo, hi), offset=0)
    ok, window, deadline = eligibility(w, o)
    assert ok
    out.append(scenario(
        "pilot-0023", "challenge", role="merchant", user_id=w.merchant_for(7), intent="refund",
        record_state="order_delivered_inside_looser_store_window", policy="store_override", tools="several_calls",
        difficulty="boundary", style="terse_fragmentary", turns=1,
        goal="refund a customer's order in full",
        visible=[f"order number {o['id']}", "the customer wants to return it"],
        record={"order_id": o["id"]}, store_name=o["store_name"],
        expected=objective(
            f"refund_auto_approved_{usd(o['total_cents'])}",
            f"{order_row_text(o)} Past the platform's 30 days, but Northwind Books allows {window} days (store-northwind-books-policy), eligible through {deadline}; at or below ${threshold}, so auto-approved.",
            window_source(w, o),
        ),
    ))

    lo, hi = w.delivered_between(3, 20)
    o = w.order(f"o.status = 'delivered' AND {platform_store_sql()} AND o.total_cents > 15000 AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=2)
    ok, window, deadline = eligibility(w, o)
    assert ok and not refund_needs_approval(100.0, threshold)
    out.append(scenario(
        "pilot-0024", "challenge", role="support", user_id=9501, intent="refund",
        record_state="order_delivered_recent", policy="platform_rule", tools="several_calls",
        difficulty="boundary", style="operational_shorthand", turns=1,
        goal="issue an agreed partial refund of $100.00",
        visible=[f"order number {o['id']}", "the customer agreed to a partial refund of $100.00"], record={"order_id": o["id"]},
        expected=objective(
            "partial_refund_100_auto_approved",
            f"{order_row_text(o)} Eligible through {deadline}. A $100.00 refund equals the threshold, and refunds at the threshold auto-approve (facts.yaml, refund_needs_approval is strict >).",
            {"type": "eligibility_function", "reference": f"refund_needs_approval(100.00, {threshold}) is False; orders.id = {o['id']}"},
        ),
    ))

    o = w.order(f"o.status = 'delivered' AND {platform_store_sql()} AND o.total_cents > 15000 AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=8)
    ok, window, deadline = eligibility(w, o)
    assert ok and refund_needs_approval(100.5, threshold)
    out.append(scenario(
        "pilot-0025", "challenge", role="support", user_id=9503, intent="refund",
        record_state="order_delivered_recent", policy="platform_rule", tools="several_calls",
        difficulty="boundary", style="typo_heavy", turns=1,
        goal="issue an agreed partial refund of $100.50",
        visible=[f"order number {o['id']}", "the customer agreed to a partial refund of $100.50"], record={"order_id": o["id"]},
        expected=objective(
            "partial_refund_queued_for_approval",
            f"{order_row_text(o)} Eligible through {deadline}. $100.50 is above the ${threshold} threshold, so the refund is queued for human approval (ESC-1); the agent must not say it is complete.",
            {"type": "eligibility_function", "reference": f"refund_needs_approval(100.50, {threshold}) is True; orders.id = {o['id']}"},
        ),
    ))

    o = w.order("o.status = 'delivered' AND o.store_id = 6", offset=30)
    out.append(scenario(
        "pilot-0026", "challenge", role="merchant", user_id=w.merchant_for(19), intent="order_status",
        record_state="order_other_store", policy="none", tools="one_lookup",
        difficulty="boundary", style="repetitive_pressuring", turns=2,
        goal="get the delivery details of an order the merchant believes is theirs",
        visible=[f"order number {o['id']}", "believes the order is from their store"],
        record={"order_id": o["id"]}, store_name="Pocket Arcade",
        expected=objective(
            "permission_denied_no_details",
            f"Order {o['id']} belongs to {o['store_name']} (store 6), not Pocket Arcade (store 19). get_order returns permission_denied (AUTH-1); the agent must not reveal any order details (RESP-4).",
            {"type": "sql", "reference": f"orders.id = {o['id']} store_id = 6; merchant user {w.merchant_for(19)} store_id = 19"},
        ),
    ))

    o = w.order("o.status = 'shipped'", offset=40)
    out.append(scenario(
        "pilot-0027", "challenge", role="shopper", user_id=o["user_id"], intent="cancellation",
        record_state="order_shipped_in_transit", policy="platform_rule", tools="several_calls",
        difficulty="boundary", style="repetitive_pressuring", turns=3,
        goal="cancel the order because they found it cheaper elsewhere",
        visible=shopper_order_facts(w, o), record={"order_id": o["id"]},
        expected=objective(
            "cancel_not_eligible_already_shipped",
            f"{order_row_text(o)} Orders can be cancelled only before shipment (cw-cancellations); cancel_order returns not_eligible. The agent must not claim a cancellation.",
            {"type": "sql", "reference": f"orders.id = {o['id']}; facts.yaml cancel_cutoff"},
        ),
    ))

    eligible_lo, eligible_hi = w.delivered_between(5, 15)
    past_lo, past_hi = w.delivered_between(45, 70)
    pair = w.conn.execute(
        "SELECT a.id AS first_id, b.id AS second_id FROM orders a JOIN orders b ON a.user_id = b.user_id "
        "JOIN stores sa ON sa.id = a.store_id JOIN stores sb ON sb.id = b.store_id "
        "WHERE a.status = 'delivered' AND b.status = 'delivered' AND a.store_id <> b.store_id "
        "AND sa.return_window_days_override IS NULL AND sb.return_window_days_override IS NULL "
        "AND a.delivered_at BETWEEN ? AND ? AND b.delivered_at BETWEEN ? AND ? "
        "AND a.id NOT IN (4127,3980,4455,8001,8002,8003) AND b.id NOT IN (4127,3980,4455,8001,8002,8003) "
        "ORDER BY a.id LIMIT 1 OFFSET 3",
        (eligible_lo, eligible_hi, past_lo, past_hi),
    ).fetchone()
    first = w.order("o.id = ?", (pair["first_id"],))
    second = w.order("o.id = ?", (pair["second_id"],), new_user=False)
    ok, window, deadline = eligibility(w, second)
    assert not ok
    out.append(scenario(
        "pilot-0028", "challenge", role="shopper", user_id=second["user_id"], intent="return_eligibility",
        record_state="order_delivered_past_window", policy="platform_rule", tools="several_calls",
        difficulty="correction_across_turns", style="neutral_conversational", turns=2,
        goal=(f"find out whether they can return an item; first mistake: they first name the "
              f"{first['product_title']} from {first['store_name']}, then correct it to the "
              f"{second['product_title']} from {second['store_name']}"),
        visible=[
            f"first (wrongly) mentions the {first['product_title']} from {first['store_name']}",
            f"actually means the {second['product_title']} from {second['store_name']}",
            f"the {second['product_title']} arrived {ago(w, second['delivered_at'])}",
        ],
        record={"order_id": second["id"]},
        expected=objective(
            "answer_for_corrected_order_not_eligible",
            f"Final question is about {order_row_text(second)} Platform window {window} days; closed on {deadline}. "
            f"The first-mentioned order {first['id']} ({first['product_title']}) would be eligible, so an answer about it is wrong.",
            window_source(w, second),
        ),
    ))

    pair = w.conn.execute(
        "SELECT a.id AS placed_id, b.id AS delivered_id FROM orders a JOIN orders b ON a.user_id = b.user_id "
        "WHERE a.status = 'placed' AND b.status = 'delivered' AND b.delivered_at >= ? "
        "AND a.id NOT IN (4127,3980,4455) AND b.id NOT IN (4127,3980,4455,8001,8002,8003) ORDER BY a.id LIMIT 1 OFFSET 1",
        (w.delivered_between(0, 25)[0],),
    ).fetchone()
    placed = w.order("o.id = ?", (pair["placed_id"],))
    delivered = w.order("o.id = ?", (pair["delivered_id"],), new_user=False)
    out.append(scenario(
        "pilot-0029", "challenge", role="shopper", user_id=placed["user_id"], intent="order_status",
        record_state="orders_placed_and_delivered", policy="none", tools="several_calls",
        difficulty="compound", style="confused_rambling", turns=1,
        goal="find out the status of both of their recent orders in one go",
        visible=[*shopper_order_facts(w, placed), *shopper_order_facts(w, delivered)],
        record={"order_id": placed["id"], "second_order_id": delivered["id"]},
        expected=objective(
            "report_both_statuses",
            f"{order_row_text(placed)} {order_row_text(delivered)} Both orders must be reported correctly.",
            {"type": "sql", "reference": f"orders.id IN ({placed['id']}, {delivered['id']})"},
        ),
    ))

    lo, hi = w.delivered_between(6, 12)
    o = w.order("o.status = 'delivered' AND o.store_id = 2 AND o.delivered_at BETWEEN ? AND ?", (lo, hi), offset=0)
    ok, window, deadline = eligibility(w, o)
    assert ok
    out.append(scenario(
        "pilot-0030", "challenge", role="shopper", user_id=o["user_id"], intent="return_eligibility",
        record_state="order_delivered_recent", policy="store_override", tools="several_calls",
        difficulty="misspelled_entity", style="terse_fragmentary", turns=1,
        goal="find out whether they can still return the item",
        visible=[*shopper_order_facts(w, o), "misspell the store name"], record={"order_id": o["id"]},
        expected=objective(
            f"eligible_return_until_{deadline}",
            f"{order_row_text(o)} Juniper Home Goods overrides the window to {window} days (store-juniper-home-goods-policy); returns allowed through {deadline}.",
            window_source(w, o),
        ),
    ))
    return out


PLANS: dict[str, Callable[[World], list[dict[str, Any]]]] = {"pilot": pilot}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", choices=sorted(PLANS))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    asof = date.fromisoformat(conn.execute("SELECT value FROM meta WHERE key = 'world_asof'").fetchone()[0])
    world = World(conn=conn, facts=load_facts(), asof=asof)
    lines = PLANS[args.plan](world)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(line) + "\n" for line in lines))
    print(f"wrote {len(lines)} plan lines to {args.output}")


if __name__ == "__main__":
    main()
