def get_or_create_cart(request):
    """
    Returns the cart for the current user or guest session.
    Creates one if it doesn't exist.
    """
    from .models import Cart

    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart
    else:
        # Guest — use session key
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        cart, _ = Cart.objects.get_or_create(session_key=session_key)
        return cart


def merge_guest_cart_to_user(request, user):
    """
    Called after OTP login — merges guest cart into user cart.
    Guest items are moved to user cart, guest cart is deleted.
    """
    from .models import Cart, CartItem

    if not request.session.session_key:
        return

    try:
        guest_cart = Cart.objects.get(session_key=request.session.session_key)
    except Cart.DoesNotExist:
        return

    user_cart, _ = Cart.objects.get_or_create(user=user)

    for guest_item in guest_cart.items.all():
        existing = CartItem.objects.filter(
            cart=user_cart,
            product=guest_item.product,
            variant=guest_item.variant
        ).first()

        if existing:
            # Merge quantities
            existing.quantity += guest_item.quantity
            existing.save()
        else:
            # Move item to user cart
            guest_item.cart = user_cart
            guest_item.save()

    guest_cart.delete()