from orders.models import OrderItem

def has_purchased_product(user, product):
    return OrderItem.objects.filter(
        order__user=user,
        order__status='delivered',
        product=product
    ).exists()