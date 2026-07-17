from django.db import models
from django.utils.text import slugify
from accounts.models import VendorProfile

import uuid


class Category(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subcategories'
    )
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.parent.name} > {self.name}" if self.parent else self.name

    class Meta:
        verbose_name_plural = "Categories"


class Brand(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    logo = models.ImageField(upload_to='brands/', null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, related_name='products'
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='products'
    )

    #New — vendor FK
    # null=True means platform products (admin-owned) have no vendor
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        help_text="Leave blank for platform-owned products"
    )

    # Price
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )

    # For simple products with no variants
    stock = models.PositiveIntegerField(default=0)

    has_variants = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) + '-' + str(self.id)[:8]
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.discount_price if self.discount_price else self.price

    @property
    def discount_percent(self):
        if self.discount_price and self.price:
            return round((1 - self.discount_price / self.price) * 100)
        return 0

    @property
    def is_in_stock(self):
        if self.has_variants:
            return self.variants.filter(stock__gt=0).exists()
        return self.stock > 0
    
    @property
    def is_vendor_product(self):
        return self.vendor is not None

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images'
    )
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        # ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - image {self.order}"

    class Meta:
        ordering = ['order']


class AttributeType(models.Model):
    """e.g. Size, Color, Storage, Material"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='variants'
    )
    sku = models.CharField(max_length=100, unique=True, blank=True)

    # Price override — if blank, use parent product price
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    discount_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(
        upload_to='variants/', null=True, blank=True
    )

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = str(uuid.uuid4())[:12].upper()
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        base = self.price or self.product.price
        discounted = self.discount_price or self.product.discount_price
        return discounted if discounted else base

    def __str__(self):
        attrs = self.attributes.select_related('attribute_type').all()
        attr_str = ', '.join(f"{a.attribute_type.name}: {a.value}" for a in attrs)
        return f"{self.product.name} — {attr_str}"


class VariantAttribute(models.Model):
    """e.g. Size: XL, Color: Red"""
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name='attributes'
    )
    attribute_type = models.ForeignKey(
        AttributeType, on_delete=models.CASCADE
    )
    value = models.CharField(max_length=100)  # "XL", "Red", "128GB"

    class Meta:
        unique_together = ('variant', 'attribute_type')

    def __str__(self):
        return f"{self.attribute_type.name}: {self.value}"