from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q
from .models import Product, Category, ProductImage, ProductVariant
from .serializers import (
    ProductListSerializer, ProductDetailSerializer,
    ProductCreateSerializer, ProductVariantCreateSerializer
)
from .permissions import IsAdminOrStaff
from django.db import models as db_models


class ProductListView(APIView):
    """
    GET  /api/products/          → public, anyone can view
    POST /api/products/          → admin only, create product

    GET /api/products/
    Supports: pagination, search, filter by category/brand/price, featured, new arrivals

    Query params:
      ?page=1
      ?search=samsung
      ?category=mobile-phones     (slug)
      ?brand=samsung              (slug)
      ?min_price=1000
      ?max_price=50000
      ?featured=true
      ?new_arrivals=true
      ?ordering=price_low | price_high | newest | discount
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrStaff()]
        return []

    @extend_schema(
        summary="List all products",
        description="Public endpoint. Supports search, category/brand/price filters, ordering and pagination.",
        parameters=[
            OpenApiParameter(name='search', type=OpenApiTypes.STR, required=False, description='Search by name, description, brand or category'),
            OpenApiParameter(name='category', type=OpenApiTypes.STR, required=False, description='Filter by category slug (e.g. mobile-phones)'),
            OpenApiParameter(name='brand', type=OpenApiTypes.STR, required=False, description='Filter by brand slug (e.g. samsung)'),
            OpenApiParameter(name='min_price', type=OpenApiTypes.NUMBER, required=False, description='Minimum price filter'),
            OpenApiParameter(name='max_price', type=OpenApiTypes.NUMBER, required=False, description='Maximum price filter'),
            OpenApiParameter(name='featured', type=OpenApiTypes.STR, required=False, description='Pass true to get only featured products'),
            OpenApiParameter(name='new_arrivals', type=OpenApiTypes.STR, required=False, description='Pass true to get products added in last 30 days'),
            OpenApiParameter(name='ordering', type=OpenApiTypes.STR, required=False, description='price_low | price_high | newest | discount'),
            OpenApiParameter(name='page', type=OpenApiTypes.INT, required=False, description='Page number (default: 1)'),
            OpenApiParameter(name='page_size', type=OpenApiTypes.INT, required=False, description='Items per page (default: 10, max: 50)'),
        ],
        responses={200: inline_serializer(
            name='ProductListResponse',
            fields={
                'count': serializers.IntegerField(),
                'page': serializers.IntegerField(),
                'page_size': serializers.IntegerField(),
                'total_pages': serializers.IntegerField(),
                'has_next': serializers.BooleanField(),
                'has_previous': serializers.BooleanField(),
                'results': ProductListSerializer(many=True),
            }
        )},
        tags=["Products"]
    )
    def get(self, request):
        queryset = Product.objects.filter(is_active=True).filter(
            db_models.Q(vendor__isnull=True) |
            db_models.Q(vendor__status='approved')
        ).select_related(
            'category', 'brand','vendor'
        ).prefetch_related('images', 'variants__attributes__attribute_type')

        # Search
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(brand__name__icontains=search) |
                Q(category__name__icontains=search) |
                Q(vendor__shop_name__icontains=search)
            )

        # Category filter
        category_slug = request.query_params.get('category')
        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug)
                subcategory_ids = list(
                    Category.objects.filter(parent=category).values_list('id', flat=True)
                )
                category_ids = [category.id] + subcategory_ids
                queryset = queryset.filter(category__id__in=category_ids)
            except Category.DoesNotExist:
                return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)

        # Brand filter
        brand_slug = request.query_params.get('brand')
        if brand_slug:
            queryset = queryset.filter(brand__slug=brand_slug)

        # Price range
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        # Featured
        featured = request.query_params.get('featured')
        if featured and featured.lower() == 'true':
            queryset = queryset.filter(is_featured=True)

        # New arrivals
        new_arrivals = request.query_params.get('new_arrivals')
        if new_arrivals and new_arrivals.lower() == 'true':
            from django.utils import timezone
            from datetime import timedelta
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))

        # Ordering
        ordering_map = {
            'price_low':  'price',
            'price_high': '-price',
            'newest':     '-created_at',
            'discount':   'discount_price',
        }
        ordering = request.query_params.get('ordering', 'newest')
        queryset = queryset.order_by(ordering_map.get(ordering, '-created_at'))

        # Pagination
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
        except ValueError:
            page, page_size = 1, 10

        page_size = min(page_size, 50)
        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size

        serializer = ProductListSerializer(
            queryset[start:end], many=True, context={'request': request}
        )
        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": end < total,
            "has_previous": page > 1,
            "results": serializer.data
        })

    @extend_schema(
        summary="Create a new product",
        description="Admin only. Creates a new product. Upload images separately via /images/ endpoint after creation.",
        request=ProductCreateSerializer,
        responses={
            201: ProductDetailSerializer,
            400: inline_serializer(
                name='ProductCreateErrorResponse',
                fields={'error': serializers.CharField()}
            ),
            403: inline_serializer(
                name='ProductCreateForbiddenResponse',
                fields={'detail': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def post(self, request):
        serializer = ProductCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            product = serializer.save()
            return Response(
                ProductDetailSerializer(product, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductDetailView(APIView):
    """
    GET    /api/products/<slug>/  → public
    PUT    /api/products/<slug>/  → admin only, full update
    PATCH  /api/products/<slug>/  → admin only, partial update
    DELETE /api/products/<slug>/  → admin only, soft delete
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminOrStaff()]
        return []

    def get_object(self, slug):
        try:
            return Product.objects.select_related('category', 'brand').prefetch_related(
                'images', 'variants__attributes__attribute_type'
            ).get(slug=slug)
        except Product.DoesNotExist:
            return None

    @extend_schema(
        summary="Get product detail",
        description="Public. Returns full product detail including all images, variants and attributes.",
        responses={
            200: ProductDetailSerializer,
            404: inline_serializer(
                name='ProductDetailNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products"]
    )
    def get(self, request, slug):
        product = self.get_object(slug)
        if not product or not product.is_active:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        summary="Full update a product",
        description="Admin only. Replaces all product fields. All fields required.",
        request=ProductCreateSerializer,
        responses={
            200: ProductDetailSerializer,
            400: inline_serializer(
                name='ProductPutErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def put(self, request, slug):
        product = self.get_object(slug)
        if not product:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductCreateSerializer(
            product, data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            product = serializer.save()
            return Response(ProductDetailSerializer(product, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Partial update a product",
        description="Admin only. Update only the fields you send. All other fields remain unchanged.",
        request=ProductCreateSerializer,
        responses={
            200: ProductDetailSerializer,
            400: inline_serializer(
                name='ProductPatchErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def patch(self, request, slug):
        product = self.get_object(slug)
        if not product:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductCreateSerializer(
            product, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            product = serializer.save()
            return Response(ProductDetailSerializer(product, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Soft delete a product",
        description="Admin only. Sets is_active=False. Product is hidden from all listings but data is preserved in DB. Can be restored anytime via admin panel.",
        responses={
            200: inline_serializer(
                name='ProductDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='ProductDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def delete(self, request, slug):
        product = self.get_object(slug)
        if not product:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        # ✅ Soft delete — hides product but keeps data in DB
        product.is_active = False
        product.save()
        return Response({"message": "Product deleted successfully."}, status=status.HTTP_200_OK)


class ProductImageUploadView(APIView):
    """
    POST   /api/products/<slug>/images/   → upload images
    DELETE /api/products/<slug>/images/<image_id>/  → delete image
    """
    permission_classes = [IsAdminOrStaff]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload product images",
        description="""
        Admin only. Upload one or more images for a product.
        Use form-data with key 'images' (type: File) — use the same key name for multiple files.
        Set is_primary=true to mark the first uploaded image as the primary/thumbnail image.
        """,
        request=inline_serializer(
            name='ProductImageUploadRequest',
            fields={
                'images': serializers.ListField(
                    child=serializers.ImageField(),
                    help_text="Upload one or more image files. Use key name: images"
                ),
                'is_primary': serializers.BooleanField(
                    required=False,
                    help_text="Set true to mark first image as primary"
                ),
                'alt_text': serializers.CharField(
                    required=False,
                    help_text="Alt text for SEO and accessibility"
                ),
            }
        ),
        responses={
            201: inline_serializer(
                name='ProductImageUploadResponse',
                fields={
                    'message': serializers.CharField(),
                    'image_ids': serializers.ListField(child=serializers.IntegerField()),
                }
            ),
            400: inline_serializer(
                name='ProductImageUploadErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        images = request.FILES.getlist('images')
        if not images:
            return Response({"error": "No images provided"}, status=status.HTTP_400_BAD_REQUEST)

        is_primary = request.data.get('is_primary', 'false').lower() == 'true'
        created = []

        for index, image_file in enumerate(images):
            img = ProductImage.objects.create(
                product=product,
                image=image_file,
                alt_text=request.data.get('alt_text', ''),
                is_primary=is_primary and index == 0,
                order=product.images.count() + index
            )
            created.append(img.id)

        return Response({
            "message": f"{len(created)} image(s) uploaded successfully.",
            "image_ids": created
        }, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Delete a product image",
        description="Admin only. Deletes a specific image by its ID. The image is removed from Cloudinary as well.",
        responses={
            200: inline_serializer(
                name='ProductImageDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='ProductImageDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def delete(self, request, slug, image_id):
        try:
            image = ProductImage.objects.get(id=image_id, product__slug=slug)
            image.delete()
            return Response({"message": "Image deleted."}, status=status.HTTP_200_OK)
        except ProductImage.DoesNotExist:
            return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)


class ProductVariantView(APIView):
    """
    POST   /api/products/<slug>/variants/         → add variant
    PUT    /api/products/<slug>/variants/<sku>/   → update variant
    DELETE /api/products/<slug>/variants/<sku>/   → delete variant
    """
    permission_classes = [IsAdminOrStaff]

    @extend_schema(
        summary="Add a variant to a product",
        description="""
        Admin only. Adds a new variant (e.g. 128GB Black) to an existing product.
        Pass attributes as a list of {attribute_type_id, value} objects.
        First get AttributeType IDs from Django admin panel.
        """,
        request=ProductVariantCreateSerializer,
        responses={
            201: inline_serializer(
                name='ProductVariantAddResponse',
                fields={
                    'message': serializers.CharField(),
                    'sku': serializers.CharField(),
                }
            ),
            400: inline_serializer(
                name='ProductVariantAddErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProductVariantCreateSerializer(
            data=request.data, context={'product': product, 'request': request}
        )
        if serializer.is_valid():
            variant = serializer.save()
            return Response(
                {"message": "Variant added.", "sku": variant.sku},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Update a product variant",
        description="Admin only. Full update of a variant by SKU. Also replaces all attributes if provided.",
        request=ProductVariantCreateSerializer,
        responses={
            200: inline_serializer(
                name='ProductVariantUpdateResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='ProductVariantUpdateNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def put(self, request, slug, sku):
        try:
            variant = ProductVariant.objects.get(sku=sku, product__slug=slug)
        except ProductVariant.DoesNotExist:
            return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProductVariantCreateSerializer(
            variant, data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Variant updated."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Delete a product variant",
        description="Admin only. Permanently deletes a variant by SKU. This is a hard delete.",
        responses={
            200: inline_serializer(
                name='ProductVariantDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='ProductVariantDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Products — Admin"]
    )
    def delete(self, request, slug, sku):
        try:
            variant = ProductVariant.objects.get(sku=sku, product__slug=slug)
            variant.delete()
            return Response({"message": "Variant deleted."}, status=status.HTTP_200_OK)
        except ProductVariant.DoesNotExist:
            return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)


class FeaturedProductsView(APIView):

    @extend_schema(
        summary="Get featured products",
        description="Public. Returns up to 10 products marked as featured. Used for homepage banners and highlights.",
        responses={200: ProductListSerializer(many=True)},
        tags=["Products"]
    )
    def get(self, request):
        products = Product.objects.filter(
            is_active=True, is_featured=True
        ).select_related('category', 'brand').prefetch_related(
            'images', 'variants__attributes__attribute_type'
        ).order_by('-created_at')[:10]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)


class NewArrivalsView(APIView):

    @extend_schema(
        summary="Get new arrivals",
        description="Public. Returns up to 20 products added in the last 30 days, ordered by newest first.",
        responses={200: ProductListSerializer(many=True)},
        tags=["Products"]
    )
    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta
        products = Product.objects.filter(
            is_active=True,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).select_related('category', 'brand').prefetch_related(
            'images', 'variants__attributes__attribute_type'
        ).order_by('-created_at')[:20]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)