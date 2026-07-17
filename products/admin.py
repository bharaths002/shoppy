from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Category, Brand, Product, ProductImage,
    ProductVariant, VariantAttribute, AttributeType
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3
    fields = ['image', 'alt_text', 'is_primary', 'order']


class VariantAttributeInline(admin.TabularInline):
    model = VariantAttribute
    extra = 2


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['sku', 'price', 'discount_price', 'stock', 'is_active', 'image']
    show_change_link = True  # click to open variant and edit its attributes


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name',  'category', 'brand', 'vendor',
        'price', 'discount_price', 'discount_percent',
        'stock', 'has_variants', 'is_active', 'is_featured'
    ]
    list_filter = ['is_active', 'is_featured', 'has_variants', 'category', 'brand', 'vendor']
    search_fields = ['name', 'description','vendor__shop_name']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['is_active', 'is_featured', 'price', 'discount_price']
    inlines = [ProductImageInline, ProductVariantInline]

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'description', 'category', 'brand')
        }),
        ('Vendor', {
            'fields': ('vendor',),
            'description': 'Leave blank for platform-owned products'
        }),
        ('Pricing', {
            'fields': ('price', 'discount_price')
        }),
        ('Inventory', {
            'fields': ('stock', 'has_variants')
        }),
        ('Visibility', {
            'fields': ('is_active', 'is_featured')
        }),
    )

    def discount_percent(self, obj):
        pct = obj.discount_percent
        if pct:
            return format_html('<span style="color:green;font-weight:bold">{}% off</span>', pct)
        return '-'
    discount_percent.short_description = 'Discount'


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'sku', 'effective_price', 'stock', 'is_active']
    search_fields = ['sku', 'product__name']
    inlines = [VariantAttributeInline]


@admin.register(AttributeType)
class AttributeTypeAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']