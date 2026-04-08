from rest_framework import serializers
from .models import (
    User, Project, Route, Household,
    WasteCollection, MissedCollection, Penalty
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role']


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = '__all__'


class HouseholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Household
        fields = '__all__'


class HouseholdSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Household
        fields = ['id', 'house_id', 'owner_name', 'address', 'status']


class WasteCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WasteCollection
        fields = '__all__'
        read_only_fields = ['collected_by', 'created_at']

    def validate(self, data):
        # Check duplicate entry for same house on same date
        qs = WasteCollection.objects.filter(
            household=data['household'],
            date=data['date']
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"detail": "This household already has an entry for today."}
            )
        return data

    def validate_waste_types(self, value):
        valid = {'dry', 'wet', 'mixed', 'hazardous', 'electric'}
        if not value:
            raise serializers.ValidationError("Select at least one waste type.")
        if not set(value).issubset(valid):
            raise serializers.ValidationError(
                f"Invalid waste type. Choose from: {valid}"
            )
        return value


class MissedCollectionSerializer(serializers.ModelSerializer):
    house_id = serializers.CharField(source='household.house_id', read_only=True)
    owner_name = serializers.CharField(source='household.owner_name', read_only=True)
    address = serializers.CharField(source='household.address', read_only=True)
    route_name = serializers.CharField(source='household.route.name', read_only=True)

    class Meta:
        model = MissedCollection
        fields = ['id', 'house_id', 'owner_name', 'address', 'route_name', 'date']


class PenaltySerializer(serializers.ModelSerializer):
    house_id = serializers.CharField(source='household.house_id', read_only=True)
    owner_name = serializers.CharField(source='household.owner_name', read_only=True)

    class Meta:
        model = Penalty
        fields = '__all__'