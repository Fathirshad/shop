from django.shortcuts import render
from rest_framework.decorators import api_view,permission_classes
from .models import Product,Cart,CartItem,Transaction
from .serializers import ProductSerializer,DetailedProductSerializer,UserSerializer,CartItemSerializer,SimpleCartSerializer,CartSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from decimal import Decimal
from django.conf import settings
import uuid
import requests
from django.views.decorators.csrf import csrf_exempt
import paypalrestsdk
from django.conf import settings
# from django.shortcuts import get_object_or_404



BASE_URL = settings.REACT_BASE_URL

paypalrestsdk.configure({
    "mode": settings.PAYPAL_MODE,
    "client_id": settings.PAYPAL_CLIENT_ID,
    "client_secret":settings.PAYPAL_CLIENT_SECRET

})





@api_view(['GET'])
def products(request):
    products = Product.objects.all()
    serializer = ProductSerializer(products,many=True)
    return Response(serializer.data)

@api_view(["GET"])
def product_detail(request,slug):
    product = Product.objects.get(slug=slug)
    serializer = DetailedProductSerializer(product)
    return Response(serializer.data)

@api_view(["POST"])
def add_item(request):
    try:
        cart_code = request.data.get("cart_code")
        product_id = request.data.get("product_id")

        cart,created = Cart.objects.get_or_create(cart_code = cart_code)
        product = Product.objects.get(id=product_id)

        cartitem, created = CartItem.objects.get_or_create(cart=cart,product=product)
        cartitem.quantity = 1
        cartitem.save()

        serializer = CartItemSerializer(cartitem)
        return Response({"data":serializer.data, "message":"Cartitem created successfully"},status=201)
    except Exception as e:
        return Response({"error":str(e)}, status=400)

@api_view(['GET'])
def product_in_cart(request):
    cart_code = request.query_params.get("cart_code")
    product_id = request.query_params.get("product_id")

    cart = Cart.objects.get(cart_code=cart_code)
    product= Product.objects.get(id=product_id)

    product_exists_in_cart = CartItem.objects.filter(cart=cart,product=product).exists()

    return Response({'product_in_cart': product_exists_in_cart})

@api_view(['GET'])
def get_cart_stat(request):
    cart_code = request.query_params.get("cart_code")
    cart = Cart.objects.get(cart_code=cart_code, paid=False)
    serializer = SimpleCartSerializer(cart)
    return Response(serializer.data)


@api_view(['GET'])
def get_cart(request):
    cart_code = request.query_params.get("cart_code")
    

    cart = Cart.objects.get(cart_code=cart_code,paid=False)
    serializer = CartSerializer(cart)
    return Response(serializer.data)



# def get_cart(request):
#     cart_code = request.GET.get('cart_code')
#     if not cart_code:
#         return Response({'error': 'cart_code is required'}, status=status.HTTP_400_BAD_REQUEST)
    
#     cart = get_object_or_404(Cart, cart_code=cart_code)
    # Serialize and return the cart

    
# def get_cart(request):
#     cart_code = request.query_params.get("cart_code")
    

#     cart = Cart.objects.get(cart_code=cart_code,paid=False)
#     serializer = CartSerializer(cart)
#     return Response(serializer.data)



@api_view(['PATCH'])
def update_quantity(request):
    try:
        cartitem_id = request.data.get("item_id")
        quantity = request.data.get("quantity")
        quantity = int(quantity)
        cartitem = CartItem.objects.get(id=cartitem_id)
        cartitem.quantity = quantity
        cartitem.save()
        serializer = CartItemSerializer(cartitem)
        return Response({"data":serializer.data,"message":"Cartitem updatede successfully!"})
    except Exception as e:
        return Response({'error':str(e)},status=400)


@api_view(['POST'])
def delete_cartitem(request):
    cartitem_id = request.data.get("item_id")
    cartitem = CartItem.objects.get(id=cartitem_id)
    cartitem.delete()
    return Response({"message":"Item deleted successfully"}, status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_username(request):
    user = request.user
    return Response({"username":user.username})
 


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_info(request):
    user = request.user
    serializer = UserSerializer(user)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    if request.user:
        try:
            tx_ref = str(uuid.uuid4())
            cart_code = request.data.get("cart_code")
            cart = Cart.objects.get(cart_code=cart_code)
            user = request.user

            amount = sum([item.quantity * item.product.price for item in cart.items.all()])
            tax = Decimal("4.00")
            total_amount = amount + tax
            currency = "NGN"
            redirect_url = f"{BASE_URL}/payment-status/"

            transaction = Transaction.objects.create(
                ref=tx_ref,
                cart=cart,
                amount=total_amount,
                currency=currency,
                user=user,
                status='pending'
            )

            flutterwave_payload = {
                "tx_ref": tx_ref,
                "amount": str(total_amount),
                "currency": currency,
                "redirect_url": redirect_url,
                "customer":{
                    "email": user.email,
                    "name": user.username,
                    "phonenumber": user.phone
                },
                "customizations":{
                    "title": "Shop Payment"
                }
            }

            headers = {
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                "Content-Type":"application/json"
            }

            response = requests.post(
                'https://api.flutterwave.com/v3/payments',
                json = flutterwave_payload,
                headers=headers
            )


            if response.status_code == 200:
                return Response(response.json(), status=status.HTTP_200_OK)
            
            else:
                return Response(response.json(), status=response.status_code)
            

        except requests.exceptions.RequestException as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['POST'])
def payment_callback(request):
    status = request.GET.get('status')
    tx_ref = request.GET.get('tx_ref')  # ✅ fixed typo
    transaction_id = request.GET.get('transaction_id')

    user = request.user

    if status == 'successful':
        headers = {
            "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"
        }

        try:
            response = requests.get(  # ✅ use requests
                f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
                headers=headers
            )
            response_data = response.json()
        except requests.RequestException:
            return Response({
                'message': 'Error contacting payment gateway.',
                'subMessage': 'Please try again shortly.'
            }, status=500)

        if response_data.get('status') == 'success':
            try:
                transaction = Transaction.objects.get(ref=tx_ref)
            except Transaction.DoesNotExist:
                return Response({
                    'message': 'Transaction not found.',
                    'subMessage': 'Please contact support.'
                }, status=404)

            flutter_data = response_data['data']
            if (
                flutter_data['status'] == "successful"
                and float(flutter_data['amount']) == float(transaction.amount)
                and flutter_data['currency'] == transaction.currency
            ):
                transaction.status = 'completed'
                transaction.save()

                cart = transaction.cart
                cart.paid = True
                cart.user = user
                cart.save()

                return Response({
                    'message': 'Payment successful!',
                    'subMessage': 'You have successfully completed your purchase.'
                })

            else:
                return Response({
                    'message': 'Payment verification failed!',
                    'subMessage': 'Transaction details did not match.'
                }, status=400)

        else:
            return Response({
                'message': 'Failed to verify transaction with Flutterwave.',
                'subMessage': 'Please try again later.'
            }, status=400)

    else:
        return Response({
            'message': 'Payment was not successful!',
            'subMessage': 'Please try again or use a different method.'
        }, status=400)
    



@api_view(["POST"])
def initiate_paypal_payment(request):
    if request.user.is_authenticated:
        try:
            cart_code = request.data.get("cart_code")
            if not cart_code:
                return Response({"error": "Cart code is required."}, status=400)

            cart = Cart.objects.get(cart_code=cart_code)

            if not cart.items.exists():
                return Response({"error": "Cart is empty."}, status=400)

            amount = sum([item.product.price * item.quantity for item in cart.items.all()])
            tax = Decimal("4.00")
            total_amount = amount + tax
            tx_ref = str(uuid.uuid4())
            user = request.user

            payment = paypalrestsdk.Payment({
                "intent": "sale",
                "payer": {
                    "payment_method": "paypal"
                },
                "redirect_urls": {
                    "return_url": f"{BASE_URL}/payment-status?paymentStatus=success&ref={tx_ref}",
                    "cancel_url": f"{BASE_URL}/payment-status?paymentStatus=cancel"
                },
                "transactions": [{
                    "item_list": {
                        "items": [{
                            "name": "Cart Items",
                            "sku": "cart",
                            "price": str(total_amount),
                            "currency": "USD",
                            "quantity": 1
                        }]
                    },
                    "amount": {
                        "total": str(total_amount),
                        "currency": "USD"
                    },
                    "description": "Payment for cart items"
                }]
            })

            transaction, created = Transaction.objects.get_or_create(
                ref=tx_ref,
                cart=cart,
                amount=total_amount,
                user=user,
                status='pending'
            )

            if payment.create():
                for link in payment.links:
                    if link.rel == "approval_url":
                        approval_url = str(link.href)
                        return Response({"approval_url": approval_url})
                return Response({"error": "Approval URL not found"}, status=400)
            else:
                return Response({"error": payment.error}, status=400)

        except Cart.DoesNotExist:
            return Response({"error": "Cart not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    return Response({"error": "User not authenticated."}, status=401)


@api_view(['POST'])
def paypal_payment_callback(request):
    payment_id= request.query_params.get('paymentId')
    payer_id = request.quary_param.get('PayerID')
    ref = request.query_params.get('ref')

    user = request.user

    print("refff",ref)

    transaction = Transaction.objects.get(ref=ref)

    if payment_id and payer_id:
        payment = paypalrestsdk.Payment.find(payment_id)
        transaction.status='completed'
        transaction.save()
        cart = transaction.cart
        cart.paid = True
        cart.user = user
        cart.save()

        return Response({'message':'Payment uccessfull!','subMessage':'You have succesfully made payment for the items you purchased'})
    
    else:
        return Response({"error":"Invalied payment details."},status=400)