from django.db import models
from django.conf import settings
from products.models import Product, ProductVariant
from accounts.models import Address ,VendorProfile
import uuid
import secrets


class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    )

    PAYMENT_METHOD_CHOICES = (
        ('cod', 'Cash on Delivery'),
        ('upi', 'UPI'),
        ('card', 'Card'),
    )

    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders'
    )

    shipping_address = models.ForeignKey(
        Address, on_delete=models.SET_NULL, null=True, related_name='shipping_orders'
    )
    billing_address = models.ForeignKey(
        Address, on_delete=models.SET_NULL, null=True, related_name='billing_orders'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')

    # Razorpay fields — null until payment is initiated/completed
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = 'ORD' + secrets.token_hex(5).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} — {self.user.email or self.user.phone_number}"

    class Meta:
        ordering = ['-created_at']


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)


        # ✅ New — vendor FK on OrderItem
    # This tells us which vendor this item belongs to
    # null = platform product (admin-owned)
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='order_items',
        help_text="Vendor who sold this item. Null for platform products."
    )

    # ✅ Snapshot fields — preserved even if product is later changed/deleted
    product_name = models.CharField(max_length=300)
    variant_details = models.CharField(max_length=255, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

        # ✅ Commission tracking — industry standard
    # Calculated at order time based on vendor's commission_rate
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Commission % applied at time of order"
    )
    commission_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Platform commission in rupees"
    )
    vendor_payout = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Amount to be paid to vendor after commission"
    )

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class OrderStatusHistory(models.Model):
    """Track every status change for audit trail"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=20)
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.order.order_number} — {self.status}"