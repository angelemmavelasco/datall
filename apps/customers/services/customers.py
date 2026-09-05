from dataclasses import dataclass
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from decimal import Decimal
from django.db.models import (
    Q,
    QuerySet,
    Exists,
    OuterRef,
    Subquery,
    Case,
    When,
    Value,
    BooleanField,
    Prefetch,
    Count,
    Sum,
    Avg,
)

from apps.core.services.uploads import BaseETLHelper
from django.contrib.contenttypes.models import ContentType
from apps.core.models import Reference
from apps.sales.models import Route
import datetime

from apps.core.services.users import UsersService
from apps.sales.services.routes import RoutesService
from ..models import (
    CustomerType,
    Customer,
    CustomerAssignment,
    CustomerClassMargin,
)

class ServiceError(Exception):
    pass

class PermissionsError(ServiceError):
    pass

class CustomerNotFound(ServiceError):
    pass

class CustomerTypeNotFound(ServiceError):
    pass

@dataclass
class CustomersService(UsersService):
    customer_model: type = Customer
    customer_type_model: type = CustomerType
    customer_assignment_model: type = CustomerAssignment
    customer_class_margin_model: type = CustomerClassMargin
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_clientes',
        'clientes',
        'acceso_total_ventas',
        'acceso_total',
    )

    def get_allowed_customers(self, *, can_view: bool = True, can_edit: bool = False) -> QuerySet:
        """
        returns a qs with the allowed customers by the main user.

        params:
        -------
            can_view: bool = True -> if true, adds customers the user can view
            can_edit: bool = False -> if true, adds customers the user can edit

        returns:
        --------
            QuerySet: filtered queryset

        exceptions:
        -----------
            ValueError: if can_view and can_edit are both False
        """
        if not can_view and not can_edit:
            raise ValueError('El filtro can_view y can_edit no pueden ser ambos falsos')

        base_qs = self.customer_model.objects.select_related('customer_type', 'geo_profile')

        if self.has_full_access:
            return base_qs.annotate(
                can_view=Value(True, output_field=BooleanField()),
                can_edit=Value(True, output_field=BooleanField()),
            )

        today = timezone.now().date()
        routes_service = RoutesService(user=self.user)
        allowed_routes_qs = routes_service.get_allowed_routes(can_view=True, can_edit=False)

        has_allowed_route_assignment = Exists(
            self.customer_assignment_model.objects.filter(
                customer=OuterRef('pk'),
                route__in=allowed_routes_qs,
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            )
        )

        annotated_qs = base_qs.annotate(
            can_view=Case(
                When(has_allowed_route_assignment, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            can_edit=Value(False, output_field=BooleanField())
        )

        if can_view and can_edit:
            return annotated_qs.filter(Q(can_view=True) | Q(can_edit=True))
        elif can_edit:
            return annotated_qs.filter(can_edit=True)
        else:
            return annotated_qs.filter(can_view=True)

    def read_customers(self) -> QuerySet:
        """
        returns the qs with the allowed customers for the main user annotated with:
        - select_related: customer_type
        - annotations: can_view, can_edit, current_route_id, current_route_name,
                       current_route_business_unit, current_route_sale_channel,
                       current_assignment_start_date
        - prefetch_related: assignments (with route and details)
        - ordering: name, id

        returns:
        --------
            QuerySet: filtered queryset
        """
        today = timezone.now().date()

        active_assignment_qs = self.customer_assignment_model.objects.filter(
            customer=OuterRef('pk')
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).order_by('-start_date')

        base_qs = self.get_allowed_customers(can_view=True, can_edit=False)

        return base_qs.annotate(
            current_route_id=Subquery(active_assignment_qs.values('route__id')[:1]),
            current_route_name=Subquery(active_assignment_qs.values('route__name')[:1]),
            current_route_business_unit=Subquery(active_assignment_qs.values('route__business_unit__name')[:1]),
            current_route_sale_channel=Subquery(active_assignment_qs.values('route__sale_channel__name')[:1]),
            current_assignment_start_date=Subquery(active_assignment_qs.values('start_date')[:1]),
        ).prefetch_related(
            Prefetch(
                'assignments',
                queryset=self.customer_assignment_model.objects.select_related(
                    'route',
                    'route__business_unit',
                    'route__sale_channel',
                    'route__route_type'
                ).order_by('-start_date'),
            ),
            Prefetch(
                'class_margins',
                queryset=self.customer_class_margin_model.objects.select_related(
                    'product_class',
                    'product_class__product_category',
                ).order_by('product_class__name', 'product_class__id'),
            )
        ).order_by('name', 'id')

    def read_customer(self, *, pk: str) -> Customer:
        """
        returns a single customer with the same annotations and prefetch_related as read_customers.

        params:
        -------
            pk: str -> id of the customer to read

        returns:
        --------
            Customer: filtered customer object

        exceptions:
        -----------
            CustomerNotFound: if the customer does not exist
            PermissionsError: if the user does not have permission to access the customer
        """
        customer = self.read_customers().filter(pk=pk).first()
        if customer:
            return customer

        if self.customer_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al cliente con ID "{pk}".')

        raise CustomerNotFound(f'No se encontró ningún cliente con el ID "{pk}".')

    def can_edit_customer_geo_profile(self, customer: Customer | str) -> bool:
        """
        determines if user can edit customer geo profile.
        returns true if user has full access or has an active route assignment
        matching the customer's current active route assignment.
        """
        if self.has_full_access:
            return True

        today = timezone.localdate()
        from apps.sales.models import RouteAssignment
        user_active_routes = RouteAssignment.objects.filter(
            employee__user=self.user,
            date_start__lte=today,
        ).filter(
            Q(date_end__isnull=True) | Q(date_end__gte=today)
        ).values_list('route_id', flat=True)

        if not user_active_routes:
            return False

        customer_id = customer.pk if hasattr(customer, 'pk') else customer
        return self.customer_assignment_model.objects.filter(
            customer_id=customer_id,
            route_id__in=user_active_routes,
            start_date__lte=today,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).exists()

    def update_or_create_geo_profile(
            self,
            *,
            customer: Customer | str,
            geo_data: dict,
        ):
        """
        creates or updates the customer geographic profile
        """
        from apps.mapser.models import CustomerGeoProfile

        customer_obj = customer if isinstance(customer, Customer) else self.customer_model.objects.get(pk=customer)
        geo_profile = getattr(customer_obj, 'geo_profile', None)
        if not geo_profile:
            geo_profile = CustomerGeoProfile.objects.filter(customer=customer_obj).first()
        if not geo_profile:
            geo_profile = CustomerGeoProfile(customer=customer_obj)

        data = dict(geo_data or {})
        data.pop('id', None)
        data.pop('customer', None)

        lat = data.get('latitude')
        lng = data.get('longitude')
        if lat is not None and str(lat).strip() != '':
            lat = round(Decimal(str(lat).strip()), 9)
            data['latitude'] = lat
        else:
            lat = None
            data['latitude'] = None

        if lng is not None and str(lng).strip() != '':
            lng = round(Decimal(str(lng).strip()), 9)
            data['longitude'] = lng
        else:
            lng = None
            data['longitude'] = None

        coords_changed = (geo_profile.latitude != lat or geo_profile.longitude != lng)
        if lat is not None and lng is not None:
            if coords_changed or geo_profile.geocoding_source in [
                CustomerGeoProfile.GeocodingSource.UNRESOLVED,
                CustomerGeoProfile.GeocodingSource.POSTAL_CODE,
                '',
            ]:
                geo_profile.geocoding_source = CustomerGeoProfile.GeocodingSource.MANUAL
            geo_profile.last_geocoded_at = timezone.now()
        elif lat is None and lng is None:
            geo_profile.geocoding_source = CustomerGeoProfile.GeocodingSource.UNRESOLVED

        for key, value in data.items():
            setattr(geo_profile, key, value)

        geo_profile.full_clean()
        geo_profile.save()
        return geo_profile

    def create_customer(
        self,
        customer_data: dict = None,
        assignments_data: list = None,
        class_margins_data: list = None,
        geo_profile_data: dict = None,
        **kwargs
    ) -> Customer:
        """
        creates a new customer along with optional route assignments and class margins
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para registrar clientes.')

        data = dict(customer_data or {})
        data.update(kwargs)

        try:
            with transaction.atomic():
                new_customer = self.customer_model(**data)
                new_customer.full_clean()
                new_customer.save()

                if assignments_data:
                    for assignment_data in assignments_data:
                        if assignment_data and not assignment_data.get('DELETE', False):
                            assign_copy = dict(assignment_data)
                            assign_copy.pop('DELETE', None)
                            assign_copy.pop('id', None)
                            assign_copy.pop('customer', None)

                            assignment = self.customer_assignment_model(customer=new_customer, **assign_copy)
                            assignment.full_clean()
                            assignment.save()

                if class_margins_data:
                    for margin_data in class_margins_data:
                        if margin_data and not margin_data.get('DELETE', False):
                            margin_copy = dict(margin_data)
                            margin_copy.pop('DELETE', None)
                            margin_copy.pop('id', None)
                            margin_copy.pop('customer', None)

                            margin = self.customer_class_margin_model(customer=new_customer, **margin_copy)
                            margin.full_clean()
                            margin.save()

                if geo_profile_data:
                    self.update_or_create_geo_profile(
                        customer=new_customer,
                        geo_data=geo_profile_data,
                    )

            return new_customer

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en base de datos (clave duplicada o restricción violada): {str(e)}")
        except Exception as e:
            raise ServiceError(f"Error al registrar el cliente: {str(e)}")

    def update_customer(
        self,
        *,
        pk: str,
        customer_data: dict = None,
        assignments_data: list = None,
        class_margins_data: list = None,
        geo_profile_data: dict = None,
        **kwargs
    ) -> Customer:
        """
        updates an existing customer along with route assignments and class margins
        """
        customer_to_update = self.read_customer(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar clientes.')

        data = dict(customer_data or {})
        data.update(kwargs)

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(customer_to_update, attr, value)

                customer_to_update.full_clean()
                customer_to_update.save()

                if assignments_data is not None:
                    for assignment_data in assignments_data:
                        if not assignment_data:
                            continue

                        assignment_instance = assignment_data.get('id')
                        should_delete = assignment_data.get('DELETE', False)

                        if should_delete:
                            if assignment_instance and assignment_instance.pk:
                                assignment_instance.delete()
                            continue

                        assign_copy = dict(assignment_data)
                        assign_copy.pop('DELETE', None)
                        assign_copy.pop('id', None)
                        assign_copy.pop('customer', None)

                        if assignment_instance and assignment_instance.pk:
                            for k, v in assign_copy.items():
                                setattr(assignment_instance, k, v)
                            assignment_instance.full_clean()
                            assignment_instance.save()
                        else:
                            new_assignment = self.customer_assignment_model(customer=customer_to_update, **assign_copy)
                            new_assignment.full_clean()
                            new_assignment.save()

                if class_margins_data is not None:
                    for margin_data in class_margins_data:
                        if not margin_data:
                            continue

                        margin_instance = margin_data.get('id')
                        should_delete = margin_data.get('DELETE', False)

                        if should_delete:
                            if margin_instance and getattr(margin_instance, 'pk', None):
                                margin_instance.delete()
                            continue

                        margin_copy = dict(margin_data)
                        margin_copy.pop('DELETE', None)
                        margin_copy.pop('id', None)
                        margin_copy.pop('customer', None)

                        if margin_instance and getattr(margin_instance, 'pk', None):
                            for k, v in margin_copy.items():
                                setattr(margin_instance, k, v)
                            margin_instance.full_clean()
                            margin_instance.save()
                        else:
                            new_margin = self.customer_class_margin_model(customer=customer_to_update, **margin_copy)
                            new_margin.full_clean()
                            new_margin.save()

                if geo_profile_data is not None:
                    self.update_or_create_geo_profile(
                        customer=customer_to_update,
                        geo_data=geo_profile_data,
                    )

            return customer_to_update

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en base de datos: {str(e)}")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el cliente: {str(e)}")

    def delete_customer(self, *, pk: str) -> None:
        """
        deletes a customer by id
        """
        customer_to_delete = self.read_customer(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para eliminar clientes.')

        try:
            with transaction.atomic():
                customer_to_delete.delete()
        except IntegrityError:
            raise ServiceError("No se puede eliminar el cliente porque tiene asignaciones u otros registros vinculados.")
        except Exception as e:
            raise ServiceError(f"Error al eliminar el cliente: {str(e)}")

    def _clean_customers(self, file_obj) -> tuple[bool, str | object]:
        import traceback
        print(f"\n[CUSTOMERS-ETL] ===== Iniciando proceso de limpieza de clientes =====", flush=True)

        try:
            import pandas as pd
        except ImportError:
            err = "La librería 'pandas' no está instalada en el entorno."
            print(f"[CUSTOMERS-ETL ERROR] {err}", flush=True)
            return False, err

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            print(f"[CUSTOMERS-ETL ERROR] Falló la lectura del DataFrame: {df_or_err}", flush=True)
            return False, df_or_err

        df = df_or_err
        print(f"[CUSTOMERS-ETL] Columnas originales leídas del archivo: {list(df.columns)}", flush=True)

        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.customer_model,
            submodule_url_name='core:upload_options_list_view',
            context='columna'
        )
        df = BaseETLHelper.resolve_foreign_key_columns(df, self.customer_model)
        print(f"[CUSTOMERS-ETL] Columnas tras mapeo de Referencias y claves foráneas: {list(df.columns)}", flush=True)

        if 'route' in df.columns and 'route_id' not in df.columns:
            df.rename(columns={'route': 'route_id'}, inplace=True)

        is_req_valid, req_msg = BaseETLHelper.validate_required_columns(df, {'id': 'Identificador de Cliente'})
        if not is_req_valid:
            print(f"[CUSTOMERS-ETL ERROR] Validación de columnas requeridas falló: {req_msg}", flush=True)
            return False, req_msg

        if not self.customer_type_model.objects.exists():
            err = "No existen registros en el catálogo de Tipos de Cliente. Debes crear al menos un Tipo de Cliente antes de importar clientes."
            print(f"[CUSTOMERS-ETL ERROR] {err}", flush=True)
            return False, err

        valid_types_dict = {str(t.id).strip().lower(): t.id for t in self.customer_type_model.objects.all()}
        default_type = valid_types_dict.get('otr') or next(iter(valid_types_dict.values()))
        print(f"[CUSTOMERS-ETL] Tipos de cliente válidos en BD: {list(valid_types_dict.keys())} (Tipo por defecto: '{default_type}')", flush=True)

        if 'customer_type_id' in df.columns:
            df = BaseETLHelper.apply_reference_value_mappings(
                df,
                column='customer_type_id',
                target_model=self.customer_type_model,
                context='valor_tipo_cliente',
                submodule_url_name='core:upload_options_list_view'
            )

            df['customer_type_id'] = df['customer_type_id'].apply(
                lambda x: valid_types_dict.get(str(x).strip().lower(), default_type) if x not in (None, 'None', 'nan', '') else default_type
            )
        else:
            df['customer_type_id'] = default_type

        #universal Foreign Key validation for customer model
        is_fk_valid, fk_msg = BaseETLHelper.validate_foreign_keys(df, self.customer_model)
        if not is_fk_valid:
            print(f"[CUSTOMERS-ETL ERROR] Validación FK de Cliente falló: {fk_msg}", flush=True)
            return False, fk_msg

        #if route_id is provided, validate against route table
        if 'route_id' in df.columns:
            # normalize route_id casing against existing routes in DB
            valid_routes_db = {str(r).strip().lower(): r for r in Route.objects.values_list('id', flat=True)}
            df['route_id'] = df['route_id'].apply(
                lambda x: valid_routes_db.get(str(x).strip().lower(), str(x).strip()) if x not in (None, 'None', 'nan', '') else None
            )

            is_route_fk_valid, route_fk_msg = BaseETLHelper.validate_foreign_keys(
                df, self.customer_assignment_model, fields=['route_id']
            )
            if not is_route_fk_valid:
                print(f"[CUSTOMERS-ETL ERROR] Validación FK de Rutas falló: {route_fk_msg}", flush=True)
                return False, route_fk_msg

        if 'registration_date' in df.columns:
            df['registration_date'] = pd.to_datetime(df['registration_date'], errors='coerce')
            df['registration_date'] = df['registration_date'].fillna(pd.Timestamp('2020-01-01')).dt.date
        else:
            df['registration_date'] = datetime.datetime.strptime('2020-01-01', '%Y-%m-%d').date()

        if 'credit_limit' in df.columns:
            df['credit_limit'] = pd.to_numeric(
                df['credit_limit'].astype(str).str.replace(r'[$, ]', '', regex=True),
                errors='coerce'
            ).fillna(0.0)

        if 'credit_days' in df.columns:
            df['credit_days'] = pd.to_numeric(
                df['credit_days'],
                errors='coerce'
            ).fillna(0).astype(int)

        df['id'] = df['id'].astype(str).str.strip()
        if 'name' in df.columns:
            df['name'] = df['name'].astype(str).str.strip()
            df['name'] = df['name'].replace({'nan': None, 'NaN': None, 'None': None, '': None}).fillna(df['id'])
        else:
            df['name'] = df['id']

        #discard invalid / empty IDs
        df = df[df['id'].notnull() & ~df['id'].str.lower().isin(['none', 'nan', 'null', ''])]
        
        #deduplicate by customer id keeping last occurrence
        initial_len = len(df)
        df = df.drop_duplicates(subset=['id'], keep='last')
        if len(df) < initial_len:
            print(f"[CUSTOMERS-ETL] Se eliminaron {initial_len - len(df)} registros con ID duplicado en el archivo.", flush=True)

        df = df.where(pd.notnull(df), None)
        print(f"[CUSTOMERS-ETL SUCCESS] Limpieza completada. {len(df)} clientes listos para procesar.\n", flush=True)

        return True, df


    def bulk_create_customers(self, file_obj) -> object:
        import traceback
        from apps.core.services.uploads import ImportResult, PermissionsError, BaseETLHelper
        from apps.sales.models import Route
        from django.db import transaction

        print(f"\n[CUSTOMERS-BULK] ===== Iniciando bulk_create_customers =====", flush=True)

        if not self.has_full_access:
            err_msg = 'No tienes permisos suficientes para realizar cargas masivas de clientes.'
            print(f"[CUSTOMERS-BULK PERMISSIONS ERROR] {err_msg}", flush=True)
            raise PermissionsError(err_msg)

        is_valid, df_or_err = self._clean_customers(file_obj)
        if not is_valid:
            print(f"[CUSTOMERS-BULK VALIDATION ERROR] {df_or_err}", flush=True)
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        created_count = 0
        updated_count = 0
        total_processed = 0

        model_fields = [f.name for f in self.customer_model._meta.get_fields() if not f.is_relation]
        model_fields.extend([f.attname for f in self.customer_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
        
        valid_columns = [col for col in df.columns if col in model_fields and col != 'opinion_leader']
        print(f"[CUSTOMERS-BULK] Columnas válidas que se guardarán en Customer: {valid_columns}", flush=True)

        ids_in_df = df['id'].dropna().astype(str).tolist()
        existing_customers = self.customer_model.objects.in_bulk(ids_in_df)
        print(f"[CUSTOMERS-BULK] Total IDs en archivo: {len(ids_in_df)} | Clientes existentes en BD: {len(existing_customers)}", flush=True)

        today = timezone.now().date()
        yesterday = today - timezone.timedelta(days=1)

        active_assignments = {
            assign.customer_id: assign
            for assign in self.customer_assignment_model.objects.filter(
                customer_id__in=ids_in_df,
                end_date__isnull=True
            )
        }
        print(f"[CUSTOMERS-BULK] Asignaciones de ruta activas encontradas: {len(active_assignments)}", flush=True)

        valid_routes = set(Route.objects.values_list('id', flat=True))
        valid_routes_map = {str(r).strip().lower(): r for r in valid_routes}

        customers_to_create = []
        customers_to_update = []
        assignments_to_update = []
        assignments_to_create = []
        seen_customer_ids = set()

        for idx, row in df.iterrows():
            cid = str(row.get('id')).strip()
            if not cid or cid.lower() in ('none', 'nan', 'null', ''):
                continue

            if cid in seen_customer_ids:
                continue
            seen_customer_ids.add(cid)

            data = {}
            for col in valid_columns:
                val = row[col]
                if val is not None and str(val).lower() != 'nan':
                    data[col] = val
            data['id'] = cid
            raw_route = row.get('route_id')
            route_id = None
            if raw_route is not None:
                route_str = str(raw_route).strip()
                if route_str.lower() not in ('none', 'nan', 'null', ''):
                    route_id = valid_routes_map.get(route_str.lower())

            total_processed += 1

            if cid in existing_customers:
                customer = existing_customers[cid]
                for key, value in data.items():
                    if key != 'opinion_leader':
                        setattr(customer, key, value)
                customers_to_update.append(customer)
                updated_count += 1

                if route_id is not None:
                    current_assignment = active_assignments.get(cid)
                    if current_assignment:
                        if str(current_assignment.route_id) != str(route_id):
                            if current_assignment.start_date and current_assignment.start_date >= today:
                                current_assignment.route_id = route_id
                                assignments_to_update.append(current_assignment)
                            else:
                                current_assignment.end_date = yesterday
                                assignments_to_update.append(current_assignment)
                                assignments_to_create.append(
                                    self.customer_assignment_model(
                                        customer_id=cid,
                                        route_id=route_id,
                                        start_date=today
                                    )
                                )
                    else:
                        assignments_to_create.append(
                            self.customer_assignment_model(
                                customer_id=cid,
                                route_id=route_id,
                                start_date=today
                            )
                        )
            else:
                customer = self.customer_model(**data)
                customers_to_create.append(customer)
                created_count += 1

                if route_id is not None:
                    assignments_to_create.append(
                        self.customer_assignment_model(
                            customer_id=cid,
                            route_id=route_id,
                            start_date=today
                        )
                    )

        print(
            f"[CUSTOMERS-BULK PLAN] Nuevos: {len(customers_to_create)} | "
            f"A actualizar: {len(customers_to_update)} | "
            f"Asignaciones a actualizar: {len(assignments_to_update)} | "
            f"Nuevas asignaciones: {len(assignments_to_create)}",
            flush=True
        )

        try:
            with transaction.atomic():
                if customers_to_create:
                    print(f"[CUSTOMERS-BULK DB] Creando {len(customers_to_create)} clientes...", flush=True)
                    self.customer_model.objects.bulk_create(customers_to_create, batch_size=500)
                
                if customers_to_update:
                    update_fields = [col for col in valid_columns if col != 'id' and col != 'opinion_leader']
                    if update_fields:
                        print(f"[CUSTOMERS-BULK DB] Actualizando {len(customers_to_update)} clientes con campos {update_fields}...", flush=True)
                        self.customer_model.objects.bulk_update(customers_to_update, update_fields, batch_size=500)
                
                if assignments_to_update:
                    print(f"[CUSTOMERS-BULK DB] Actualizando {len(assignments_to_update)} asignaciones de ruta...", flush=True)
                    self.customer_assignment_model.objects.bulk_update(assignments_to_update, ['route_id', 'end_date'], batch_size=500)
                
                if assignments_to_create:
                    print(f"[CUSTOMERS-BULK DB] Creando {len(assignments_to_create)} asignaciones de ruta...", flush=True)
                    self.customer_assignment_model.objects.bulk_create(assignments_to_create, batch_size=500)
            
            success_msg = f"Importación exitosa. Se crearon {created_count} clientes y se actualizaron {updated_count}."
            print(f"[CUSTOMERS-BULK SUCCESS] {success_msg}\n", flush=True)
            return ImportResult(
                success=True,
                message=success_msg,
                total_processed=total_processed,
                created_count=created_count,
                updated_count=updated_count
            )
        except Exception as e:
            print(f"\n[CUSTOMERS-BULK DATABASE EXCEPTION] Error al ejecutar transacción en base de datos: {str(e)}", flush=True)
            traceback.print_exc()
            humanized_msg = BaseETLHelper.humanize_database_error(e)
            print(f"[CUSTOMERS-BULK HUMANIZED MESSAGE] {humanized_msg}\n", flush=True)
            return ImportResult(
                success=False,
                message=humanized_msg,
                total_processed=total_processed,
                errors=[str(e)]
            )

@dataclass
class CustomersStats:
    '''dedicated only to give general stats about customers'''
    customers_service: CustomersService

    @property
    def _base_qs(self) -> QuerySet:
        return self.customers_service.read_customers()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            customers_count=Count('pk', distinct=True),
            assigned_customers_count=Count(
                'pk',
                filter=Q(current_route_id__isnull=False),
                distinct=True
            ),
            unassigned_customers_count=Count(
                'pk',
                filter=Q(current_route_id__isnull=True),
                distinct=True
            ),
            opinion_leaders_count=Count(
                'pk',
                filter=Q(opinion_leader=True),
                distinct=True
            ),
            total_credit_limit=Sum('credit_limit'),
            avg_credit_limit=Avg('credit_limit'),
            avg_credit_days=Avg('credit_days'),
        )

        agg['total_credit_limit'] = agg['total_credit_limit'] or Decimal('0.00')
        agg['avg_credit_limit'] = agg['avg_credit_limit'] or Decimal('0.00')
        agg['avg_credit_days'] = agg['avg_credit_days'] or 0

        return agg

