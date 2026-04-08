from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path('auth/login/',   TokenObtainPairView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(),    name='refresh'),
    path('auth/me/',      views.MeView.as_view(),        name='me'),

    # Projects
    path('projects/',          views.ProjectListView.as_view(),   name='projects'),
    path('projects/<int:pk>/', views.ProjectDetailView.as_view(), name='project-detail'),

    # Routes
    path('routes/', views.RouteListView.as_view(), name='routes'),

    # Collections
    path('collections/',       views.CollectionCreateView.as_view(), name='collection-create'),
    path('collections/daily/', views.DailyCollectionView.as_view(),  name='collection-daily'),

    # Alerts
    path('alerts/missing/', views.MissingHouseholdsView.as_view(), name='missing'),

    # Dashboard
    path('dashboard/daily/',   views.DailyDashboardView.as_view(),  name='dashboard-daily'),
    path('dashboard/weekly/',  views.WeeklyDashboardView.as_view(), name='dashboard-weekly'),
    path('dashboard/compare/', views.ProjectCompareView.as_view(),  name='dashboard-compare'),

    # Penalties
    path('penalties/', views.PenaltyListView.as_view(), name='penalties'),
]