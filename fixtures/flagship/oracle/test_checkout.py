from shop.checkout import place_order
from shop.pricing import quote_total


def test_checkout_without_coupon():
    try:
        result = place_order([{"price_cents": 1299, "quantity": 1}])
    except Exception as error:
        result = {"error": type(error).__name__}
    assert result == {"status": "confirmed", "total_cents": 1299}


def test_explicit_discount():
    assert quote_total(1299, 200) == 1099
