from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.db import transaction, models
from django.conf import settings
from .models import Order, OrderItem, OrderStatusHistory
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    CreateOrderSerializer,
)
from .razorpay_utils import create_razorpay_order, verify_payment_signature
from products.models import ProductVariant
from .permissions import IsAdminOrStaff


class CreateOrderView(APIView):
    """
    POST /api/orders/create/
    Converts cart into an order. For COD — order is confirmed immediately.
    For UPI/Card — order is created in 'pending' state, Razorpay order is generated,
    frontend must complete payment and call /verify-payment/ to confirm.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create an order from cart",
        description="""
        Converts the current user's cart into an order.
        - COD: order confirmed immediately, cart cleared
        - UPI/Card: Razorpay order created, returns payment details for frontend checkout.
          Cart is cleared only after /verify-payment/ succeeds.
        """,
        request=CreateOrderSerializer,
        responses={
            201: inline_serializer(
                name="CreateOrderResponse",
                fields={
                    "message": serializers.CharField(),
                    "order_id": serializers.CharField(),
                    "order_number": serializers.CharField(),
                    "razorpay_order_id": serializers.CharField(required=False),
                    "amount": serializers.IntegerField(required=False),
                    "currency": serializers.CharField(required=False),
                    "razorpay_key_id": serializers.CharField(required=False),
                },
            ),
            400: inline_serializer(
                name="CreateOrderErrorResponse",
                fields={"error": serializers.CharField()},
            ),
        },
        tags=["Orders"],
    )
    def post(self, request):
        serializer = CreateOrderSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        cart = serializer.validated_data["cart"]
        shipping_address = serializer.validated_data["shipping_address"]
        billing_address = serializer.validated_data["billing_address"]
        payment_method = serializer.validated_data["payment_method"]

        # Re-validate stock at order time
        for item in cart.items.select_related("product", "variant"):
            available_stock = item.variant.stock if item.variant else item.product.stock
            if item.quantity > available_stock:
                return Response(
                    {
                        "error": f"{item.product.name} only has {available_stock} unit(s) left. Please update your cart."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        subtotal = cart.subtotal
        shipping_fee = 0 if subtotal >= 999 else 49
        total = subtotal + shipping_fee

        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                shipping_address=shipping_address,
                billing_address=billing_address,
                payment_method=payment_method,
                subtotal=subtotal,
                shipping_fee=shipping_fee,
                total=total,
                status="pending",
                payment_status="pending",
            )

            for item in cart.items.select_related("product", "variant"):
                variant_details = ""
                if item.variant:
                    attrs = item.variant.attributes.select_related(
                        "attribute_type"
                    ).all()
                    variant_details = ", ".join(
                        f"{a.attribute_type.name}: {a.value}" for a in attrs
                    )

                    # ✅ Calculate commission at order time
                item_vendor = item.product.vendor if item.product else None
                commission_rate = item_vendor.commission_rate if item_vendor else 0
                line_total = item.unit_price * item.quantity
                commission_amount = (line_total * commission_rate / 100).quantize(
                __import__('decimal').Decimal('0.01')
                    )
                vendor_payout = line_total - commission_amount    

                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    variant=item.variant,
                    vendor=item_vendor,
                    product_name=item.product.name,
                    variant_details=variant_details,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    commission_rate=commission_rate,        # ✅ snapshot commission
                    commission_amount=commission_amount,    # ✅ platform cut
                    vendor_payout=vendor_payout,            # ✅ vendor gets this
                    )
                

                # Deduct stock
                if item.variant:
                    ProductVariant.objects.filter(id=item.variant.id).update(
                        stock=item.variant.stock - item.quantity
                    )
                else:
                    item.product.stock -= item.quantity
                    item.product.save()

            OrderStatusHistory.objects.create(
                order=order, status="pending", note="Order placed"
            )

            # COD — confirm immediately
            if payment_method == "cod":
                order.status = "confirmed"
                order.save()
                OrderStatusHistory.objects.create(
                    order=order, status="confirmed", note="COD order confirmed"
                )
                cart.items.all().delete()
                return Response(
                    {
                        "message": "Order placed successfully.",
                        "order": OrderDetailSerializer(order).data,
                    },
                    status=status.HTTP_201_CREATED,
                )

            # UPI/Card — create Razorpay order
            razorpay_order = create_razorpay_order(
                amount_in_rupees=total, receipt_id=order.order_number
            )
            order.razorpay_order_id = razorpay_order["id"]
            order.save()

            return Response(
                {
                    "message": "Order created. Proceed to payment.",
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "razorpay_order_id": razorpay_order["id"],
                    "amount": razorpay_order["amount"],
                    "currency": razorpay_order["currency"],
                    "razorpay_key_id": settings.RAZORPAY_KEY_ID,  # ✅ fixed — no more __import__ hack
                },
                status=status.HTTP_201_CREATED,
            )


class VerifyPaymentView(APIView):
    """
    POST /api/orders/verify-payment/
    Called by frontend after Razorpay checkout completes.
    Verifies signature server-side — never trust frontend success callback alone.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Verify Razorpay payment signature",
        description="""
        Must be called after frontend Razorpay checkout completes.
        Verifies the payment signature server-side — never trust frontend alone.
        On success: order confirmed, cart cleared.
        On failure: payment marked as failed.
        """,
        request=inline_serializer(
            name="VerifyPaymentRequest",
            fields={
                "order_id": serializers.CharField(),
                "razorpay_payment_id": serializers.CharField(),
                "razorpay_signature": serializers.CharField(),
            },
        ),
        responses={
            200: inline_serializer(
                name="VerifyPaymentSuccessResponse",
                fields={
                    "message": serializers.CharField(),
                    "order": OrderDetailSerializer(),
                },
            ),
            400: inline_serializer(
                name="VerifyPaymentErrorResponse",
                fields={"error": serializers.CharField()},
            ),
        },
        tags=["Orders"],
    )
    def post(self, request):
        order_id = request.data.get("order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        if not all([order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {"error": "Missing payment verification fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if not order.razorpay_order_id:
            return Response(
                {"error": "No payment was initiated for this order."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_valid = verify_payment_signature(
            order.razorpay_order_id, razorpay_payment_id, razorpay_signature
        )

        if not is_valid:
            order.payment_status = "failed"
            order.save()
            OrderStatusHistory.objects.create(
                order=order, status="pending", note="Payment verification failed"
            )
            return Response(
                {"error": "Payment verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.razorpay_payment_id = razorpay_payment_id
        order.razorpay_signature = razorpay_signature
        order.payment_status = "paid"
        order.status = "confirmed"
        order.save()

        OrderStatusHistory.objects.create(
            order=order, status="confirmed", note="Payment verified, order confirmed"
        )

        cart = getattr(request.user, "cart", None)
        if cart:
            cart.items.all().delete()

        return Response(
            {
                "message": "Payment verified. Order confirmed.",
                "order": OrderDetailSerializer(order).data,
            },
            status=status.HTTP_200_OK,
        )


class OrderListView(APIView):
    """GET /api/orders/ — order history for logged-in user"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get order history",
        description="Returns all orders for the currently logged-in user.",
        responses={200: OrderListSerializer(many=True)},
        tags=["Orders"],
    )
    def get(self, request):
        orders = Order.objects.filter(user=request.user).prefetch_related("items")
        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderDetailView(APIView):
    """GET /api/orders/<order_id>/ — single order detail"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get single order detail",
        description="Returns full order detail including items, addresses and status history.",
        responses={
            200: OrderDetailSerializer,
            404: inline_serializer(
                name="OrderNotFoundResponse", fields={"error": serializers.CharField()}
            ),
        },
        tags=["Orders"],
    )
    def get(self, request, order_id):
        try:
            order = (
                Order.objects.select_related("shipping_address", "billing_address")
                .prefetch_related("items", "status_history")
                .get(id=order_id, user=request.user)
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = OrderDetailSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CancelOrderView(APIView):
    """POST /api/orders/<order_id>/cancel/"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cancel an order",
        description="""
        Customer can cancel an order only if status is pending or confirmed.
        Cannot cancel if: shipped, delivered, already cancelled, or returned.
        Stock is automatically restored on cancellation.
        """,
        request=None,
        responses={
            200: inline_serializer(
                name="CancelOrderResponse",
                fields={
                    "message": serializers.CharField(),
                    "order": OrderDetailSerializer(),
                },
            ),
            400: inline_serializer(
                name="CancelOrderErrorResponse",
                fields={"error": serializers.CharField()},
            ),
        },
        tags=["Orders"],
    )
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if order.status in ["shipped", "delivered", "cancelled", "returned"]:
            return Response(
                {
                    "error": f"Order cannot be cancelled — current status is '{order.status}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order.status = "cancelled"
            order.save()

            for item in order.items.all():
                if item.variant:
                    ProductVariant.objects.filter(id=item.variant.id).update(
                        stock=models.F("stock") + item.quantity
                    )
                elif item.product:
                    item.product.stock += item.quantity
                    item.product.save()

            OrderStatusHistory.objects.create(
                order=order, status="cancelled", note="Cancelled by customer"
            )

        return Response(
            {
                "message": "Order cancelled successfully.",
                "order": OrderDetailSerializer(order).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminOrderListView(APIView):
    permission_classes = [IsAdminOrStaff]

    @extend_schema(
        summary="Admin — list all orders",
        description="Admin/staff can view all orders. Filter by status using ?status=pending etc.",
        responses={200: OrderListSerializer(many=True)},
        parameters=[
            inline_serializer(
                name="AdminOrderFilter",
                fields={
                    "status": serializers.ChoiceField(
                        choices=[
                            "pending",
                            "confirmed",
                            "shipped",
                            "delivered",
                            "cancelled",
                            "returned",
                        ],
                        required=False,
                    )
                },
            )
        ],
        tags=["Admin — Orders"],
    )
    def get(self, request):
        status_filter = request.query_params.get("status")
        orders = Order.objects.all().prefetch_related("items")
        if status_filter:
            orders = orders.filter(status=status_filter)
        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminUpdateOrderStatusView(APIView):
    permission_classes = [IsAdminOrStaff]

    @extend_schema(
        summary="Admin — update order status",
        description="""
        Admin/staff can update order status to any valid status.
        Every change is logged in the order's status history with an optional note.
        Valid statuses: pending, confirmed, shipped, delivered, cancelled, returned
        """,
        request=inline_serializer(
            name="UpdateOrderStatusRequest",
            fields={
                "status": serializers.ChoiceField(
                    choices=[
                        "pending",
                        "confirmed",
                        "shipped",
                        "delivered",
                        "cancelled",
                        "returned",
                    ]
                ),
                "note": serializers.CharField(required=False),
            },
        ),
        responses={
            200: inline_serializer(
                name="UpdateOrderStatusResponse",
                fields={
                    "message": serializers.CharField(),
                    "order": OrderDetailSerializer(),
                },
            ),
            400: inline_serializer(
                name="UpdateOrderStatusErrorResponse",
                fields={"error": serializers.CharField()},
            ),
        },
        tags=["Admin — Orders"],
    )
    def patch(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get("status")
        note = request.data.get("note", "")

        valid_statuses = [c[0] for c in Order.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {"error": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST
            )

        order.status = new_status
        order.save()
        OrderStatusHistory.objects.create(order=order, status=new_status, note=note)

        return Response(
            {
                "message": f"Order status updated to '{new_status}'.",
                "order": OrderDetailSerializer(order).data,
            },
            status=status.HTTP_200_OK,
        )
