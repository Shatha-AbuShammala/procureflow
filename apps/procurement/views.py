from django.db import transaction

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Approval, PurchaseRequest
from .serializers import PurchaseRequestSerializer


class PurchaseRequestViewSet(viewsets.ModelViewSet):

    serializer_class = PurchaseRequestSerializer

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_queryset(self):

        user = self.request.user

        queryset = (
            PurchaseRequest.objects
            .filter(company=user.company)
            .select_related(
                "requester",
                "approval",
                "approval__approver",
            )
            .prefetch_related("items")
            .order_by("-created_at")
        )

        if user.role == user.Role.EMPLOYEE:
            return queryset.filter(
                requester=user
            )

        return queryset

    def perform_create(self, serializer):

        user = self.request.user

        if user.company_id is None:
            raise PermissionDenied(
                "You must belong to a company."
            )

        if user.role != user.Role.EMPLOYEE:
            raise PermissionDenied(
                "Only employees can create purchase requests."
            )

        serializer.save(
            company=user.company,
            requester=user,
        )

    @action(
        detail=True,
        methods=["post"],
    )
    def submit(self, request, pk=None):

        purchase_request = self.get_object()

        if purchase_request.requester_id != request.user.id:
            raise PermissionDenied(
                "You can only submit your own purchase requests."
            )

        if purchase_request.status != PurchaseRequest.Status.DRAFT:
            return Response(
                {
                    "detail": (
                        "Only draft purchase requests "
                        "can be submitted."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not purchase_request.items.exists():
            return Response(
                {
                    "detail": (
                        "A purchase request must contain "
                        "at least one item."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        purchase_request.status = (
            PurchaseRequest.Status.PENDING_APPROVAL
        )

        purchase_request.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return Response(
            self.get_serializer(purchase_request).data
        )

    @action(
        detail=True,
        methods=["post"],
    )
    @transaction.atomic
    def approve(self, request, pk=None):

        purchase_request = self.get_object()
        user = request.user

        if user.role != user.Role.MANAGER:
            raise PermissionDenied(
                "Only managers can approve purchase requests."
            )

        if purchase_request.requester_id == user.id:
            raise PermissionDenied(
                "You cannot approve your own purchase request."
            )

        if (
            purchase_request.status
            != PurchaseRequest.Status.PENDING_APPROVAL
        ):
            return Response(
                {
                    "detail": (
                        "Only pending purchase requests "
                        "can be approved."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = request.data.get(
            "comment",
            "",
        )

        Approval.objects.create(
            purchase_request=purchase_request,
            approver=user,
            status=Approval.Status.APPROVED,
            comment=comment,
        )

        purchase_request.status = (
            PurchaseRequest.Status.APPROVED
        )

        purchase_request.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return Response(
            self.get_serializer(purchase_request).data
        )

    @action(
        detail=True,
        methods=["post"],
    )
    @transaction.atomic
    def reject(self, request, pk=None):

        purchase_request = self.get_object()
        user = request.user

        if user.role != user.Role.MANAGER:
            raise PermissionDenied(
                "Only managers can reject purchase requests."
            )

        if purchase_request.requester_id == user.id:
            raise PermissionDenied(
                "You cannot reject your own purchase request."
            )

        if (
            purchase_request.status
            != PurchaseRequest.Status.PENDING_APPROVAL
        ):
            return Response(
                {
                    "detail": (
                        "Only pending purchase requests "
                        "can be rejected."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = request.data.get(
            "comment",
            "",
        )

        Approval.objects.create(
            purchase_request=purchase_request,
            approver=user,
            status=Approval.Status.REJECTED,
            comment=comment,
        )

        purchase_request.status = (
            PurchaseRequest.Status.REJECTED
        )

        purchase_request.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return Response(
            self.get_serializer(purchase_request).data
        )