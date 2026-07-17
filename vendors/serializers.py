from rest_framework import serializers
from accounts.models import VendorProfile
from products.models import Product, ProductVariant


class VendorRegistrationSerializer(serializers.Serializer):
    """
    Collects all vendor info needed to create a VendorProfile.
    OTP verification happens first via existing /sendotp/ + this endpoint.
    """
    # Auth fields
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    # Shop info
    shop_name = serializers.CharField(max_length=200)
    shop_description = serializers.CharField(required=False, allow_blank=True)

    # Business info
    business_type = serializers.ChoiceField(choices=[
        'individual', 'partnership', 'private_limited', 'public_limited'
    ])
    gstin = serializers.CharField(
        max_length=15, required=False, allow_blank=True
    )
    pan_number = serializers.CharField(
        max_length=10, required=False, allow_blank=True
    )

    # Contact
    business_phone = serializers.CharField(max_length=15)
    business_email = serializers.EmailField()
    business_address = serializers.CharField(required=False, allow_blank=True)

    def validate_shop_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Shop name must be at least 3 characters.")
        if VendorProfile.objects.filter(shop_name__iexact=value.strip()).exists():
            raise serializers.ValidationError("A shop with this name already exists.")
        return value.strip()

    def validate_gstin(self, value):
        if value and len(value) != 15:
            raise serializers.ValidationError("GSTIN must be exactly 15 characters.")
        return value.upper()

    def validate_pan_number(self, value):
        if value and len(value) != 10:
            raise serializers.ValidationError("PAN number must be exactly 10 characters.")
        return value.upper()

    def validate_business_phone(self, value):
        cleaned = value.strip().replace(' ', '').replace('-', '')
        if not cleaned.isdigit():
            raise serializers.ValidationError("Phone must contain only digits.")
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise serializers.ValidationError("Phone must be between 10 and 15 digits.")
        return cleaned


class VendorProfileSerializer(serializers.ModelSerializer):
    """Used to display vendor profile info"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    total_products = serializers.IntegerField(read_only=True)

    class Meta:
        model = VendorProfile
        fields = [
            'id', 'user_email', 'shop_name', 'shop_slug',
            'shop_description', 'logo', 'banner',
            'business_type', 'gstin', 'pan_number',
            'business_phone', 'business_email', 'business_address',
            'status', 'rejection_reason', 'commission_rate',
            'is_active', 'total_products', 'approved_at', 'created_at'
        ]
        read_only_fields = [
            'shop_slug', 'status', 'rejection_reason',
            'commission_rate', 'is_active', 'approved_at', 'created_at'
        ]


class UpdateVendorProfileSerializer(serializers.ModelSerializer):
    """Vendor can update their own shop info — not status or commission"""
    class Meta:
        model = VendorProfile
        fields = [
            'shop_description', 'logo', 'banner',
            'business_phone', 'business_email', 'business_address'
        ]


# ─────────────────────────────────────────────────────────────
# Inventory Serializers
# ─────────────────────────────────────────────────────────────

class VariantInventorySerializer(serializers.ModelSerializer):
    """Shows a single variant's stock status"""
    attributes = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'sku', 'stock',
            'stock_status', 'attributes',
            'price', 'is_active'
        ]

    def get_attributes(self, obj):
        return [
            {"attribute": a.attribute_type.name, "value": a.value}
            for a in obj.attributes.select_related('attribute_type').all()
        ]

    def get_stock_status(self, obj):
        """
        Industry standard stock status labels:
        out_of_stock → 0 units
        low_stock    → 1-10 units (vendor should restock)
        in_stock     → 11+ units
        """
        if obj.stock == 0:
            return "out_of_stock"
        elif obj.stock <= 10:
            return "low_stock"
        return "in_stock"


class ProductInventorySerializer(serializers.ModelSerializer):
    """
    Shows a product's full inventory snapshot.
    For simple products (no variants) — shows product-level stock.
    For variant products — shows each variant's stock.
    """
    variants = VariantInventorySerializer(many=True)
    stock_status = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug',
            'has_variants', 'stock',
            'total_stock', 'stock_status',
            'primary_image', 'variants',
            'is_active', 'updated_at'
        ]

    def get_stock_status(self, obj):
        if obj.has_variants:
            total = sum(v.stock for v in obj.variants.all())
            if total == 0:
                return "out_of_stock"
            elif total <= 10:
                return "low_stock"
            return "in_stock"
        else:
            if obj.stock == 0:
                return "out_of_stock"
            elif obj.stock <= 10:
                return "low_stock"
            return "in_stock"

    def get_total_stock(self, obj):
        if obj.has_variants:
            return sum(v.stock for v in obj.variants.all())
        return obj.stock

    def get_primary_image(self, obj):
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image:
            request = self.context.get('request')
            return request.build_absolute_uri(
                image.image.url
            ) if request else image.image.url
        return None


class UpdateSimpleProductStockSerializer(serializers.Serializer):
    """For updating stock on a simple product (no variants)"""
    stock = serializers.IntegerField(min_value=0)

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock cannot be negative.")
        return value


class UpdateVariantStockSerializer(serializers.Serializer):
    """For updating stock on a single variant"""
    stock = serializers.IntegerField(min_value=0)

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock cannot be negative.")
        return value


class BulkStockUpdateItemSerializer(serializers.Serializer):
    """One item in a bulk stock update"""
    sku = serializers.CharField()
    stock = serializers.IntegerField(min_value=0)


class BulkStockUpdateSerializer(serializers.Serializer):
    """
    Update multiple variants' stock in one API call.
    Industry standard — vendor uploads a CSV or sends bulk update
    after receiving new inventory.
    """
    updates = BulkStockUpdateItemSerializer(many=True)

    def validate_updates(self, value):
        if len(value) == 0:
            raise serializers.ValidationError("At least one update required.")
        if len(value) > 100:
            raise serializers.ValidationError(
                "Maximum 100 updates per request."
            )
        skus = [item['sku'] for item in value]
        if len(skus) != len(set(skus)):
            raise serializers.ValidationError(
                "Duplicate SKUs found in updates."
            )
        return value
    

class RevenueChartSerializer(serializers.Serializer):
    """Daily revenue data for the last 7 or 30 days — used for charts"""
    date = serializers.DateField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    orders = serializers.IntegerField()
    payout = serializers.DecimalField(max_digits=12, decimal_places=2)


class BestSellingProductSerializer(serializers.Serializer):
    """Top selling products by units sold"""
    product_id = serializers.UUIDField()
    product_name = serializers.CharField()
    product_slug = serializers.CharField()
    total_units_sold = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payout = serializers.DecimalField(max_digits=12, decimal_places=2)


class RecentOrderSummarySerializer(serializers.Serializer):
    """Lightweight order summary for dashboard recent orders list"""
    order_id = serializers.UUIDField()
    order_number = serializers.CharField()
    status = serializers.CharField()
    payment_status = serializers.CharField()
    vendor_item_count = serializers.IntegerField()
    vendor_subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    vendor_payout = serializers.DecimalField(max_digits=10, decimal_places=2)
    created_at = serializers.DateTimeField()


class VendorDashboardSerializer(serializers.Serializer):
    """Complete vendor dashboard summary"""

    # Shop info
    shop_name = serializers.CharField()
    shop_slug = serializers.CharField()
    vendor_status = serializers.CharField()
    member_since = serializers.DateTimeField()

    # Overall stats
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payout = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_commission_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_orders = serializers.IntegerField()
    total_products = serializers.IntegerField()
    active_products = serializers.IntegerField()

    # This month stats
    this_month_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    this_month_payout = serializers.DecimalField(max_digits=12, decimal_places=2)
    this_month_orders = serializers.IntegerField()

    # Inventory alerts
    low_stock_count = serializers.IntegerField()
    out_of_stock_count = serializers.IntegerField()

    # Order status breakdown
    orders_by_status = serializers.DictField(child=serializers.IntegerField())

    # Chart data
    revenue_last_7_days = RevenueChartSerializer(many=True)
    revenue_last_30_days = RevenueChartSerializer(many=True)

    # Lists
    best_selling_products = BestSellingProductSerializer(many=True)
    recent_orders = RecentOrderSummarySerializer(many=True)