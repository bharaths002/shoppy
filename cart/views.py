from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from .models import CartItem
from .serializers import (
    CartSerializer, AddToCartSerializer, UpdateCartItemSerializer
)
from .utils import get_or_create_cart


class CartView(APIView):
    """
    GET    /api/cart/     → view cart
    DELETE /api/cart/     → clear entire cart
    """

    @extend_schema(
        summary="View cart",
        responses=CartSerializer,
        tags=["Cart"]
    )
    def get(self, request):
        cart = get_or_create_cart(request)
        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Clear entire cart",
        responses={200: inline_serializer(
            name='ClearCartResponse',
            fields={'message': serializers.CharField()}
        )},
        tags=["Cart"]
    )
    def delete(self, request):
        cart = get_or_create_cart(request)
        cart.items.all().delete()
        return Response(
            {"message": "Cart cleared successfully."},
            status=status.HTTP_200_OK
        )


class CartItemView(APIView):
    """
    POST  /api/cart/items/          → add item to cart
    """

    @extend_schema(
        summary="Add item to cart",
        request=AddToCartSerializer,
        responses={200: inline_serializer(
            name='AddToCartResponse',
            fields={
                'message': serializers.CharField(),
                'cart': CartSerializer()
            }
        )},
        tags=["Cart"]
    )
    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        cart = get_or_create_cart(request)
        product = serializer.validated_data['product']
        variant = serializer.validated_data.get('variant')
        quantity = serializer.validated_data['quantity']

        existing_item = CartItem.objects.filter(
            cart=cart, product=product, variant=variant
        ).first()

        if existing_item:
            total_quantity = existing_item.quantity + quantity
            stock = variant.stock if variant else product.stock
            if total_quantity > stock:
                return Response(
                    {"error": f"Cannot add {quantity} more. Only {stock - existing_item.quantity} left."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            existing_item.quantity = total_quantity
            existing_item.save()
            message = "Cart updated."
        else:
            CartItem.objects.create(
                cart=cart,
                product=product,
                variant=variant,
                quantity=quantity
            )
            message = "Item added to cart."

        cart.refresh_from_db()
        cart_serializer = CartSerializer(cart, context={'request': request})
        return Response(
            {"message": message, "cart": cart_serializer.data},
            status=status.HTTP_200_OK
        )


class CartItemDetailView(APIView):
    """
    PATCH  /api/cart/items/<item_id>/   → update quantity
    DELETE /api/cart/items/<item_id>/   → remove item
    """

    def get_item(self, request, item_id):
        cart = get_or_create_cart(request)
        try:
            return CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return None

    @extend_schema(
        summary="Update cart item quantity",
        request=UpdateCartItemSerializer,
        responses={200: inline_serializer(
            name='UpdateCartItemResponse',
            fields={
                'message': serializers.CharField(),
                'cart': CartSerializer()
            }
        )},
        tags=["Cart"]
    )
    def patch(self, request, item_id):
        item = self.get_item(request, item_id)
        if not item:
            return Response(
                {"error": "Cart item not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UpdateCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_quantity = serializer.validated_data['quantity']

        stock = item.variant.stock if item.variant else item.product.stock
        if new_quantity > stock:
            return Response(
                {"error": f"Only {stock} item(s) available in stock."},
                status=status.HTTP_400_BAD_REQUEST
            )

        item.quantity = new_quantity
        item.save()

        cart = get_or_create_cart(request)
        cart_serializer = CartSerializer(cart, context={'request': request})
        return Response(
            {"message": "Quantity updated.", "cart": cart_serializer.data},
            status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Remove item from cart",
        responses={200: inline_serializer(
            name='RemoveCartItemResponse',
            fields={
                'message': serializers.CharField(),
                'cart': CartSerializer()
            }
        )},
        tags=["Cart"]
    )
    def delete(self, request, item_id):
        item = self.get_item(request, item_id)
        if not item:
            return Response(
                {"error": "Cart item not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        item.delete()
        cart = get_or_create_cart(request)
        cart_serializer = CartSerializer(cart, context={'request': request})
        return Response(
            {"message": "Item removed.", "cart": cart_serializer.data},
            status=status.HTTP_200_OK
        )