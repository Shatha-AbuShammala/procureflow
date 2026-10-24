from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db.models.deletion import ProtectedError

from .models import Supplier
from .permissions import CanManageSuppliers
from .serializers import SupplierSerializer


class SupplierListCreateView(generics.ListCreateAPIView):
    serializer_class = SupplierSerializer

    permission_classes = [
        IsAuthenticated,
        CanManageSuppliers,
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Supplier.objects.none()
        return Supplier.objects.filter(company=self.request.user.company).order_by(
            "name"
        )

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SupplierSerializer

    permission_classes = [
        IsAuthenticated,
        CanManageSuppliers,
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Supplier.objects.none()
        return Supplier.objects.filter(company=self.request.user.company)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                "This supplier has procurement records. Deactivate it instead."
            ) from exc
