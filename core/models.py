from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('field_worker', 'Field Worker'),
        ('manager', 'Manager'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='field_worker')

    def __str__(self):
        return f"{self.username} ({self.role})"


class Project(models.Model):
    name       = models.CharField(max_length=200, unique=True)
    code       = models.CharField(max_length=20, unique=True)
    city       = models.CharField(max_length=100)
    state      = models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]


class Route(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='routes')
    name    = models.CharField(max_length=200)
    area    = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.project.name} - {self.name}"

    class Meta:
        unique_together = ('project', 'name')
        indexes = [models.Index(fields=['project'])]


class MasterHousehold(models.Model):
    """
    Master list imported from Excel / Google Sheet.
    SOURCE OF TRUTH for total household count and missing detection.
    """
    house_id       = models.CharField(max_length=50)
    project        = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='master_households')
    sub_route      = models.CharField(max_length=200, blank=True)
    driver_name    = models.CharField(max_length=200, blank=True)
    area_name      = models.CharField(max_length=200, blank=True)
    hh_type        = models.CharField(max_length=50, blank=True)   # Household / Shop
    status         = models.CharField(max_length=50, default='Active')
    date_of_active = models.DateField(null=True, blank=True)
    is_active      = models.BooleanField(default=True)
    imported_at    = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.house_id} - {self.project.name}"

    class Meta:
        unique_together = ('house_id', 'project')
        indexes = [
            models.Index(fields=['project', 'is_active']),
            models.Index(fields=['house_id']),
            models.Index(fields=['project', 'area_name']),
            models.Index(fields=['project', 'driver_name']),
        ]


class Household(models.Model):
    """
    Auto-created when field staff submit an entry.
    Linked to MasterHousehold for validation.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('defaulter', 'Defaulter'),
    ]
    house_id              = models.CharField(max_length=50)
    project               = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='households')
    route                 = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL)
    owner_name            = models.CharField(max_length=200, blank=True)
    address               = models.TextField(blank=True)
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    registered_at         = models.DateField(auto_now_add=True)
    last_collection_date  = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.house_id} - {self.project.name}"

    class Meta:
        unique_together = ('house_id', 'project')
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['house_id']),
            models.Index(fields=['project', 'last_collection_date']),
        ]


class WasteCollection(models.Model):
    household   = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='collections')
    project     = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='collections')
    date        = models.DateField(db_index=True)
    waste_types = models.JSONField(default=list)
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='collections')
    notes       = models.TextField(blank=True)
    gps_lat     = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_lng     = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.household.house_id} - {self.date}"

    class Meta:
        unique_together = ('household', 'date')
        indexes = [
            models.Index(fields=['project', 'date']),
            models.Index(fields=['household', 'date']),
            models.Index(fields=['date']),
        ]


class MissedCollection(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    project   = models.ForeignKey(Project, on_delete=models.CASCADE)
    date      = models.DateField()
    notified  = models.BooleanField(default=False)

    class Meta:
        unique_together = ('household', 'date')
        indexes = [models.Index(fields=['project', 'date'])]


class Penalty(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('waived', 'Waived'),
    ]
    household   = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='penalties')
    project     = models.ForeignKey(Project, on_delete=models.CASCADE)
    week_start  = models.DateField()
    week_end    = models.DateField()
    missed_days = models.PositiveSmallIntegerField()
    amount      = models.DecimalField(max_digits=8, decimal_places=2)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('household', 'week_start')
        indexes = [models.Index(fields=['project', 'week_start', 'status'])]