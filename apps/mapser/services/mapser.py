from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from apps.customers.models import Customer, CustomerAssignment
from apps.mapser.models import CustomerGeoProfile, DenueInegi
from apps.sales.services.routes import RoutesService


@dataclass
class MapserService:
    '''
    main service for geospatial and commercial coverage analysis in mapser
    '''
    user: Any
    customers_qs: QuerySet | None = None
    cleaned_data: dict[str, Any] | None = None
    default_center: tuple[float, float] = (23.6345, -102.5528)

    today: Any = field(init=False)
    allowed_routes_qs: QuerySet = field(init=False)

    def __post_init__(self):
        self.today = timezone.localdate()
        self._init_routes()

    def _init_routes(self) -> None:
        '''
        initializes allowed routes for current user
        '''
        routes_service = RoutesService(user=self.user)
        self.allowed_routes_qs = routes_service.get_allowed_routes(can_view=True, can_edit=False)

    def _get_allowed_customers_qs(self) -> QuerySet:
        '''
        returns active customers currently assigned to user allowed routes or provided queryset
        '''
        if self.customers_qs is not None:
            return self.customers_qs

        active_customer_ids = (
            CustomerAssignment.objects
            .filter(route__in=self.allowed_routes_qs)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=self.today))
            .values_list('customer_id', flat=True)
            .distinct()
        )
        return Customer.objects.filter(id__in=active_customer_ids)

    def read_geo_profiles(self) -> dict[str, Any]:
        '''
        returns allowed customers and their geo profiles separated by exact coordinates and postal code groups
        '''
        allowed_customers_qs = self._get_allowed_customers_qs()
        profiles_qs = CustomerGeoProfile.objects.filter(
            customer__in=allowed_customers_qs
        ).select_related('customer')

        exact_points = []
        postal_code_buckets = defaultdict(list)
        unresolved_clients = []

        for profile in profiles_qs:
            customer = profile.customer
            client_summary = {
                'customer_id': customer.id.upper(),
                'customer_name': customer.name.title(),
                'credit_limit': float(customer.credit_limit) if customer.credit_limit else 0.0,
                'zip_code': profile.zip_code.strip() if profile.zip_code else '',
                'municipality': profile.municipality.strip() if profile.municipality else '',
                'street_address': profile.street_address.strip() if profile.street_address else '',
            }

            if profile.has_coordinates:
                exact_points.append({
                    **client_summary,
                    'lat': float(profile.latitude),
                    'lng': float(profile.longitude),
                    'is_approximate': False,
                    'source_label': 'GPS Exacto',
                })
            elif client_summary['zip_code']:
                postal_code_buckets[client_summary['zip_code']].append(client_summary)
            else:
                unresolved_clients.append(client_summary)

        postal_code_groups = []
        if postal_code_buckets:
            zip_codes_list = list(postal_code_buckets.keys())

            denue_centroids = (
                DenueInegi.objects.filter(
                    zip_code__in=zip_codes_list,
                    latitude__isnull=False,
                    longitude__isnull=False
                )
                .values('zip_code')
                .annotate(
                    avg_lat=Avg('latitude'),
                    avg_lng=Avg('longitude'),
                    denue_count=Count('id')
                )
            )

            centroids_map = {
                item['zip_code']: {
                    'lat': float(item['avg_lat']),
                    'lng': float(item['avg_lng']),
                    'denue_count': item['denue_count'],
                }
                for item in denue_centroids
                if item['avg_lat'] is not None and item['avg_lng'] is not None
            }

            for cp, clients in postal_code_buckets.items():
                centroid = centroids_map.get(cp)
                if centroid:
                    total_credit = sum(c['credit_limit'] for c in clients)
                    postal_code_groups.append({
                        'zip_code': cp,
                        'total_customers': len(clients),
                        'total_credit_limit': total_credit,
                        'lat': centroid['lat'],
                        'lng': centroid['lng'],
                        'denue_reference_count': centroid['denue_count'],
                        'is_approximate': True,
                        'source_label': f'Agrupado por CP ({cp})',
                        'customers': clients,
                    })
                else:
                    unresolved_clients.extend(clients)

        return {
            'exact_points': exact_points,
            'postal_code_groups': postal_code_groups,
            'unresolved_clients': unresolved_clients,
            'total_allowed_customers': allowed_customers_qs.count(),
            'total_geolocated': len(exact_points) + sum(g['total_customers'] for g in postal_code_groups),
        }

    def _get_filtered_denue_qs(self) -> QuerySet:
        '''
        returns filtered denue queryset based on cleaned_data parameters
        '''
        denue_qs = DenueInegi.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        )

        if self.cleaned_data:
            state_filter = self.cleaned_data.get('state') or self.cleaned_data.get('state_code')
            if state_filter:
                if isinstance(state_filter, (list, tuple, set)):
                    state_codes = [str(v).zfill(2) for v in state_filter if v]
                    if state_codes:
                        denue_qs = denue_qs.filter(state_code__in=state_codes)
                else:
                    denue_qs = denue_qs.filter(state_code=str(state_filter).zfill(2))

            if self.cleaned_data.get('municipality_code'):
                denue_qs = denue_qs.filter(municipality_code=self.cleaned_data['municipality_code'])
            if self.cleaned_data.get('scian_code'):
                denue_qs = denue_qs.filter(scian_code__startswith=self.cleaned_data['scian_code'])
            if self.cleaned_data.get('zip_code'):
                denue_qs = denue_qs.filter(zip_code=self.cleaned_data['zip_code'])

        return denue_qs

    def read_denues(self, limit: int | None = None) -> list[dict[str, Any]]:
        '''
        returns potential customers from denue inegi
        '''
        denue_qs = self._get_filtered_denue_qs()

        if limit:
            denue_qs = denue_qs[:limit]

        denue_values = denue_qs.values(
            'id', 'unit_name', 'tax_name', 'scian_code', 'scian_name',
            'personal_occupied_stratum', 'zip_code', 'municipality_name',
            'settlement_name', 'latitude', 'longitude'
        )

        points = []
        for item in denue_values:
            points.append({
                'id': item['id'],
                'unit_name': item['unit_name'],
                'tax_name': item['tax_name'],
                'scian_code': item['scian_code'],
                'scian_name': item['scian_name'],
                'personal_occupied_stratum': item['personal_occupied_stratum'],
                'zip_code': item['zip_code'],
                'municipality': item['municipality_name'],
                'neighborhood': item['settlement_name'],
                'lat': float(item['latitude']),
                'lng': float(item['longitude']),
            })

        return points

    def get_stats(self) -> dict[str, Any]:
        '''
        returns high-level market metrics for the current user
        '''
        denue_total = self._get_filtered_denue_qs().count()
        allowed_customers_count = self._get_allowed_customers_qs().count()

        geo_data = self.read_geo_profiles()
        geolocated_count = geo_data['total_geolocated']

        if denue_total > 0:
            market_share = round((allowed_customers_count / denue_total) * 100, 2)
            untapped = max(0, denue_total - allowed_customers_count)
        else:
            market_share = 0.0
            untapped = 0

        return {
            'denue_total': denue_total,
            'customers_total': allowed_customers_count,
            'geocoded_customers': geolocated_count,
            'market_share_percentage': market_share,
            'untapped_opportunities': untapped,
            'exact_count': len(geo_data['exact_points']),
            'postal_code_groups_count': len(geo_data['postal_code_groups']),
            'unresolved_count': len(geo_data['unresolved_clients']),
        }

    get_kpis = get_stats