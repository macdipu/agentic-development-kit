def total_cents(unit_cents, quantity):
    """Legacy fixture defect: shipping charged twice for a two-item order."""
    return unit_cents * quantity + 100 * quantity
