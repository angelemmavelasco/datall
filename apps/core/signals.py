
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from apps.data_admin.services.data_history.data_history_crud import ActivityLogger

@receiver(user_logged_in)
def track_user_login(sender, request, user, **kwargs):
    """
    This function is automatically triggered every time a user logs in successfully.
    """
    ActivityLogger.log_login(user=user, request=request)