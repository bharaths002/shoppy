from django.db import models
from django.conf import settings
from products.models import Product, ProductVariant


class Cart(models.Model):
    # Logged-in user cart
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='cart'
    )
    # Guest user cart — tied to session
    session_key = models.CharField(max_length=100, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())

    def __str__(self):
        if self.user:
            return f"Cart — {self.user.email}"
        return f"Cart — Guest ({self.session_key})"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='cart_items'
    )
    # ✅ Optional — only set if product has variants
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One row per product+variant combo per cart
        unique_together = ('cart', 'product', 'variant')

    @property
    def unit_price(self):
        if self.variant:
            return self.variant.effective_price
        return self.product.effective_price

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"