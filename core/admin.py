import csv
import io
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.safestring import mark_safe
from django import forms
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import path
from .models import (
    User, Project, Route, MasterHousehold,
    Household, WasteCollection, MissedCollection, Penalty
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'is_active']
    list_filter  = ['role']
    fieldsets    = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display  = ['name', 'code', 'city', 'state', 'is_active']
    list_filter   = ['is_active', 'state']
    search_fields = ['name', 'code', 'city']


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display  = ['name', 'project', 'area']
    list_filter   = ['project']
    search_fields = ['name', 'area']


WASTE_CHOICES = [
    ('dry',       '🟦 Dry'),
    ('wet',       '🟩 Wet'),
    ('mixed',     '🟧 Mixed'),
    ('hazardous', '🟥 Hazardous'),
    ('electric',  '🟪 Electric'),
]

WASTE_COLORS = {
    'dry': '#1565c0', 'wet': '#00695c',
    'mixed': '#e65100', 'hazardous': '#b71c1c', 'electric': '#6a1b9a',
}

WASTE_ICONS = {
    'dry': '🟦', 'wet': '🟩',
    'mixed': '🟧', 'hazardous': '🟥', 'electric': '🟪'
}


class WasteTypeMultipleField(forms.MultipleChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['choices']  = WASTE_CHOICES
        kwargs['widget']   = forms.CheckboxSelectMultiple(
            attrs={'style': 'margin-right:6px;width:16px;height:16px;'}
        )
        kwargs['required'] = False
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except Exception:
                return []
        return value or []


@admin.register(WasteCollection)
class WasteCollectionAdmin(admin.ModelAdmin):
    list_display   = ['household', 'project', 'date', 'show_waste_types', 'collected_by', 'created_at']
    list_filter    = ['project', 'date']
    search_fields  = ['household__house_id']
    date_hierarchy = 'date'

    def show_waste_types(self, obj):
        if not obj.waste_types:
            return '-'
        badges = []
        for wtype in obj.waste_types:
            color = WASTE_COLORS.get(wtype, '#333')
            icon  = WASTE_ICONS.get(wtype, '⬜')
            badges.append(
                f'<span style="background:{color};color:white;'
                f'padding:3px 10px;border-radius:12px;'
                f'font-size:12px;margin-right:4px;">'
                f'{icon} {wtype.capitalize()}</span>'
            )
        return mark_safe(''.join(badges))
    show_waste_types.short_description = 'Waste Types'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['waste_types'] = WasteTypeMultipleField()
        return form

    def save_model(self, request, obj, form, change):
        obj.waste_types = form.cleaned_data.get('waste_types', [])
        super().save_model(request, obj, form, change)


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display  = ['house_id', 'project', 'owner_name', 'status', 'last_collection_date']
    list_filter   = ['project', 'status']
    search_fields = ['house_id', 'owner_name']


@admin.register(MissedCollection)
class MissedCollectionAdmin(admin.ModelAdmin):
    list_display  = ['household', 'project', 'date', 'notified']
    list_filter   = ['project', 'date']
    search_fields = ['household__house_id']


@admin.register(Penalty)
class PenaltyAdmin(admin.ModelAdmin):
    list_display  = ['household', 'project', 'week_start', 'missed_days', 'amount', 'status']
    list_filter   = ['project', 'status']
    search_fields = ['household__house_id']


# ── MasterHousehold with Excel/CSV Import ─────────────────────
@admin.register(MasterHousehold)
class MasterHouseholdAdmin(admin.ModelAdmin):
    list_display        = ['house_id', 'project', 'sub_route', 'driver_name', 'area_name', 'hh_type', 'is_active']
    list_filter         = ['project', 'is_active', 'hh_type', 'driver_name', 'area_name']
    search_fields       = ['house_id', 'driver_name', 'area_name']
    change_list_template = 'admin/master_household_changelist.html'

    def get_urls(self):
        urls   = super().get_urls()
        custom = [path('import-file/', self.import_file, name='import-master-file')]
        return custom + urls

    def import_file(self, request):
        if request.method == 'POST':
            upload     = request.FILES.get('data_file')
            project_id = request.POST.get('project')

            if not upload or not project_id:
                messages.error(request, 'Please select both a project and a file.')
                return redirect('..')

            try:
                project = Project.objects.get(id=project_id)
                fname   = upload.name.lower()

                # ── Read rows based on file type ──────────────
                if fname.endswith('.xlsx') or fname.endswith('.xls'):
                    import openpyxl
                    wb   = openpyxl.load_workbook(upload, read_only=True)
                    ws   = wb.active
                    rows = list(ws.iter_rows(values_only=True))
                    # First row = headers
                    headers = [str(h).strip().lower().replace(' ', '_') if h else '' for h in rows[0]]
                    data_rows = rows[1:]
                else:
                    # CSV fallback
                    decoded   = upload.read().decode('utf-8')
                    reader    = csv.DictReader(io.StringIO(decoded))
                    headers   = None
                    data_rows = list(reader)

                created_count = 0
                updated_count = 0

                for row in data_rows:
                    # Handle both xlsx (tuple) and csv (dict)
                    if isinstance(row, (tuple, list)):
                        row_dict = dict(zip(headers, row))
                    else:
                        row_dict = {k.strip().lower().replace(' ', '_'): v for k, v in row.items()}

                    # Map column names flexibly
                    house_id = str(
                        row_dict.get('hh_number') or
                        row_dict.get('hh_no') or
                        row_dict.get('house_id') or
                        row_dict.get('id') or ''
                    ).strip().upper()

                    if not house_id or house_id == 'NONE':
                        continue

                    # Date handling
                    date_active = row_dict.get('date_of_active')
                    if hasattr(date_active, 'date'):
                        date_active = date_active.date()
                    elif isinstance(date_active, str):
                        try:
                            from datetime import datetime
                            date_active = datetime.strptime(date_active, '%Y-%m-%d').date()
                        except Exception:
                            date_active = None
                    else:
                        date_active = None

                    obj, created = MasterHousehold.objects.update_or_create(
                        house_id=house_id,
                        project=project,
                        defaults={
                            'sub_route':      str(row_dict.get('sub_route') or '').strip(),
                            'driver_name':    str(row_dict.get('driver_name') or '').strip(),
                            'area_name':      str(row_dict.get('area_name') or '').strip(),
                            'hh_type':        str(row_dict.get('type') or 'Household').strip(),
                            'status':         str(row_dict.get('status') or 'Active').strip(),
                            'date_of_active': date_active,
                            'is_active':      True,
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                messages.success(
                    request,
                    f'✅ Done! {created_count} new households, {updated_count} updated for "{project.name}"'
                )
                return redirect('..')

            except Exception as e:
                messages.error(request, f'❌ Error: {str(e)}')
                return redirect('..')

        projects = Project.objects.filter(is_active=True)
        return render(request, 'admin/import_file.html', {'projects': projects})