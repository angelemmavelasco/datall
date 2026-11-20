from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from apps.core.models import ActivityLog, Module, Reference, Submodule
from apps.core.services.activity_logs import ActivityLogsService

User = get_user_model()


class ActivityLogsServiceTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a',
            password='p',
            first_name='Alice',
            last_name='Uno',
        )
        self.user_b = User.objects.create_user(
            username='user_b',
            password='p',
            first_name='Bob',
            last_name='Dos',
        )
        self.admin_user = User.objects.create_superuser(
            username='admin_u',
            password='p',
            email='admin@test.com',
        )

        self.module = Module.objects.create(name='Core')
        self.submodule = Submodule.objects.create(
            name='Actividad',
            module=self.module,
            url_name='core:activity_logs_view',
        )
        ct_user = ContentType.objects.get_for_model(User)
        ct_mod = ContentType.objects.get_for_model(Module)

        for i in range(5):
            ActivityLog.objects.create(
                user=self.user_a,
                path=f'/core/activity/{i}/',
                view_name='core:activity_logs_view',
                submodule=self.submodule,
                content_type=ct_user,
                object_id=str(self.user_a.pk),
                params={'q': str(i)},
                changes={'step': i},
                ip_address='127.0.0.1',
                user_agent='TestBrowser',
            )
            ActivityLog.objects.create(
                user=self.user_b,
                path=f'/core/other/{i}/',
                view_name='core:activity_logs_view',
                submodule=self.submodule,
                content_type=ct_mod,
                object_id=str(self.module.pk),
                params={'page': str(i)},
                changes={'updated': True},
                ip_address='10.0.0.1',
                user_agent='OtherBrowser',
            )

    def test_regular_user_sees_only_own_logs_and_full_access_sees_all(self):
        logs_a = list(ActivityLogsService(user=self.user_a).get())
        self.assertEqual(len(logs_a), 5)
        self.assertTrue(all(log.user_id == self.user_a.id for log in logs_a))

        logs_admin = list(ActivityLogsService(user=self.admin_user).get())
        self.assertEqual(len(logs_admin), 10)

        grp = Group.objects.create(name='auditor')
        Reference.objects.create(context='acceso_total_actividad', key='rol', value='auditor')
        self.user_b.groups.add(grp)
        logs_auditor = list(ActivityLogsService(user=self.user_b).get())
        self.assertEqual(len(logs_auditor), 10)

    def test_activity_logs_query_avoids_n_plus_one(self):
        service = ActivityLogsService(user=self.admin_user)
        with self.assertNumQueries(3):
            logs = list(service.get())
            rendered_items = [
                (
                    log.user.username,
                    log.user.get_full_name(),
                    str(log.submodule),
                    str(log.content_type),
                    str(log.content_object),
                )
                for log in logs
            ]
        self.assertEqual(len(rendered_items), 10)

        rf = RequestFactory()
        request = rf.get('/core/activity/')
        request.user = self.admin_user
        html = render_to_string(
            'core/activity_logs/activity_logs_list.html',
            {'logs': logs},
            request=request,
        )
        self.assertIn('Alice Uno (@user_a)', html)
        self.assertIn('Bob Dos (@user_b)', html)
        self.assertIn('Core &gt; Actividad', html)
