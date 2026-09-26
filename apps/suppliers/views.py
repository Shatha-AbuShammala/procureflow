from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

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
        return Supplier.objects.filter(
            company=self.request.user.company
        ).order_by("name")

    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company
        )

class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SupplierSerializer

    permission_classes = [
        IsAuthenticated,
        CanManageSuppliers,
    ]

    def get_queryset(self):
        return Supplier.objects.filter(
            company=self.request.user.company
        )