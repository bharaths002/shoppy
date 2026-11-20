from django.db.models import Q
from orders.models import OrderItem


def has_purchased_product(user, product):
    """True once the user has received this product: its own item, or the whole order, is delivered."""
    return OrderItem.objects.filter(
        Q(status='delivered') | Q(order__status='delivered'),
        order__user=user,
        product=product,
    ).exclude(order__status__in=['cancelled', 'returned']).exists()