from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory
from accounts.models import Address


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'id', 'full_name', 'phone_number',
            'address_line_1', 'address_line_2',
            'city', 'state', 'postal_code', 'country',
            'address_type', 'is_default'
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'variant', 'product_name',
            'variant_details', 'unit_price', 'quantity', 'line_total'
        ]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['status', 'note', 'changed_at']


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight — for order history listing"""
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status', 'payment_method',
            'payment_status', 'total', 'item_count', 'created_at'
        ]

    def get_item_count(self, obj):
        return obj.items.count()


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    shipping_address = AddressSerializer()
    billing_address = AddressSerializer()
    status_history = OrderStatusHistorySerializer(many=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status',
            'shipping_address', 'billing_address',
            'payment_method', 'payment_status',
            'razorpay_order_id', 'razorpay_payment_id',
            'subtotal', 'shipping_fee', 'total',
            'items', 'status_history',
            'created_at', 'updated_at'
        ]


class CreateOrderSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField()
    billing_address_id = serializers.IntegerField(required=False)
    same_as_shipping = serializers.BooleanField(default=True)
    payment_method = serializers.ChoiceField(choices=['cod', 'upi', 'card'])

    def validate(self, data):
        request = self.context['request']
        user = request.user

        # Validate shipping address belongs to user
        try:
            shipping_address = Address.objects.get(
                id=data['shipping_address_id'], user=user
            )
        except Address.DoesNotExist:
            raise serializers.ValidationError({"shipping_address_id": "Address not found."})

        # Determine billing address
        if data.get('same_as_shipping', True):
            billing_address = shipping_address
        else:
            billing_id = data.get('billing_address_id')
            if not billing_id:
                raise serializers.ValidationError(
                    {"billing_address_id": "Required when same_as_shipping is false."}
                )
            try:
                billing_address = Address.objects.get(id=billing_id, user=user)
            except Address.DoesNotExist:
                raise serializers.ValidationError({"billing_address_id": "Address not found."})

        # Validate cart is not empty
        cart = getattr(user, 'cart', None)
        if not cart or not cart.items.exists():
            raise serializers.ValidationError({"cart": "Your cart is empty."})

        data['shipping_address'] = shipping_address
        data['billing_address'] = billing_address
        data['cart'] = cart
        return data



# ✅ New — vendor sees order with only their items
class VendorOrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product_name', 'variant_details',
            'unit_price', 'quantity', 'line_total',
            'commission_rate', 'commission_amount', 'vendor_payout'
        ]


class VendorOrderSerializer(serializers.ModelSerializer):
    """
    Vendor-facing order serializer.
    Shows order info but only the items belonging to this vendor.
    Hides customer payment details and other vendors' items.
    """
    vendor_items = serializers.SerializerMethodField()
    vendor_subtotal = serializers.SerializerMethodField()
    vendor_total_payout = serializers.SerializerMethodField()
    shipping_city = serializers.SerializerMethodField()
    shipping_state = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status',
            'payment_method', 'payment_status',
            # ✅ Vendor sees shipping city/state but NOT full address
            # Full address is revealed only after order is confirmed
            'shipping_city', 'shipping_state',
            'vendor_items', 'vendor_subtotal', 'vendor_total_payout',
            'created_at'
        ]

    def get_vendor_items(self, obj):
        vendor = self.context.get('vendor')
        items = obj.items.filter(vendor=vendor)
        return VendorOrderItemSerializer(items, many=True).data

    def get_vendor_subtotal(self, obj):
        vendor = self.context.get('vendor')
        items = obj.items.filter(vendor=vendor)
        return sum(item.line_total for item in items)

    def get_vendor_total_payout(self, obj):
        vendor = self.context.get('vendor')
        items = obj.items.filter(vendor=vendor)
        return sum(item.vendor_payout for item in items)

    def get_shipping_city(self, obj):
        if obj.shipping_address:
            return obj.shipping_address.city
        return None

    def get_shipping_state(self, obj):
        if obj.shipping_address:
            return obj.shipping_address.state
        return None


class VendorOrderDetailSerializer(serializers.ModelSerializer):
    """
    Full order detail for vendor — shows complete shipping address
    only after order is confirmed.
    """
    vendor_items = serializers.SerializerMethodField()
    vendor_subtotal = serializers.SerializerMethodField()
    vendor_total_payout = serializers.SerializerMethodField()
    shipping_address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status',
            'payment_method', 'payment_status',
            'shipping_address',
            'vendor_items', 'vendor_subtotal', 'vendor_total_payout',
            'created_at', 'updated_at'
        ]

    def get_vendor_items(self, obj):
        vendor = self.context.get('vendor')
        items = obj.items.filter(vendor=vendor)
        return VendorOrderItemSerializer(items, many=True).data

    def get_vendor_subtotal(self, obj):
        vendor = self.context.get('vendor')
        items = obj.items.filter(vendor=vendor)
        return sum(item.line_total for item in items)

    def get_vendor_total_payout(self, obj):
        vendor = self.context.get('vendor')
        items = obj.items.filter(vendor=vendor)
        return sum(item.vendor_payout for item in items)

    def get_shipping_address(self, obj):
        # ✅ Full address only revealed after order confirmed
        if obj.status in ['confirmed', 'shipped', 'delivered']:
            if obj.shipping_address:
                return AddressSerializer(obj.shipping_address).data
        return {
            "city": obj.shipping_address.city if obj.shipping_address else None,
            "state": obj.shipping_address.state if obj.shipping_address else None,
            "note": "Full address visible after order confirmation."
        }        