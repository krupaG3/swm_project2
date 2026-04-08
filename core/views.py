from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from django.core.cache import cache
from datetime import date, timedelta
from collections import defaultdict
import json

from .models import (
    Project, Route, Household, WasteCollection,
    MissedCollection, Penalty, MasterHousehold
)
from .serializers import (
    ProjectSerializer, RouteSerializer, HouseholdSerializer,
    WasteCollectionSerializer, MissedCollectionSerializer,
    PenaltySerializer, UserSerializer
)
from .permissions import IsAdmin, IsAdminOrFieldWorker, IsAdminOrManager


# ─── Auth ────────────────────────────────────────────────────
class MeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ─── Projects ────────────────────────────────────────────────
class ProjectListView(generics.ListCreateAPIView):
    queryset           = Project.objects.filter(is_active=True)
    serializer_class   = ProjectSerializer
    permission_classes = [IsAuthenticated]


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = Project.objects.all()
    serializer_class   = ProjectSerializer
    permission_classes = [IsAdmin]


# ─── Routes ──────────────────────────────────────────────────
class RouteListView(generics.ListCreateAPIView):
    serializer_class   = RouteSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        pid = self.request.query_params.get('project')
        return Route.objects.filter(project_id=pid) if pid else Route.objects.all()


# ─── Collection Entry ────────────────────────────────────────
class CollectionCreateView(APIView):
    permission_classes = [IsAdminOrFieldWorker]

    def post(self, request):
        project_id  = request.data.get('project')
        house_id    = str(request.data.get('house_id', '')).strip().upper()
        waste_types = request.data.get('waste_types', [])
        entry_date  = request.data.get('date', str(date.today()))
        notes       = request.data.get('notes', '')

        if not project_id:
            return Response({"error": "Project is required."}, status=400)
        if not house_id:
            return Response({"error": "House ID is required."}, status=400)

        valid_types = {'dry', 'wet', 'mixed', 'hazardous', 'electric'}
        if not waste_types or not set(waste_types).issubset(valid_types):
            return Response({"error": "Select at least one valid waste type."}, status=400)

        try:
            project = Project.objects.get(id=project_id, is_active=True)
        except Project.DoesNotExist:
            return Response({"error": "Project not found."}, status=404)

        # Auto-create household if not exists
        household, created = Household.objects.get_or_create(
            house_id=house_id,
            project=project,
            defaults={'status': 'active'}
        )

        # Check duplicate
        if WasteCollection.objects.filter(household=household, date=entry_date).exists():
            return Response({
                "error": f"House {house_id} already submitted today.",
                "duplicate": True
            }, status=400)

        # Save entry
        WasteCollection.objects.create(
            household=household,
            project=project,
            date=entry_date,
            waste_types=waste_types,
            collected_by=request.user,
            notes=notes,
        )

        # Update household last collection date
        Household.objects.filter(id=household.id).update(
            last_collection_date=entry_date,
            status='active'
        )

        # Bust cache
        cache.delete(f"dashboard:daily:{project_id}:{entry_date}")
        cache.delete(f"missing:{project_id}:{entry_date}")
        cache.delete(f"dashboard:weekly:{project_id}")

        return Response({
            "success":          True,
            "message":          f"House {house_id} entry saved!",
            "house_id":         house_id,
            "entered_by":       request.user.username,
            "is_new_household": created,
            "waste_types":      waste_types,
            "date":             entry_date,
        }, status=201)


class DailyCollectionView(generics.ListAPIView):
    serializer_class   = WasteCollectionSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        pid  = self.request.query_params.get('project')
        d    = self.request.query_params.get('date', str(date.today()))
        return WasteCollection.objects.filter(
            project_id=pid, date=d
        ).select_related('household').order_by('-created_at')[:200]


# ─── Missing Households ──────────────────────────────────────
class MissingHouseholdsView(APIView):
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        project_id  = request.query_params.get('project')
        target_date = request.query_params.get('date', str(date.today()))

        if not project_id:
            return Response({"error": "project param required"}, status=400)

        cache_key = f"missing:{project_id}:{target_date}"
        cached    = cache.get(cache_key)
        if cached:
            return Response(json.loads(cached))

        # House IDs collected today
        collected_house_ids = set(
            WasteCollection.objects.filter(
                project_id=project_id, date=target_date
            ).values_list('household__house_id', flat=True)
        )

        # Master list house IDs
        master_qs = MasterHousehold.objects.filter(
            project_id=project_id, is_active=True
        ).values('house_id', 'driver_name', 'area_name', 'sub_route', 'hh_type')

        master_list  = list(master_qs)
        total_master = len(master_list)

        # Missing = in master list but NOT collected today
        missing_list = [
            h for h in master_list
            if h['house_id'] not in collected_house_ids
        ]

        result = {
            "date":               target_date,
            "total_master":       total_master,
            "collected_today":    len(collected_house_ids),
            "missing_count":      len(missing_list),
            "missing_households": missing_list,
        }

        cache.set(cache_key, json.dumps(result, default=str), 120)
        return Response(result)


# ─── Daily Dashboard ─────────────────────────────────────────
class DailyDashboardView(APIView):
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        project_id  = request.query_params.get('project')
        target_date = request.query_params.get('date', str(date.today()))

        if not project_id:
            return Response({"error": "project param required"}, status=400)

        cache_key = f"dashboard:daily:{project_id}:{target_date}"
        cached    = cache.get(cache_key)
        if cached:
            return Response(json.loads(cached))

        # Total from MASTER LIST (source of truth)
        total = MasterHousehold.objects.filter(
            project_id=project_id, is_active=True
        ).count()

        # Fallback if master list not yet imported
        if total == 0:
            total = Household.objects.filter(
                project_id=project_id, status='active'
            ).count()

        # Today's collections
        collections = list(
            WasteCollection.objects.filter(
                project_id=project_id, date=target_date
            ).values_list('waste_types', flat=True)
        )
        collected = len(collections)

        # Waste type distribution
        type_dist = {'dry': 0, 'wet': 0, 'mixed': 0, 'hazardous': 0, 'electric': 0}
        for waste_list in collections:
            for wtype in waste_list:
                if wtype in type_dist:
                    type_dist[wtype] += 1

        result = {
            "date":               target_date,
            "total_households":   total,
            "collected":          collected,
            "missing":            max(total - collected, 0),
            "coverage_pct":       round((collected / total * 100) if total > 0 else 0, 1),
            "waste_distribution": type_dist,
        }

        timeout = 300 if target_date != str(date.today()) else 60
        cache.set(cache_key, json.dumps(result), timeout)
        return Response(result)


# ─── Weekly Dashboard ────────────────────────────────────────
class WeeklyDashboardView(APIView):
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({"error": "project param required"}, status=400)

        cache_key = f"dashboard:weekly:{project_id}"
        cached    = cache.get(cache_key)
        if cached:
            return Response(json.loads(cached))

        today     = date.today()
        from_date = today - timedelta(days=6)

        # Single query for all 7 days
        collections = WasteCollection.objects.filter(
            project_id=project_id,
            date__range=(from_date, today)
        ).values('date', 'waste_types')

        daily_counts = defaultdict(lambda: {
            'dry': 0, 'wet': 0, 'mixed': 0,
            'hazardous': 0, 'electric': 0, 'total': 0
        })

        for entry in collections:
            d = str(entry['date'])
            daily_counts[d]['total'] += 1
            for wtype in entry['waste_types']:
                if wtype in daily_counts[d]:
                    daily_counts[d][wtype] += 1

        total = MasterHousehold.objects.filter(
            project_id=project_id, is_active=True
        ).count() or Household.objects.filter(
            project_id=project_id, status='active'
        ).count()

        week_data = []
        for i in range(6, -1, -1):
            d         = str(today - timedelta(days=i))
            counts    = daily_counts.get(d, {})
            collected = counts.get('total', 0)
            week_data.append({
                "date":         d,
                "collected":    collected,
                "total":        total,
                "coverage_pct": round((collected / total * 100) if total > 0 else 0, 1),
                "waste_counts": {
                    "dry":       counts.get('dry', 0),
                    "wet":       counts.get('wet', 0),
                    "mixed":     counts.get('mixed', 0),
                    "hazardous": counts.get('hazardous', 0),
                    "electric":  counts.get('electric', 0),
                }
            })

        result = {"project_id": project_id, "weekly_trend": week_data}
        cache.set(cache_key, json.dumps(result), 120)
        return Response(result)


# ─── Project Compare ─────────────────────────────────────────
class ProjectCompareView(APIView):
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        target_date = request.query_params.get('date', str(date.today()))
        cache_key   = f"dashboard:compare:{target_date}"
        cached      = cache.get(cache_key)
        if cached:
            return Response(json.loads(cached))

        collected_map = {
            row['project_id']: row['collected']
            for row in WasteCollection.objects.filter(date=target_date)
            .values('project_id').annotate(collected=Count('id'))
        }
        household_map = {
            row['project_id']: row['total']
            for row in MasterHousehold.objects.filter(is_active=True)
            .values('project_id').annotate(total=Count('id'))
        }

        result = []
        for p in Project.objects.filter(is_active=True):
            total     = household_map.get(p.id, 0)
            collected = collected_map.get(p.id, 0)
            result.append({
                "project_id":   p.id,
                "project_name": p.name,
                "total":        total,
                "collected":    collected,
                "missing":      max(total - collected, 0),
                "coverage_pct": round((collected / total * 100) if total > 0 else 0, 1),
            })

        result.sort(key=lambda x: x['coverage_pct'], reverse=True)
        cache.set(cache_key, json.dumps(result), 120)
        return Response(result)


# ─── Penalties ───────────────────────────────────────────────
class PenaltyListView(generics.ListAPIView):
    serializer_class   = PenaltySerializer
    permission_classes = [IsAdminOrManager]
    def get_queryset(self):
        pid = self.request.query_params.get('project')
        qs  = Penalty.objects.select_related('household').order_by('-created_at')
        return qs.filter(project_id=pid)[:200] if pid else qs[:200]