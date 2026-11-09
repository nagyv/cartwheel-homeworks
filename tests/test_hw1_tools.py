from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent import db, tools
from agent.auth import AuthContext

SHOPPER_1 = AuthContext(user_id=1, role="shopper")
MERCHANT_STORE_2 = AuthContext(user_id=9002, role="merchant", store_id=2)
SUPPORT = AuthContext(user_id=9501, role="support")


def _status(db_path: Path, order_id: int) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT status FROM orders WHERE id = ?", (order_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _first_order_with_status(db_path: Path, status: str, store_id: int) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT id FROM orders WHERE status = ? AND store_id = ? ORDER BY id LIMIT 1",
            (status, store_id),
        ).fetchone()[0]
    finally:
        conn.close()


def _title_of_order_4127() -> str:
    with db.connection() as conn:
        order = db.get_order(conn, 4127)
        return next(p.title for p in db.list_products(conn, order.store_id) if p.id == order.product_id)


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_search_products_rejects_blank_query(world: dict, query: str) -> None:
    assert tools.search_products(SHOPPER_1, query)["error"] == "invalid_argument"


@pytest.mark.parametrize("ceiling", [0, -5])
def test_search_products_rejects_nonpositive_ceiling(world: dict, ceiling: float) -> None:
    assert tools.search_products(SHOPPER_1, "vase", max_price_usd=ceiling)["error"] == "invalid_argument"


def test_search_products_unknown_store_names_the_store(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "vase", store="Nowhere Shop")
    assert result["error"] == "not_found"
    assert "Nowhere Shop" in result["reason"]


def test_search_products_returns_contract_fields_only(world: dict) -> None:
    product = tools.search_products(SHOPPER_1, "vase")["products"][0]
    assert set(product) == {"product_id", "store_id", "title", "price_usd"}


def test_search_products_requires_every_token(world: dict) -> None:
    both = tools.search_products(SHOPPER_1, "VASE zzzznotaword", limit=25)
    assert both == {"ok": True, "products": [], "count": 0}


def test_search_products_matches_title_or_description(world: dict) -> None:
    with db.connection() as conn:
        product = db.list_products(conn, store_id=1)[0]
    token = next(word for word in product.description.split() if word.lower() not in product.title.lower())
    query = f"{product.title.split()[-1]} {token}"
    result = tools.search_products(SHOPPER_1, query, store="blue-heron-ceramics", limit=25)
    assert product.id in [p["product_id"] for p in result["products"]]


def test_search_products_ceiling_is_inclusive(world: dict) -> None:
    prices = [p["price_usd"] for p in tools.search_products(SHOPPER_1, "vase", limit=25)["products"]]
    ceiling = prices[0]
    result = tools.search_products(SHOPPER_1, "vase", max_price_usd=ceiling, limit=25)
    assert result["count"] >= 1
    assert all(p["price_usd"] <= ceiling for p in result["products"])
    assert ceiling in [p["price_usd"] for p in result["products"]]


def test_search_products_breaks_price_ties_by_product_id(world: dict) -> None:
    products = tools.search_products(SHOPPER_1, "a", limit=25)["products"]
    keys = [(p["price_usd"], p["product_id"]) for p in products]
    assert keys == sorted(keys)


@pytest.mark.parametrize(
    ("limit", "expected"),
    [(0, 1), (-3, 1), (2, 2), (1000, tools.MAX_SEARCH_LIMIT)],
)
def test_search_products_clamps_limit(world: dict, limit: int, expected: int) -> None:
    assert tools.search_products(SHOPPER_1, "a", limit=limit)["count"] == expected


def test_list_my_orders_returns_public_dicts_within_limit(world: dict) -> None:
    result = tools.list_my_orders(MERCHANT_STORE_2)
    assert 0 < result["count"] <= tools.DEFAULT_ORDER_LIMIT
    assert all(order["store_id"] == 2 for order in result["orders"])
    assert "user_id" not in result["orders"][0]


def test_list_my_orders_with_no_orders_is_success(world: dict) -> None:
    result = tools.list_my_orders(AuthContext(user_id=999_999, role="shopper"))
    assert result == {"ok": True, "orders": [], "count": 0}


def test_cancel_order_out_of_scope_hides_status(world_copy: Path) -> None:
    result = tools.cancel_order(MERCHANT_STORE_2, 4127, "not my store")
    assert result["error"] == "permission_denied"
    assert "merchant" in result["reason"]
    assert "4127" in result["reason"]
    assert "delivered" not in result["reason"]
    assert _status(world_copy, 4127) == "delivered"


def test_cancel_order_merchant_cancels_own_store_order(world_copy: Path) -> None:
    conn = sqlite3.connect(world_copy)
    try:
        order_id, store_id = conn.execute(
            "SELECT id, store_id FROM orders WHERE status = 'placed' ORDER BY id LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    merchant = AuthContext(user_id=9002, role="merchant", store_id=store_id)
    result = tools.cancel_order(merchant, order_id, "out of stock")
    assert result == {"ok": True, "order_id": order_id, "status": "cancelled"}
    assert _status(world_copy, order_id) == "cancelled"


def test_cancel_order_support_cancels_any_placed_order(world_copy: Path) -> None:
    order_id = _first_order_with_status(world_copy, "placed", 1)
    assert tools.cancel_order(SUPPORT, order_id, "duplicate")["status"] == "cancelled"
    assert _status(world_copy, order_id) == "cancelled"


@pytest.mark.parametrize("status", ["shipped", "delivered", "cancelled", "refunded"])
def test_cancel_order_requires_placed_for_every_role(world_copy: Path, status: str) -> None:
    order_id = _first_order_with_status(world_copy, status, 1)
    result = tools.cancel_order(SUPPORT, order_id, "too late")
    assert result["error"] == "not_eligible"
    assert status in result["reason"]
    assert "before shipment" in result["reason"]
    assert _status(world_copy, order_id) == status


def test_find_order_understands_natural_language(world: dict) -> None:
    query = f"the {_title_of_order_4127()} I bought last week"
    assert 4127 in [o["order_id"] for o in tools.find_order(SHOPPER_1, query)["orders"]]


def test_find_order_tolerates_case_and_small_typos(world: dict) -> None:
    *leading, last = _title_of_order_4127().upper().split()
    misspelled = last[:2] + last[3:]
    query = " ".join([*leading, misspelled])
    assert misspelled not in _title_of_order_4127().upper()
    assert 4127 in [o["order_id"] for o in tools.find_order(SHOPPER_1, query)["orders"]]


@pytest.mark.parametrize("query", ["", "   ", "the one I bought last week"])
def test_find_order_without_product_words_matches_nothing(world: dict, query: str) -> None:
    assert tools.find_order(SHOPPER_1, query) == {"ok": True, "orders": []}


def test_find_order_stays_in_the_shopper_scope(world: dict) -> None:
    orders = tools.find_order(SHOPPER_1, _title_of_order_4127())["orders"]
    with db.connection() as conn:
        assert {db.get_order(conn, o["order_id"]).user_id for o in orders} == {1}


def test_find_order_rejects_merchant_without_store(world: dict) -> None:
    merchant = AuthContext(user_id=9002, role="merchant", store_id=2)
    object.__setattr__(merchant, "store_id", None)
    result = tools.find_order(merchant, _title_of_order_4127())
    assert result["ok"] is False
    assert result["error"] == "permission_denied"


def test_find_order_rejects_unknown_role(world: dict) -> None:
    caller = AuthContext(user_id=1, role="shopper")
    object.__setattr__(caller, "role", "admin")
    result = tools.find_order(caller, _title_of_order_4127())
    assert result["ok"] is False
    assert result["error"] == "permission_denied"


def test_find_order_merchant_cannot_see_other_stores(world: dict) -> None:
    orders = tools.find_order(MERCHANT_STORE_2, _title_of_order_4127())["orders"]
    assert 4127 not in [o["order_id"] for o in orders]
    assert all(o["store_id"] == 2 for o in orders)
