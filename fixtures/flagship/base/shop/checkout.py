from shop.pricing import quote_total

def place_order(cart):
    subtotal_cents = sum(item["price_cents"] * item["quantity"] for item in cart)
    total_cents = quote_total(subtotal_cents)
    return {"status": "confirmed", "total_cents": total_cents}
