import secrets
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.core.mail import send_mail
from accounts.models import OTP, VendorProfile, User
from products.models import (
    Product, ProductImage, ProductVariant
)
from products.serializers import (
    ProductListSerializer, ProductDetailSerializer,
    ProductCreateSerializer, ProductVariantCreateSerializer
)
from .serializers import (
    VendorRegistrationSerializer,
    VendorProfileSerializer,
    UpdateVendorProfileSerializer,ProductInventorySerializer
)
from .permissions import IsVendor
from orders.models import Order, OrderItem, OrderStatusHistory
from orders.serializers import (
    VendorOrderSerializer,
    VendorOrderDetailSerializer
)






def get_user_role_data(user):
    """
    Helper — returns role and vendor status for login responses.
    Reused in both customer and vendor login flows.
    """
    role_data = {
        "role": user.role,
        "vendor_profile": None
    }

    if user.role == 'vendor' and hasattr(user, 'vendor_profile'):
        vp = user.vendor_profile
        role_data["vendor_profile"] = {
            "shop_name": vp.shop_name,
            "shop_slug": vp.shop_slug,
            "status": vp.status,
            "is_active": vp.is_active,
            "rejection_reason": vp.rejection_reason if vp.status == 'rejected' else None,
        }

    if user.is_superuser or user.is_staff:
        role_data["role"] = "admin"

    return role_data


class VendorRegisterView(APIView):
    """
    POST /api/vendors/register/
    Step 2 of vendor registration — verifies OTP and creates
    both User and VendorProfile in one atomic operation.

    Step 1 is: POST /api/accounts/sendotp/ { "email": "vendor@gmail.com" }
    That reuses existing OTP infrastructure — no changes needed there.
    """

    @extend_schema(
        summary="Register as a vendor",
        description="""
        Step 2 of vendor registration.
        Step 1: Call POST /api/accounts/sendotp/ with your email first.
        Step 2: Call this endpoint with the OTP + all shop details.

        On success: User is created with role=vendor,
        VendorProfile is created with status=pending.
        Admin must approve before vendor can list products.
        """,
        request=VendorRegistrationSerializer,
        responses={
            201: inline_serializer(
                name='VendorRegisterResponse',
                fields={
                    'message': serializers.CharField(),
                    'access': serializers.CharField(),
                    'refresh': serializers.CharField(),
                    'role': serializers.CharField(),
                    'vendor_profile': VendorProfileSerializer(),
                }
            ),
            400: inline_serializer(
                name='VendorRegisterErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Auth"]
    )
    def post(self, request):
        serializer = VendorRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data['email']

        # ── Verify OTP ────────────────────────────────────────
        otp_obj = OTP.objects.filter(
            contact=email, is_verified=False
        ).order_by('-created_at').first()

        if not otp_obj:
            return Response(
                {"error": "OTP not found. Please request a new OTP first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.attempts >= 5:
            otp_obj.delete()
            return Response(
                {"error": "Too many failed attempts. Please request a new OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.is_expired():
            otp_obj.delete()
            return Response(
                {"error": "OTP has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.otp != data['otp']:
            otp_obj.attempts += 1
            otp_obj.save()
            remaining = 5 - otp_obj.attempts
            return Response(
                {"error": f"Invalid OTP. {remaining} attempt(s) remaining."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # OTP is valid
        otp_obj.is_verified = True
        otp_obj.save()

        # ── Check if user already exists ──────────────────────
        user = User.objects.filter(email=email).first()

        if user and hasattr(user, 'vendor_profile'):
            return Response(
                {"error": "A vendor account already exists with this email."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user and user.role == 'customer':
            return Response(
                {"error": "This email is already registered as a customer account. Please use a different email for vendor registration."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Create User + VendorProfile ───────────────────────
        if not user:
            user = User.objects.create(
                email=email,
                username=email.split('@')[0] + str(secrets.randbelow(9999)),
                role='vendor',
                is_verified=True
            )
        else:
            user.role = 'vendor'
            user.is_verified = True
            user.save()

        vendor_profile = VendorProfile.objects.create(
            user=user,
            shop_name=data['shop_name'],
            shop_description=data.get('shop_description', ''),
            business_type=data['business_type'],
            gstin=data.get('gstin', ''),
            pan_number=data.get('pan_number', ''),
            business_phone=data['business_phone'],
            business_email=data['business_email'],
            business_address=data.get('business_address', ''),
            status='pending',
            is_active=False
        )

        # ── Notify admin via email ────────────────────────────
        try:
            send_mail(
                subject="New Vendor Registration — Pending Approval",
                message=f"""
A new vendor has registered and is awaiting approval.

Shop Name: {vendor_profile.shop_name}
Email: {email}
Business Type: {vendor_profile.business_type}
GSTIN: {vendor_profile.gstin or 'Not provided'}

Please login to the admin panel to review and approve:
http://127.0.0.1:8000/admin/accounts/vendorprofile/
                """,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[settings.EMAIL_HOST_USER],
                fail_silently=True
            )
        except Exception:
            pass  # Don't block registration if email fails

        # ── Generate JWT tokens ───────────────────────────────
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Vendor registration successful. Your application is under review. You will be notified once approved.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "role": "vendor",
                "vendor_profile": VendorProfileSerializer(vendor_profile).data,
            },
            status=status.HTTP_201_CREATED
        )


class VendorProfileView(APIView):
    """
    GET   /api/vendors/profile/   → view own vendor profile
    PATCH /api/vendors/profile/   → update own shop info
    """
    permission_classes = [IsAuthenticated]

    def get_vendor_profile(self, user):
        try:
            return user.vendor_profile
        except VendorProfile.DoesNotExist:
            return None

    @extend_schema(
        summary="Get my vendor profile",
        description="Returns the vendor profile for the logged-in vendor.",
        responses={
            200: VendorProfileSerializer,
            403: inline_serializer(
                name='VendorProfileForbiddenResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Profile"]
    )
    def get(self, request):
        vendor = self.get_vendor_profile(request.user)
        if not vendor:
            return Response(
                {"error": "No vendor profile found. Please register as a vendor first."},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VendorProfileSerializer(vendor)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update my vendor profile",
        description="""
        Vendors can update their shop description, logo, banner,
        and contact details. Cannot change shop name, status or commission rate.
        """,
        request=UpdateVendorProfileSerializer,
        responses={
            200: VendorProfileSerializer,
            403: inline_serializer(
                name='VendorProfileUpdateForbiddenResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Profile"]
    )
    def patch(self, request):
        vendor = self.get_vendor_profile(request.user)
        if not vendor:
            return Response(
                {"error": "No vendor profile found."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = UpdateVendorProfileSerializer(
            vendor, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            VendorProfileSerializer(vendor).data,
            status=status.HTTP_200_OK
        )
    


# ─────────────────────────────────────────────────────────────
# Vendor Product Management
# ─────────────────────────────────────────────────────────────

class VendorProductListView(APIView):
    """
    GET  /api/vendors/products/   → vendor sees only their own products
    POST /api/vendors/products/   → vendor creates a new product
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="List my products",
        description="""
        Vendor sees only their own products.
        Supports search, filter by category, is_active status.
        """,
        parameters=[
            OpenApiParameter(name='search', type=OpenApiTypes.STR, required=False),
            OpenApiParameter(name='is_active', type=OpenApiTypes.BOOL, required=False),
            OpenApiParameter(name='page', type=OpenApiTypes.INT, required=False),
            OpenApiParameter(name='page_size', type=OpenApiTypes.INT, required=False),
        ],
        responses={200: inline_serializer(
            name='VendorProductListResponse',
            fields={
                'count': serializers.IntegerField(),
                'page': serializers.IntegerField(),
                'total_pages': serializers.IntegerField(),
                'results': ProductListSerializer(many=True),
            }
        )},
        tags=["Vendor — Products"]
    )
    def get(self, request):
        vendor = request.user.vendor_profile

        # ✅ Always scoped to this vendor only
        queryset = Product.objects.filter(
            vendor=vendor
        ).select_related(
            'category', 'brand', 'vendor'
        ).prefetch_related(
            'images', 'variants__attributes__attribute_type'
        )

        # Search
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )

        # Filter by active status
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Ordering
        queryset = queryset.order_by('-created_at')

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
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Create a product",
        description="""
        Vendor creates a new product under their shop.
        Vendor is automatically set from the logged-in user — no need to pass it.
        Product starts as inactive by default — vendor must activate after adding images and variants.
        """,
        request=ProductCreateSerializer,
        responses={
            201: ProductDetailSerializer,
            400: inline_serializer(
                name='VendorProductCreateErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def post(self, request):
        vendor = request.user.vendor_profile

        serializer = ProductCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Vendor is automatically set — vendor cannot spoof another vendor's ID
        product = serializer.save(vendor=vendor, is_active=False)

        return Response(
            ProductDetailSerializer(product, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class VendorProductDetailView(APIView):
    """
    GET    /api/vendors/products/<slug>/   → view own product
    PATCH  /api/vendors/products/<slug>/   → update own product
    DELETE /api/vendors/products/<slug>/   → soft delete own product
    """
    permission_classes = [IsVendor]

    def get_product(self, slug, vendor):
        """
        ✅ Critical security — always filter by BOTH slug AND vendor.
        A vendor cannot access another vendor's product even if they know the slug.
        """
        try:
            return Product.objects.select_related(
                'category', 'brand', 'vendor'
            ).prefetch_related(
                'images', 'variants__attributes__attribute_type'
            ).get(slug=slug, vendor=vendor)
        except Product.DoesNotExist:
            return None

    @extend_schema(
        summary="Get my product detail",
        description="Vendor views their own product. Returns 404 if product belongs to another vendor.",
        responses={
            200: ProductDetailSerializer,
            404: inline_serializer(
                name='VendorProductNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def get(self, request, slug):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update my product",
        description="Vendor can update their own product. Cannot change vendor ownership.",
        request=ProductCreateSerializer,
        responses={
            200: ProductDetailSerializer,
            404: inline_serializer(
                name='VendorProductUpdateNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def patch(self, request, slug):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductCreateSerializer(
            product, data=request.data,
            partial=True, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            ProductDetailSerializer(product, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Delete my product",
        description="Soft delete. Sets is_active=False. Product hidden from customers but data preserved.",
        responses={
            200: inline_serializer(
                name='VendorProductDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
            404: inline_serializer(
                name='VendorProductDeleteNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def delete(self, request, slug):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        product.is_active = False
        product.save()
        return Response(
            {"message": "Product deactivated successfully."},
            status=status.HTTP_200_OK
        )


class VendorProductImageView(APIView):
    """
    POST   /api/vendors/products/<slug>/images/            → upload images
    DELETE /api/vendors/products/<slug>/images/<image_id>/ → delete image
    """
    from rest_framework.parsers import MultiPartParser, FormParser
    permission_classes = [IsVendor]
    parser_classes = [MultiPartParser, FormParser]

    def get_product(self, slug, vendor):
        try:
            return Product.objects.get(slug=slug, vendor=vendor)
        except Product.DoesNotExist:
            return None

    @extend_schema(
        summary="Upload images to my product",
        description="Use form-data. Key name must be 'images' for all files.",
        request=inline_serializer(
            name='VendorImageUploadRequest',
            fields={
                'images': serializers.ListField(child=serializers.ImageField()),
                'is_primary': serializers.BooleanField(required=False),
                'alt_text': serializers.CharField(required=False),
            }
        ),
        responses={
            201: inline_serializer(
                name='VendorImageUploadResponse',
                fields={
                    'message': serializers.CharField(),
                    'image_ids': serializers.ListField(child=serializers.IntegerField()),
                }
            ),
        },
        tags=["Vendor — Products"]
    )
    def post(self, request, slug):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        images = request.FILES.getlist('images')
        if not images:
            return Response(
                {"error": "No images provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

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
            "message": f"{len(created)} image(s) uploaded.",
            "image_ids": created
        }, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Delete image from my product",
        responses={
            200: inline_serializer(
                name='VendorImageDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def delete(self, request, slug, image_id):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        try:
            image = ProductImage.objects.get(id=image_id, product=product)
            image.delete()
            return Response(
                {"message": "Image deleted."},
                status=status.HTTP_200_OK
            )
        except ProductImage.DoesNotExist:
            return Response(
                {"error": "Image not found."},
                status=status.HTTP_404_NOT_FOUND
            )


class VendorVariantView(APIView):
    """
    POST   /api/vendors/products/<slug>/variants/          → add variant
    PATCH  /api/vendors/products/<slug>/variants/<sku>/    → update variant
    DELETE /api/vendors/products/<slug>/variants/<sku>/    → delete variant
    """
    permission_classes = [IsVendor]

    def get_product(self, slug, vendor):
        try:
            return Product.objects.get(slug=slug, vendor=vendor)
        except Product.DoesNotExist:
            return None

    @extend_schema(
        summary="Add variant to my product",
        request=ProductVariantCreateSerializer,
        responses={
            201: inline_serializer(
                name='VendorVariantAddResponse',
                fields={
                    'message': serializers.CharField(),
                    'sku': serializers.CharField(),
                }
            ),
        },
        tags=["Vendor — Products"]
    )
    def post(self, request, slug):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductVariantCreateSerializer(
            data=request.data,
            context={'product': product, 'request': request}
        )
        if serializer.is_valid():
            variant = serializer.save()
            return Response(
                {"message": "Variant added.", "sku": variant.sku},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Update my product variant",
        request=ProductVariantCreateSerializer,
        responses={
            200: inline_serializer(
                name='VendorVariantUpdateResponse',
                fields={'message': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def patch(self, request, slug, sku):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        try:
            variant = ProductVariant.objects.get(sku=sku, product=product)
        except ProductVariant.DoesNotExist:
            return Response(
                {"error": "Variant not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductVariantCreateSerializer(
            variant, data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Variant updated."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Delete my product variant",
        responses={
            200: inline_serializer(
                name='VendorVariantDeleteResponse',
                fields={'message': serializers.CharField()}
            ),
        },
        tags=["Vendor — Products"]
    )
    def delete(self, request, slug, sku):
        product = self.get_product(slug, request.user.vendor_profile)
        if not product:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        try:
            variant = ProductVariant.objects.get(sku=sku, product=product)
            variant.delete()
            return Response(
                {"message": "Variant deleted."},
                status=status.HTTP_200_OK
            )
        except ProductVariant.DoesNotExist:
            return Response(
                {"error": "Variant not found."},
                status=status.HTTP_404_NOT_FOUND
            )    
        

class VendorOrderListView(APIView):
    """
    GET /api/vendors/orders/
    Vendor sees only orders that contain at least one of their products.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="List my orders",
        description="""
        Returns all orders containing at least one product from this vendor's shop.
        Each order shows only this vendor's items — not items from other vendors.
        """,
        parameters=[
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                required=False,
                description='Filter by order status: pending | confirmed | shipped | delivered | cancelled | returned'
            ),
            OpenApiParameter(
                name='page', type=OpenApiTypes.INT, required=False
            ),
        ],
        responses={200: inline_serializer(
            name='VendorOrderListResponse',
            fields={
                'count': serializers.IntegerField(),
                'page': serializers.IntegerField(),
                'total_pages': serializers.IntegerField(),
                'results': VendorOrderSerializer(many=True),
            }
        )},
        tags=["Vendor — Orders"]
    )
    def get(self, request):
        vendor = request.user.vendor_profile

        # ✅ Find orders that have at least one item belonging to this vendor
        orders = Order.objects.filter(
            items__vendor=vendor
        ).distinct().order_by('-created_at')

        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            orders = orders.filter(status=status_filter)

        # Pagination
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
        except ValueError:
            page, page_size = 1, 10

        page_size = min(page_size, 50)
        total = orders.count()
        start = (page - 1) * page_size
        end = start + page_size

        serializer = VendorOrderSerializer(
            orders[start:end],
            many=True,
            context={'request': request, 'vendor': vendor}  # ✅ pass vendor for item filtering
        )

        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": end < total,
            "has_previous": page > 1,
            "results": serializer.data
        }, status=status.HTTP_200_OK)


class VendorOrderDetailView(APIView):
    """
    GET /api/vendors/orders/<order_id>/
    Full detail of one order — only this vendor's items shown.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Get order detail",
        description="""
        Returns full detail of an order containing this vendor's products.
        Only this vendor's items are shown — other vendors' items are hidden.
        Full shipping address visible only after order is confirmed.
        Returns 404 if this order has no items from this vendor.
        """,
        responses={
            200: VendorOrderDetailSerializer,
            404: inline_serializer(
                name='VendorOrderNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Orders"]
    )
    def get(self, request, order_id):
        vendor = request.user.vendor_profile

        # ✅ Security — vendor can only access orders containing their items
        order = Order.objects.filter(
            id=order_id,
            items__vendor=vendor
        ).distinct().select_related(
            'shipping_address', 'billing_address'
        ).prefetch_related('items', 'status_history').first()

        if not order:
            return Response(
                {"error": "Order not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = VendorOrderDetailSerializer(
            order,
            context={'request': request, 'vendor': vendor}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class VendorUpdateOrderItemStatusView(APIView):
    """
    PATCH /api/vendors/orders/<order_id>/items/<item_id>/status/
    Vendor updates the status of their own order items.
    For example: marking an item as shipped after dispatching.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Update order item status",
        description="""
        Vendor can update status of their own order items only.
        This is separate from the full order status which admin controls.
        Useful for tracking per-vendor fulfillment in a multi-vendor order.
        Valid statuses: confirmed | shipped | delivered | cancelled
        """,
        request=inline_serializer(
            name='VendorItemStatusUpdateRequest',
            fields={
                'status': serializers.ChoiceField(
                    choices=['confirmed', 'shipped', 'delivered', 'cancelled']
                ),
                'note': serializers.CharField(required=False),
            }
        ),
        responses={
            200: inline_serializer(
                name='VendorItemStatusUpdateResponse',
                fields={'message': serializers.CharField()}
            ),
            403: inline_serializer(
                name='VendorItemStatusForbiddenResponse',
                fields={'error': serializers.CharField()}
            ),
            404: inline_serializer(
                name='VendorItemStatusNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Orders"]
    )
    def patch(self, request, order_id, item_id):
        vendor = request.user.vendor_profile

        # ✅ Vendor can only update their own items
        try:
            item = OrderItem.objects.get(
                id=item_id,
                order__id=order_id,
                vendor=vendor
            )
        except OrderItem.DoesNotExist:
            return Response(
                {"error": "Order item not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get('status')
        valid_statuses = ['confirmed', 'shipped', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return Response(
                {"error": f"Invalid status. Valid options: {', '.join(valid_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        note = request.data.get('note', f"Updated by vendor: {vendor.shop_name}")

        # Log on the parent order's history
        OrderStatusHistory.objects.create(
            order=item.order,
            status=new_status,
            note=f"{item.product_name}: {note}"
        )

        return Response(
            {"message": f"Item status updated to '{new_status}'."},
            status=status.HTTP_200_OK
        )        
    

class VendorInventoryView(APIView):
    """
    GET /api/vendors/inventory/
    Vendor sees full inventory snapshot of all their products.
    Supports filtering by stock_status and search.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="View my inventory",
        description="""
        Returns full inventory snapshot for all vendor products.
        Each product shows stock levels, stock status labels,
        and per-variant breakdown for variant products.

        Stock status labels:
        - in_stock     → 11+ units
        - low_stock    → 1-10 units (should restock)
        - out_of_stock → 0 units
        """,
        parameters=[
            OpenApiParameter(
                name='stock_status',
                type=OpenApiTypes.STR,
                required=False,
                description='Filter: in_stock | low_stock | out_of_stock'
            ),
            OpenApiParameter(
                name='search',
                type=OpenApiTypes.STR,
                required=False,
                description='Search by product name or SKU'
            ),
            OpenApiParameter(
                name='page',
                type=OpenApiTypes.INT,
                required=False
            ),
        ],
        responses={200: inline_serializer(
            name='VendorInventoryResponse',
            fields={
                'summary': inline_serializer(
                    name='InventorySummary',
                    fields={
                        'total_products': serializers.IntegerField(),
                        'in_stock': serializers.IntegerField(),
                        'low_stock': serializers.IntegerField(),
                        'out_of_stock': serializers.IntegerField(),
                        'total_stock_value': serializers.DecimalField(
                            max_digits=12, decimal_places=2
                        ),
                    }
                ),
                'products': ProductInventorySerializer(many=True),
            }
        )},
        tags=["Vendor — Inventory"]
    )
    def get(self, request):
        from .serializers import ProductInventorySerializer
        vendor = request.user.vendor_profile

        # ✅ Always scoped to this vendor
        queryset = Product.objects.filter(
            vendor=vendor
        ).prefetch_related(
            'images',
            'variants__attributes__attribute_type'
        ).order_by('name')

        # Search by name
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(variants__sku__icontains=search)
            ).distinct()

        # Filter by stock status
        stock_status_filter = request.query_params.get('stock_status')
        all_products = list(queryset)

        if stock_status_filter:
            filtered = []
            for product in all_products:
                if product.has_variants:
                    total = sum(v.stock for v in product.variants.all())
                else:
                    total = product.stock

                if stock_status_filter == 'out_of_stock' and total == 0:
                    filtered.append(product)
                elif stock_status_filter == 'low_stock' and 1 <= total <= 10:
                    filtered.append(product)
                elif stock_status_filter == 'in_stock' and total > 10:
                    filtered.append(product)
            all_products = filtered

        # Build inventory summary
        total_products = len(all_products)
        in_stock_count = 0
        low_stock_count = 0
        out_of_stock_count = 0
        total_stock_value = 0

        for product in all_products:
            if product.has_variants:
                total = sum(v.stock for v in product.variants.all())
                # Stock value = sum of (variant effective price × stock)
                for v in product.variants.all():
                    total_stock_value += float(v.effective_price) * v.stock
            else:
                total = product.stock
                total_stock_value += float(product.effective_price) * product.stock

            if total == 0:
                out_of_stock_count += 1
            elif total <= 10:
                low_stock_count += 1
            else:
                in_stock_count += 1

        # Pagination
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
        except ValueError:
            page, page_size = 1, 20

        page_size = min(page_size, 50)
        total = len(all_products)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = all_products[start:end]

        serializer = ProductInventorySerializer(
            paginated, many=True, context={'request': request}
        )

        return Response({
            "summary": {
                "total_products": total_products,
                "in_stock": in_stock_count,
                "low_stock": low_stock_count,
                "out_of_stock": out_of_stock_count,
                "total_stock_value": round(total_stock_value, 2),
            },
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": end < total,
            "has_previous": page > 1,
            "products": serializer.data
        }, status=status.HTTP_200_OK)


class VendorUpdateProductStockView(APIView):
    """
    PATCH /api/vendors/inventory/<slug>/stock/
    Update stock for a simple product (no variants).
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Update product stock",
        description="""
        Update stock for a simple product (no variants).
        For variant products use the variant stock endpoint instead.
        """,
        request=inline_serializer(
            name='UpdateSimpleStockRequest',
            fields={'stock': serializers.IntegerField(min_value=0)}
        ),
        responses={
            200: inline_serializer(
                name='UpdateSimpleStockResponse',
                fields={
                    'message': serializers.CharField(),
                    'product': serializers.CharField(),
                    'stock': serializers.IntegerField(),
                    'stock_status': serializers.CharField(),
                }
            ),
            400: inline_serializer(
                name='UpdateSimpleStockErrorResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Inventory"]
    )
    def patch(self, request, slug):
        vendor = request.user.vendor_profile

        try:
            product = Product.objects.get(slug=slug, vendor=vendor)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        if product.has_variants:
            return Response(
                {"error": "This product has variants. Update stock per variant using /inventory/<slug>/variants/<sku>/stock/"},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .serializers import UpdateSimpleProductStockSerializer
        serializer = UpdateSimpleProductStockSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        old_stock = product.stock
        new_stock = serializer.validated_data['stock']
        product.stock = new_stock
        product.save()

        # Determine stock status
        if new_stock == 0:
            stock_status = "out_of_stock"
        elif new_stock <= 10:
            stock_status = "low_stock"
        else:
            stock_status = "in_stock"

        return Response({
            "message": f"Stock updated from {old_stock} to {new_stock}.",
            "product": product.name,
            "stock": new_stock,
            "stock_status": stock_status,
        }, status=status.HTTP_200_OK)


class VendorUpdateVariantStockView(APIView):
    """
    PATCH /api/vendors/inventory/<slug>/variants/<sku>/stock/
    Update stock for a specific variant.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Update variant stock",
        description="Update stock for a specific product variant by SKU.",
        request=inline_serializer(
            name='UpdateVariantStockRequest',
            fields={'stock': serializers.IntegerField(min_value=0)}
        ),
        responses={
            200: inline_serializer(
                name='UpdateVariantStockResponse',
                fields={
                    'message': serializers.CharField(),
                    'product': serializers.CharField(),
                    'sku': serializers.CharField(),
                    'stock': serializers.IntegerField(),
                    'stock_status': serializers.CharField(),
                }
            ),
            404: inline_serializer(
                name='UpdateVariantStockNotFoundResponse',
                fields={'error': serializers.CharField()}
            ),
        },
        tags=["Vendor — Inventory"]
    )
    def patch(self, request, slug, sku):
        vendor = request.user.vendor_profile

        # ✅ Validate product belongs to this vendor first
        try:
            product = Product.objects.get(slug=slug, vendor=vendor)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Then validate variant belongs to that product
        try:
            variant = ProductVariant.objects.get(sku=sku, product=product)
        except ProductVariant.DoesNotExist:
            return Response(
                {"error": "Variant not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        from .serializers import UpdateVariantStockSerializer
        serializer = UpdateVariantStockSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        old_stock = variant.stock
        new_stock = serializer.validated_data['stock']
        variant.stock = new_stock
        variant.save()

        if new_stock == 0:
            stock_status = "out_of_stock"
        elif new_stock <= 10:
            stock_status = "low_stock"
        else:
            stock_status = "in_stock"

        return Response({
            "message": f"Variant stock updated from {old_stock} to {new_stock}.",
            "product": product.name,
            "sku": variant.sku,
            "stock": new_stock,
            "stock_status": stock_status,
        }, status=status.HTTP_200_OK)


class VendorBulkStockUpdateView(APIView):
    """
    POST /api/vendors/inventory/bulk-update/
    Update multiple variants' stock in a single request.
    Industry standard — vendor uploads new inventory after receiving shipment.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Bulk update stock",
        description="""
        Update stock for multiple variants in one API call.
        Maximum 100 updates per request.
        Only updates variants belonging to this vendor — unknown or other vendors' SKUs are skipped safely.

        Example:
        {
            "updates": [
                {"sku": "ABC123DEF456", "stock": 50},
                {"sku": "XYZ789GHI012", "stock": 0},
                {"sku": "MNO345PQR678", "stock": 25}
            ]
        }
        """,
        request=inline_serializer(
            name='BulkStockUpdateRequest',
            fields={
                'updates': inline_serializer(
                    name='BulkStockUpdateItem',
                    fields={
                        'sku': serializers.CharField(),
                        'stock': serializers.IntegerField(min_value=0),
                    },
                    many=True
                )
            }
        ),
        responses={
            200: inline_serializer(
                name='BulkStockUpdateResponse',
                fields={
                    'message': serializers.CharField(),
                    'updated_count': serializers.IntegerField(),
                    'skipped_count': serializers.IntegerField(),
                    'skipped_skus': serializers.ListField(
                        child=serializers.CharField()
                    ),
                    'results': inline_serializer(
                        name='BulkStockUpdateResult',
                        fields={
                            'sku': serializers.CharField(),
                            'product': serializers.CharField(),
                            'old_stock': serializers.IntegerField(),
                            'new_stock': serializers.IntegerField(),
                            'stock_status': serializers.CharField(),
                        },
                        many=True
                    )
                }
            ),
        },
        tags=["Vendor — Inventory"]
    )
    def post(self, request):
        from .serializers import BulkStockUpdateSerializer
        vendor = request.user.vendor_profile

        serializer = BulkStockUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updates = serializer.validated_data['updates']
        results = []
        skipped_skus = []
        updated_count = 0

        for update in updates:
            sku = update['sku']
            new_stock = update['stock']

            # ✅ Only update variants belonging to this vendor's products
            variant = ProductVariant.objects.filter(
                sku=sku,
                product__vendor=vendor
            ).select_related('product').first()

            if not variant:
                # SKU not found or belongs to another vendor — skip silently
                skipped_skus.append(sku)
                continue

            old_stock = variant.stock
            variant.stock = new_stock
            variant.save()
            updated_count += 1

            if new_stock == 0:
                stock_status = "out_of_stock"
            elif new_stock <= 10:
                stock_status = "low_stock"
            else:
                stock_status = "in_stock"

            results.append({
                "sku": sku,
                "product": variant.product.name,
                "old_stock": old_stock,
                "new_stock": new_stock,
                "stock_status": stock_status,
            })

        return Response({
            "message": f"Bulk update complete. {updated_count} variant(s) updated.",
            "updated_count": updated_count,
            "skipped_count": len(skipped_skus),
            "skipped_skus": skipped_skus,
            "results": results
        }, status=status.HTTP_200_OK)


class VendorLowStockAlertView(APIView):
    """
    GET /api/vendors/inventory/low-stock/
    Quick view of all products and variants with low or zero stock.
    Vendor checks this before a sale event or busy season.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Get low stock alerts",
        description="""
        Returns all products and variants with stock at 10 or below.
        Use this to identify what needs restocking before it runs out.
        threshold query param lets you customize the low stock cutoff (default: 10).
        """,
        parameters=[
            OpenApiParameter(
                name='threshold',
                type=OpenApiTypes.INT,
                required=False,
                description='Stock level considered low (default: 10)'
            ),
        ],
        responses={200: inline_serializer(
            name='LowStockAlertResponse',
            fields={
                'total_alerts': serializers.IntegerField(),
                'out_of_stock': ProductInventorySerializer(many=True),
                'low_stock': ProductInventorySerializer(many=True),
            }
        )},
        tags=["Vendor — Inventory"]
    )
    def get(self, request):
        from .serializers import ProductInventorySerializer
        vendor = request.user.vendor_profile

        try:
            threshold = int(request.query_params.get('threshold', 10))
            threshold = max(1, min(threshold, 100))  # clamp between 1 and 100
        except ValueError:
            threshold = 10

        products = Product.objects.filter(
            vendor=vendor, is_active=True
        ).prefetch_related(
            'images', 'variants__attributes__attribute_type'
        )

        out_of_stock = []
        low_stock = []

        for product in products:
            if product.has_variants:
                for variant in product.variants.all():
                    if variant.stock == 0:
                        out_of_stock.append(product)
                        break
                    elif variant.stock <= threshold:
                        low_stock.append(product)
                        break
            else:
                if product.stock == 0:
                    out_of_stock.append(product)
                elif product.stock <= threshold:
                    low_stock.append(product)

        # Deduplicate
        out_of_stock = list({p.id: p for p in out_of_stock}.values())
        low_stock = list({p.id: p for p in low_stock}.values())

        return Response({
            "total_alerts": len(out_of_stock) + len(low_stock),
            "threshold_used": threshold,
            "out_of_stock": ProductInventorySerializer(
                out_of_stock, many=True, context={'request': request}
            ).data,
            "low_stock": ProductInventorySerializer(
                low_stock, many=True, context={'request': request}
            ).data,
        }, status=status.HTTP_200_OK)    
    
class VendorDashboardView(APIView):
    """
    GET /api/vendors/dashboard/
    Complete vendor dashboard summary in one API call.
    """
    permission_classes = [IsVendor]

    @extend_schema(
        summary="Vendor dashboard summary",
        description="""
        Returns everything a vendor needs on their dashboard:
        - Overall revenue, payout and commission stats
        - This month's performance
        - Inventory alerts (low stock, out of stock)
        - Order status breakdown
        - Revenue chart data for last 7 and 30 days
        - Top 5 best-selling products
        - Last 5 recent orders

        All data is scoped to this vendor only.
        """,
        responses={200: inline_serializer(
            name='VendorDashboardResponse',
            fields={
                'shop_name': serializers.CharField(),
                'total_revenue': serializers.DecimalField(
                    max_digits=12, decimal_places=2
                ),
                'total_orders': serializers.IntegerField(),
                'low_stock_count': serializers.IntegerField(),
            }
        )},
        tags=["Vendor — Dashboard"]
    )
    def get(self, request):
        from django.db.models import (
            Sum, Count, F, DecimalField as DField
        )
        from django.db.models.functions import TruncDate
        from django.utils import timezone
        from datetime import timedelta
        from decimal import Decimal
        from orders.models import Order, OrderItem
        from products.models import Product

        vendor = request.user.vendor_profile
        now = timezone.now()
        this_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # ── All vendor order items ─────────────────────────────
        all_items = OrderItem.objects.filter(vendor=vendor)

        # ── Overall stats ──────────────────────────────────────
        overall = all_items.aggregate(
            total_revenue=Sum(
                F('unit_price') * F('quantity'),
                output_field=DField(max_digits=12, decimal_places=2)
            ),
            total_payout=Sum('vendor_payout'),
            total_commission=Sum('commission_amount'),
        )

        total_revenue = overall['total_revenue'] or Decimal('0.00')
        total_payout = overall['total_payout'] or Decimal('0.00')
        total_commission = overall['total_commission'] or Decimal('0.00')

        # ── Total unique orders containing this vendor's items ─
        total_orders = Order.objects.filter(
            items__vendor=vendor
        ).distinct().count()

        # ── Product counts ────────────────────────────────────
        all_products = Product.objects.filter(vendor=vendor)
        total_products = all_products.count()
        active_products = all_products.filter(is_active=True).count()

        # ── This month stats ──────────────────────────────────
        this_month_items = all_items.filter(
            order__created_at__gte=this_month_start
        )
        this_month = this_month_items.aggregate(
            revenue=Sum(
                F('unit_price') * F('quantity'),
                output_field=DField(max_digits=12, decimal_places=2)
            ),
            payout=Sum('vendor_payout'),
        )
        this_month_revenue = this_month['revenue'] or Decimal('0.00')
        this_month_payout = this_month['payout'] or Decimal('0.00')
        this_month_orders = Order.objects.filter(
            items__vendor=vendor,
            created_at__gte=this_month_start
        ).distinct().count()

        # ── Inventory alerts ──────────────────────────────────
        low_stock_count = 0
        out_of_stock_count = 0

        for product in all_products.filter(is_active=True).prefetch_related('variants'):
            if product.has_variants:
                for variant in product.variants.all():
                    if variant.stock == 0:
                        out_of_stock_count += 1
                    elif variant.stock <= 10:
                        low_stock_count += 1
            else:
                if product.stock == 0:
                    out_of_stock_count += 1
                elif product.stock <= 10:
                    low_stock_count += 1

        # ── Orders by status ──────────────────────────────────
        status_choices = [
            'pending', 'confirmed', 'shipped',
            'delivered', 'cancelled', 'returned'
        ]
        orders_by_status = {}
        for s in status_choices:
            orders_by_status[s] = Order.objects.filter(
                items__vendor=vendor,
                status=s
            ).distinct().count()

        # ── Revenue chart — last 7 days ───────────────────────
        seven_day_data = (
            all_items.filter(
                order__created_at__gte=seven_days_ago
            )
            .annotate(date=TruncDate('order__created_at'))
            .values('date')
            .annotate(
                revenue=Sum(
                    F('unit_price') * F('quantity'),
                    output_field=DField(max_digits=12, decimal_places=2)
                ),
                payout=Sum('vendor_payout'),
                orders=Count('order', distinct=True)
            )
            .order_by('date')
        )

        # Fill in missing days with zero values
        revenue_last_7_days = []
        seven_day_map = {
            item['date']: item for item in seven_day_data
        }
        for i in range(7):
            day = (now - timedelta(days=6 - i)).date()
            data = seven_day_map.get(day, {})
            revenue_last_7_days.append({
                "date": day,
                "revenue": data.get('revenue', Decimal('0.00')),
                "orders": data.get('orders', 0),
                "payout": data.get('payout', Decimal('0.00')),
            })

        # ── Revenue chart — last 30 days ──────────────────────
        thirty_day_data = (
            all_items.filter(
                order__created_at__gte=thirty_days_ago
            )
            .annotate(date=TruncDate('order__created_at'))
            .values('date')
            .annotate(
                revenue=Sum(
                    F('unit_price') * F('quantity'),
                    output_field=DField(max_digits=12, decimal_places=2)
                ),
                payout=Sum('vendor_payout'),
                orders=Count('order', distinct=True)
            )
            .order_by('date')
        )

        revenue_last_30_days = []
        thirty_day_map = {
            item['date']: item for item in thirty_day_data
        }
        for i in range(30):
            day = (now - timedelta(days=29 - i)).date()
            data = thirty_day_map.get(day, {})
            revenue_last_30_days.append({
                "date": day,
                "revenue": data.get('revenue', Decimal('0.00')),
                "orders": data.get('orders', 0),
                "payout": data.get('payout', Decimal('0.00')),
            })

        # ── Best selling products — top 5 ─────────────────────
        best_selling_raw = (
            all_items.filter(product__isnull=False)
            .values(
                'product__id', 'product__name', 'product__slug'
            )
            .annotate(
                total_units_sold=Sum('quantity'),
                total_revenue=Sum(
                    F('unit_price') * F('quantity'),
                    output_field=DField(max_digits=12, decimal_places=2)
                ),
                total_payout=Sum('vendor_payout'),
            )
            .order_by('-total_units_sold')[:5]
        )

        best_selling_products = [
            {
                "product_id": item['product__id'],
                "product_name": item['product__name'],
                "product_slug": item['product__slug'],
                "total_units_sold": item['total_units_sold'],
                "total_revenue": item['total_revenue'] or Decimal('0.00'),
                "total_payout": item['total_payout'] or Decimal('0.00'),
            }
            for item in best_selling_raw
        ]

        # ── Recent orders — last 5 ────────────────────────────
        recent_orders_qs = Order.objects.filter(
            items__vendor=vendor
        ).distinct().order_by('-created_at')[:5]

        recent_orders = []
        for order in recent_orders_qs:
            vendor_items = order.items.filter(vendor=vendor)
            vendor_subtotal = sum(
                item.unit_price * item.quantity for item in vendor_items
            )
            vendor_payout = sum(
                item.vendor_payout for item in vendor_items
            )
            recent_orders.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": order.payment_status,
                "vendor_item_count": vendor_items.count(),
                "vendor_subtotal": vendor_subtotal,
                "vendor_payout": vendor_payout,
                "created_at": order.created_at,
            })

        # ── Build final response ───────────────────────────────
        return Response({
            # Shop info
            "shop_name": vendor.shop_name,
            "shop_slug": vendor.shop_slug,
            "vendor_status": vendor.status,
            "member_since": vendor.created_at,

            # Overall stats
            "total_revenue": total_revenue,
            "total_payout": total_payout,
            "total_commission_paid": total_commission,
            "total_orders": total_orders,
            "total_products": total_products,
            "active_products": active_products,

            # This month
            "this_month_revenue": this_month_revenue,
            "this_month_payout": this_month_payout,
            "this_month_orders": this_month_orders,

            # Inventory alerts
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,

            # Order breakdown
            "orders_by_status": orders_by_status,

            # Charts
            "revenue_last_7_days": revenue_last_7_days,
            "revenue_last_30_days": revenue_last_30_days,

            # Lists
            "best_selling_products": best_selling_products,
            "recent_orders": recent_orders,

        }, status=status.HTTP_200_OK)    