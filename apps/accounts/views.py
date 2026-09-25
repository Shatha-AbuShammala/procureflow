from django.contrib.auth import get_user_model
from rest_framework import generics, permissions
from .permissions import IsCompanyAdmin
from .serializers import CompanyUserSerializer
from .serializers import RegisterSerializer, CompanyUserSerializer

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


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
        return User.objects.filter(
            company=self.request.user.company
        ).order_by("id")    

class CompanyUserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanyUserSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsCompanyAdmin,
    ]

    def get_queryset(self):
        return User.objects.filter(
            company=self.request.user.company
        )