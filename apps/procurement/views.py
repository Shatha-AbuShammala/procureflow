from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import log_action

from .models import Approval, PurchaseOrder, PurchaseRequest, RFQ, SupplierQuote
from .permissions import CanManageProcurement
from .serializers import (
    PurchaseRequestSerializer,
    RFQSerializer,
    SupplierQuoteSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderCreateSerializer,
    ReceivingCreateSerializer,
    ReceivingSerializer,
)
from .services import create_purchase_order, receive_purchase_order


class PurchaseRequestViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        user = self.request.user
        queryset = (
            PurchaseRequest.objects
            .filter(company=user.company)
            .select_related("requester", "approval", "approval__approver")
            .prefetch_related("items")
            .order_by("-created_at")
        )
        if user.role == user.Role.EMPLOYEE:
            return queryset.filter(requester=user)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        if user.company_id is None:
            raise PermissionDenied("You must belong to a company.")
        if user.role != user.Role.EMPLOYEE:
            raise PermissionDenied("Only employees can create purchase requests.")

        with transaction.atomic():
            purchase_request = serializer.save(company=user.company, requester=user)
            log_action(
                actor=user,
                action=AuditLog.Action.CREATE,
                entity=purchase_request,
                new_values={
                    "status": purchase_request.status,
                    "title": purchase_request.title,
                },
            )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def submit(self, request, pk=None):
        purchase_request = self.get_object()
        if purchase_request.requester_id != request.user.id:
            raise PermissionDenied("You can only submit your own purchase requests.")
        if purchase_request.status != PurchaseRequest.Status.DRAFT:
            return Response(
                {"detail": "Only draft purchase requests can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not purchase_request.items.exists():
            return Response(
                {"detail": "A purchase request must contain at least one item."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = purchase_request.status
        purchase_request.status = PurchaseRequest.Status.PENDING_APPROVAL
        purchase_request.save(update_fields=["status", "updated_at"])
        log_action(
            actor=request.user,
            action=AuditLog.Action.UPDATE,
            entity=purchase_request,
            old_values={"status": old_status},
            new_values={"status": purchase_request.status},
        )
        return Response(self.get_serializer(purchase_request).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        purchase_request = self.get_object()
        user = request.user
        if user.role != user.Role.MANAGER:
            raise PermissionDenied("Only managers can approve purchase requests.")
        if purchase_request.requester_id == user.id:
            raise PermissionDenied("You cannot approve your own purchase request.")
        if purchase_request.status != PurchaseRequest.Status.PENDING_APPROVAL:
            return Response(
                {"detail": "Only pending purchase requests can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = request.data.get("comment", "")
        Approval.objects.create(
            purchase_request=purchase_request,
            approver=user,
            status=Approval.Status.APPROVED,
            comment=comment,
        )
        old_status = purchase_request.status
        purchase_request.status = PurchaseRequest.Status.APPROVED
        purchase_request.save(update_fields=["status", "updated_at"])
        log_action(
            actor=user,
            action=AuditLog.Action.APPROVE,
            entity=purchase_request,
            old_values={"status": old_status},
            new_values={"status": purchase_request.status},
        )
        return Response(self.get_serializer(purchase_request).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reject(self, request, pk=None):
        purchase_request = self.get_object()
        user = request.user
        if user.role != user.Role.MANAGER:
            raise PermissionDenied("Only managers can reject purchase requests.")
        if purchase_request.requester_id == user.id:
            raise PermissionDenied("You cannot reject your own purchase request.")
        if purchase_request.status != PurchaseRequest.Status.PENDING_APPROVAL:
            return Response(
                {"detail": "Only pending purchase requests can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = request.data.get("comment", "")
        Approval.objects.create(
            purchase_request=purchase_request,
            approver=user,
            status=Approval.Status.REJECTED,
            comment=comment,
        )
        old_status = purchase_request.status
        purchase_request.status = PurchaseRequest.Status.REJECTED
        purchase_request.save(update_fields=["status", "updated_at"])
        log_action(
            actor=user,
            action=AuditLog.Action.REJECT,
            entity=purchase_request,
            old_values={"status": old_status},
            new_values={"status": purchase_request.status},
        )
        return Response(self.get_serializer(purchase_request).data)


class RFQViewSet(viewsets.ModelViewSet):
    serializer_class = RFQSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageProcurement]
    http_method_names = ["get", "post", "head", "options"]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return (
            RFQ.objects
            .filter(purchase_request__company=self.request.user.company)
            .select_related("purchase_request", "created_by")
            .prefetch_related("suppliers", "quotes", "quotes__supplier")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            rfq = serializer.save(created_by=self.request.user)
            log_action(
                actor=self.request.user,
                action=AuditLog.Action.CREATE,
                entity=rfq,
                new_values={
                    "status": rfq.status,
                    "purchase_request_id": rfq.purchase_request_id,
                },
            )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def send(self, request, pk=None):
        rfq = self.get_object()
        if rfq.status != RFQ.Status.DRAFT:
            return Response(
                {"detail": "Only draft RFQs can be sent."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not rfq.suppliers.exists():
            return Response(
                {"detail": "RFQ must contain at least one supplier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = rfq.status
        rfq.status = RFQ.Status.SENT
        rfq.save(update_fields=["status", "updated_at"])
        log_action(
            actor=request.user,
            action=AuditLog.Action.UPDATE,
            entity=rfq,
            old_values={"status": old_status},
            new_values={"status": rfq.status},
        )
        return Response(self.get_serializer(rfq).data)

    @action(detail=True, methods=["get"])
    def quotes(self, request, pk=None):
        rfq = self.get_object()
        quotes = (
            rfq.quotes
            .select_related("supplier")
            .order_by("total_amount", "delivery_days")
        )
        serializer = SupplierQuoteSerializer(
            quotes, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"quotes/(?P<quote_id>\d+)/select",
    )
    @transaction.atomic
    def select_quote(self, request, pk=None, quote_id=None):
        rfq = self.get_object()
        if rfq.status != RFQ.Status.SENT:
            return Response(
                {"detail": "A quote can only be selected from a sent RFQ."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_quote = (
                SupplierQuote.objects
                .select_related("supplier")
                .get(pk=quote_id, rfq=rfq)
            )
        except SupplierQuote.DoesNotExist:
            return Response(
                {"detail": "Quote not found for this RFQ."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if rfq.quotes.filter(status=SupplierQuote.Status.SELECTED).exists():
            return Response(
                {"detail": "A quote has already been selected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rfq.quotes.exclude(pk=selected_quote.pk).update(
            status=SupplierQuote.Status.REJECTED
        )
        selected_quote.status = SupplierQuote.Status.SELECTED
        selected_quote.save(update_fields=["status"])
        rfq.status = RFQ.Status.CLOSED
        rfq.save(update_fields=["status", "updated_at"])
        old_quote_status = selected_quote.status
        log_action(
        actor=request.user,
        action=AuditLog.Action.UPDATE,
        entity=selected_quote,
        old_values={"status": old_quote_status},
        new_values={"status": selected_quote.status},)

        return Response(
            SupplierQuoteSerializer(
                selected_quote, context={"request": request}
            ).data
        )


class SupplierQuoteViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierQuoteSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageProcurement]
    http_method_names = ["get", "post", "head", "options"]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return (
            SupplierQuote.objects
            .filter(rfq__purchase_request__company=self.request.user.company)
            .select_related("rfq", "supplier", "rfq__purchase_request")
            .order_by("-submitted_at")
        )


class PurchaseOrderViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseOrderSerializer
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return (
            PurchaseOrder.objects
            .filter(purchase_request__company=self.request.user.company)
            .select_related("purchase_request", "supplier", "selected_quote")
            .prefetch_related("items")
        )

    def _can_manage(self):
        return self.request.user.role in ["PROCUREMENT_OFFICER", "ADMIN"]

    def list(self, request):
        queryset = self.get_queryset()
        return Response(PurchaseOrderSerializer(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        po = self.get_object()
        return Response(PurchaseOrderSerializer(po).data)

    def create(self, request):
        if not self._can_manage():
            return Response(
                {"detail": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PurchaseOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        quote = get_object_or_404(
            SupplierQuote,
            pk=data["selected_quote_id"],
            rfq__purchase_request__company=request.user.company,
        )
        po = create_purchase_order(
            user=request.user,
            quote_id=quote.id,
            expected_date=data["expected_delivery_date"],
            items=data["items"],
        )
        return Response(
            PurchaseOrderSerializer(po).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        if not self._can_manage():
            return Response(
                {"detail": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN,
            )

        po = self.get_object()
        serializer = ReceivingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receiving = receive_purchase_order(
            user=request.user,
            po_id=po.id,
            items=serializer.validated_data["items"],
        )
        return Response(
            ReceivingSerializer(receiving).data,
            status=status.HTTP_201_CREATED,
        )
