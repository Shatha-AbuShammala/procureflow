from django.contrib.auth import get_user_model
from rest_framework import generics, permissions
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .permissions import IsCompanyAdmin
from .serializers import RegisterSerializer, CompanyUserSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "registration"


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class MeView(generics.RetrieveAPIView):
    serializer_class = CompanyUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class CompanyUserListView(generics.ListAPIView):
    serializer_class = CompanyUserSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsCompanyAdmin,
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        return User.objects.filter(company=self.request.user.company).order_by("id")


class CompanyUserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanyUserSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsCompanyAdmin,
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        return User.objects.filter(company=self.request.user.company)
