from rest_framework import serializers
from .models import Product, ProductImage, ProductVariant, VariantAttribute, Category, Brand, AttributeType


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug']

class ProductVendorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    shop_name = serializers.CharField()
    shop_slug = serializers.CharField()

class VariantAttributeSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source='attribute_type.name')

    class Meta:
        model = VariantAttribute
        fields = ['attribute_name', 'value']


class ProductVariantSerializer(serializers.ModelSerializer):
    attributes = VariantAttributeSerializer(many=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = ProductVariant
        fields = ['id', 'sku', 'price', 'discount_price', 'effective_price',
                  'stock', 'is_active', 'image', 'attributes']


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    brand = BrandSerializer()
    vendor = ProductVendorSerializer()
    primary_image = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField()
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    is_in_stock = serializers.BooleanField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'category', 'brand', 'vendor',
            'price', 'discount_price', 'effective_price', 'discount_percent',
            'primary_image', 'is_in_stock', 'is_featured', 'created_at'
        ]

    def get_primary_image(self, obj):
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image:
            request = self.context.get('request')
            return request.build_absolute_uri(image.image.url) if request else image.image.url
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    brand = BrandSerializer()
    vendor = ProductVendorSerializer() 
    images = ProductImageSerializer(many=True)
    variants = ProductVariantSerializer(many=True)
    discount_percent = serializers.IntegerField()
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    is_in_stock = serializers.BooleanField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand', 'vendor',
            'price', 'discount_price', 'effective_price', 'discount_percent',
            'stock', 'has_variants', 'is_in_stock', 'is_active', 'is_featured',
            'images', 'variants', 'created_at', 'updated_at'
        ]


# ✅ New — for creating and updating products
class ProductCreateSerializer(serializers.ModelSerializer):
    # Accept category and brand by ID
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    brand = serializers.PrimaryKeyRelatedField(queryset=Brand.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'brand',
            'price', 'discount_price', 'stock',
            'has_variants', 'is_active', 'is_featured'
        ]

    def validate(self, data):
        price = data.get('price')
        discount_price = data.get('discount_price')
        if discount_price and price and discount_price >= price:
            raise serializers.ValidationError(
                {"discount_price": "Discount price must be less than original price."}
            )
        return data

    def create(self, validated_data):
        product = Product.objects.create(**validated_data)
        return product

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ✅ New — for creating and updating variants
class ProductVariantCreateSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    discount_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    stock = serializers.IntegerField(default=0)
    is_active = serializers.BooleanField(default=True)
    # attributes: [{"attribute_type_id": 1, "value": "128GB"}, ...]
    attributes = serializers.ListField(
        child=serializers.DictField(), required=False
    )

    def validate(self, data):
        price = data.get('price')
        discount_price = data.get('discount_price')
        if discount_price and price and discount_price >= price:
            raise serializers.ValidationError(
                {"discount_price": "Discount price must be less than original price."}
            )
        return data

    def create(self, validated_data):
        attributes_data = validated_data.pop('attributes', [])
        product = self.context['product']
        variant = ProductVariant.objects.create(product=product, **validated_data)

        for attr in attributes_data:
            attr_type = AttributeType.objects.filter(id=attr.get('attribute_type_id')).first()
            if attr_type:
                VariantAttribute.objects.create(
                    variant=variant,
                    attribute_type=attr_type,
                    value=attr.get('value', '')
                )
        return variant

    def update(self, instance, validated_data):
        attributes_data = validated_data.pop('attributes', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if attributes_data:
            instance.attributes.all().delete()
            for attr in attributes_data:
                attr_type = AttributeType.objects.filter(id=attr.get('attribute_type_id')).first()
                if attr_type:
                    VariantAttribute.objects.create(
                        variant=instance,
                        attribute_type=attr_type,
                        value=attr.get('value', '')
                    )
        return instance