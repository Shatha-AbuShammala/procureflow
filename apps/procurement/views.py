from django.db import transaction

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Approval, PurchaseRequest, RFQ, SupplierQuote
from .permissions import CanManageProcurement

from .serializers import PurchaseRequestSerializer, RFQSerializer, SupplierQuoteSerializer


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

class RFQViewSet(viewsets.ModelViewSet):

    serializer_class = RFQSerializer

    permission_classes = [
        permissions.IsAuthenticated,
        CanManageProcurement,
    ]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_queryset(self):

        return (
            RFQ.objects
            .filter(
                purchase_request__company=self.request.user.company
            )
            .select_related(
                "purchase_request",
                "created_by",
            )
            .prefetch_related(
                "suppliers",
                "quotes",
                "quotes__supplier",
            )
            .order_by("-created_at")
        )

    def perform_create(self, serializer):

        serializer.save(
            created_by=self.request.user
        )

    @action(
        detail=True,
        methods=["post"],
    )
    def send(self, request, pk=None):

        rfq = self.get_object()

        if rfq.status != RFQ.Status.DRAFT:
            return Response(
                {
                    "detail": (
                        "Only draft RFQs can be sent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not rfq.suppliers.exists():
            return Response(
                {
                    "detail": (
                        "RFQ must contain at least "
                        "one supplier."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        rfq.status = RFQ.Status.SENT

        rfq.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return Response(
            self.get_serializer(rfq).data
        )

    @action(
        detail=True,
        methods=["get"],
    )
    def quotes(self, request, pk=None):

        rfq = self.get_object()

        quotes = (
            rfq.quotes
            .select_related("supplier")
            .order_by(
                "total_amount",
                "delivery_days",
            )
        )

        serializer = SupplierQuoteSerializer(
            quotes,
            many=True,
            context={
                "request": request,
            },
        )

        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"quotes/(?P<quote_id>\d+)/select",
    )
    @transaction.atomic
    def select_quote(
        self,
        request,
        pk=None,
        quote_id=None,
    ):

        rfq = self.get_object()

        if rfq.status != RFQ.Status.SENT:
            return Response(
                {
                    "detail": (
                        "A quote can only be selected "
                        "from a sent RFQ."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_quote = (
                SupplierQuote.objects
                .select_related("supplier")
                .get(
                    pk=quote_id,
                    rfq=rfq,
                )
            )

        except SupplierQuote.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "Quote not found for this RFQ."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if rfq.quotes.filter(
            status=SupplierQuote.Status.SELECTED
        ).exists():
            return Response(
                {
                    "detail": (
                        "A quote has already been selected."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        rfq.quotes.exclude(
            pk=selected_quote.pk
        ).update(
            status=SupplierQuote.Status.REJECTED
        )

        selected_quote.status = (
            SupplierQuote.Status.SELECTED
        )

        selected_quote.save(
            update_fields=["status"]
        )

        rfq.status = RFQ.Status.CLOSED

        rfq.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return Response(
            SupplierQuoteSerializer(
                selected_quote,
                context={
                    "request": request,
                },
            ).data
        )


class SupplierQuoteViewSet(viewsets.ModelViewSet):

    serializer_class = SupplierQuoteSerializer

    permission_classes = [
        permissions.IsAuthenticated,
        CanManageProcurement,
    ]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_queryset(self):

        return (
            SupplierQuote.objects
            .filter(
                rfq__purchase_request__company=(
                    self.request.user.company
                )
            )
            .select_related(
                "rfq",
                "supplier",
                "rfq__purchase_request",
            )
            .order_by("-submitted_at")
        )    