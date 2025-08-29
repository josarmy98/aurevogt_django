from rest_framework import serializers
from .models import Package, PackageEvent, DeliveryAttempt, PodPhoto

class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = '__all__'

class DeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAttempt
        fields = '__all__'