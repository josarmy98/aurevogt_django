from rest_framework import serializers
from .models import Driver, LocationPing

class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = '__all__'

class LocationPingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationPing
        fields = '__all__'