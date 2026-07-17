from rest_framework import serializers
from .models import Cart, CartItem
from products.models import Product, ProductVariant


class CartItemProductSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    primary_image = serializers.SerializerMethodField()

    def get_primary_image(self, obj):
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image:
            request = self.context.get('request')
            return request.build_absolute_uri(image.image.url) if request else image.image.url
        return None


class CartItemVariantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    attributes = serializers.SerializerMethodField()

    def get_attributes(self, obj):
        return [
            {"attribute": a.attribute_type.name, "value": a.value}
            for a in obj.attributes.select_related('attribute_type').all()
        ]


# ✅ Fixed — using SerializerMethodField to pass context manually
class CartItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    variant = serializers.SerializerMethodField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'variant',
            'quantity', 'unit_price', 'line_total',
            'added_at'
        ]

    def get_product(self, obj):
        return CartItemProductSerializer(
            obj.product, context=self.context
        ).data

    def get_variant(self, obj):
        if obj.variant:
            return CartItemVariantSerializer(
                obj.variant, context=self.context
            ).data
        return None


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True)
    total_items = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = Cart
        fields = ['id', 'total_items', 'subtotal', 'items', 'updated_at']


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, data):
        try:
            product = Product.objects.get(id=data['product_id'], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Product not found or inactive."})

        variant = None
        if data.get('variant_id'):
            try:
                variant = ProductVariant.objects.get(
                    id=data['variant_id'], product=product, is_active=True
                )
            except ProductVariant.DoesNotExist:
                raise serializers.ValidationError({"variant_id": "Variant not found."})

        if variant:
            if variant.stock < data['quantity']:
                raise serializers.ValidationError(
                    {"quantity": f"Only {variant.stock} item(s) in stock."}
                )
        else:
            if product.has_variants:
                raise serializers.ValidationError(
                    {"variant_id": "This product has variants. Please select a variant."}
                )
            if product.stock < data['quantity']:
                raise serializers.ValidationError(
                    {"quantity": f"Only {product.stock} item(s) in stock."}
                )

        data['product'] = product
        data['variant'] = variant
        return data


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)