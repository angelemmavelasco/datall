from django.utils import timezone
from apps.core.models import User, GeneratedReport
from apps.core.services.uploads import UploadsService


def process_bulk_upload_task(report_id: int, model_key: str, user_id: int):
    """
    django q background task to process file uploads asynchronously.
    updates the GeneratedReport record with the outcome and diagnostics.
    """
    try:
        report = GeneratedReport.objects.get(id=report_id)
    except GeneratedReport.DoesNotExist:
        return False

    try:
        user = User.objects.get(id=user_id)
        service = UploadsService(user=user)

        if not report.file:
            report.status = GeneratedReport.Status.FAILED
            report.error_message = "No se encontró el archivo adjunto para procesar la importación."
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            return False

        report.file.open('rb')
        try:
            result = service.process_upload(model_key=model_key, file_obj=report.file)
        finally:
            report.file.close()

        if result.success:
            report.status = GeneratedReport.Status.COMPLETED
            report.error_message = result.message
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            return True
        else:
            report.status = GeneratedReport.Status.FAILED
            report.error_message = result.message
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            return False

    except Exception as e:
        report.status = GeneratedReport.Status.FAILED
        report.error_message = f"Error inesperado durante la ejecución en segundo plano: {str(e)}"
        report.completed_at = timezone.now()
        report.is_seen = False
        report.save()
        return False
