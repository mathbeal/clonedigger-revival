def total_with_tax(items):
    total = 0
    for item in items:
        price = item.price * item.quantity
        if item.discount:
            price = price - item.discount
        total = total + price
    total = total * 1.2
    return round(total, 2)


def total_with_rebate(lines):
    amount = 0
    for line in lines:
        cost = line.price * line.quantity
        if line.discount:
            cost = cost - line.discount
        amount = amount + cost
    amount = amount * 0.9
    return round(amount, 2)
