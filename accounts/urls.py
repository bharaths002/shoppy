from django.urls import path
from .views import SendOTPView, VerifyOTPView, EmailPasswordLoginView, SetPasswordView, AddressListCreateView, AddressDetailView,SetDefaultAddressView

    

urlpatterns = [
    path('sendotp/', SendOTPView.as_view()),
    path('verifyotp/', VerifyOTPView.as_view()),
    path('login/', EmailPasswordLoginView.as_view(), name='email-password-login'),
    path('set-password/', SetPasswordView.as_view(), name='set-password'),  
    # Addresses
    path('addresses/', AddressListCreateView.as_view(), name='address-list-create'),
    path('addresses/<int:address_id>/', AddressDetailView.as_view(), name='address-detail'),
    path('addresses/<int:address_id>/set-default/', SetDefaultAddressView.as_view(), name='address-set-default'),

]