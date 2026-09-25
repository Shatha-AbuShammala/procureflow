from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound
from .serializers import CompanySerializer
class MyCompanyView(generics.RetrieveAPIView):
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        company = self.request.user.company

        if company is None:
            raise NotFound("This user is not assigned to a company.")

        return company