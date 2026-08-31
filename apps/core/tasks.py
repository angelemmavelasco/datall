import sys
import traceback
from django.utils import timezone
from apps.core.models import User, GeneratedReport
from apps.core.services.uploads import UploadsService


def process_bulk_upload_task(report_id: int, model_key: str, user_id: int):
    """
    django q background task to process file uploads asynchronously.
    updates the GeneratedReport record with the outcome and diagnostics.
    """
    print(f"\n{'='*20} [TASK-UPLOAD START] Report ID: {report_id} | Model: {model_key} | User ID: {user_id} {'='*20}", flush=True)
    try:
        report = GeneratedReport.objects.get(id=report_id)
    except GeneratedReport.DoesNotExist:
        print(f"[TASK-UPLOAD ERROR] GeneratedReport #{report_id} no existe.", flush=True)
        return False

    try:
        user = User.objects.get(id=user_id)
        service = UploadsService(user=user)

        if not report.file:
            err_msg = "No se encontró el archivo adjunto para procesar la importación."
            print(f"[TASK-UPLOAD ERROR] #{report_id}: {err_msg}", flush=True)
            report.status = GeneratedReport.Status.FAILED
            report.error_message = err_msg
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            return False

        filename = getattr(report.file, 'name', 'desconocido')
        file_size = getattr(report.file, 'size', 'desconocido')
        print(f"[TASK-UPLOAD] Archivo a procesar: {filename} (Tamaño: {file_size} bytes)", flush=True)

        report.file.open('rb')
        try:
            result = service.process_upload(model_key=model_key, file_obj=report.file)
        finally:
            report.file.close()

        print(f"[TASK-UPLOAD] Resultado de la importación: success={result.success}, mensaje='{result.message}'", flush=True)
        if result.errors:
            print(f"[TASK-UPLOAD ERRORS DETAIL]: {result.errors}", flush=True)

        if result.success:
            report.status = GeneratedReport.Status.COMPLETED
            report.error_message = result.message
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            print(f"{'='*20} [TASK-UPLOAD SUCCESS] Report ID: {report_id} {'='*20}\n", flush=True)
            return True
        else:
            report.status = GeneratedReport.Status.FAILED
            report.error_message = result.message
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            print(f"{'='*20} [TASK-UPLOAD FAILED] Report ID: {report_id} - {result.message} {'='*20}\n", flush=True)
            return False

    except Exception as e:
        print(f"\n[TASK-UPLOAD EXCEPTION] Excepción no controlada en la tarea #{report_id}: {str(e)}", flush=True)
        traceback.print_exc()
        report.status = GeneratedReport.Status.FAILED
        report.error_message = f"Error inesperado durante la ejecución en segundo plano: {str(e)}"
        report.completed_at = timezone.now()
        report.is_seen = False
        report.save()
        return False
