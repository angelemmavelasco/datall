import os
import sys
import traceback
from django.utils import timezone
from django.core.files import File
from apps.core.models import User, GeneratedReport
from apps.core.services.uploads import UploadsService


def process_bulk_upload_task(report_id: int, model_key: str, user_id: int, temp_file_path: str = None):
    """
    django q background task to process file uploads asynchronously from local shared volume.
    updates the GeneratedReport record with the outcome and diagnostics without uploading raw files to Cloudflare R2.
    """
    print(f"\n{'='*20} [TASK-UPLOAD START] Report ID: {report_id} | Model: {model_key} | User ID: {user_id} {'='*20}", flush=True)
    try:
        report = GeneratedReport.objects.get(id=report_id)
    except GeneratedReport.DoesNotExist:
        print(f"[TASK-UPLOAD ERROR] GeneratedReport #{report_id} no existe.", flush=True)
        return False

    target_temp_path = temp_file_path or (report.filters.get('temp_file_path') if report.filters else None)
    raw_file = None
    file_to_process = None

    try:
        user = User.objects.get(id=user_id)
        service = UploadsService(user=user)

        orig_filename = (report.filters.get('filename') if report.filters else '') or f"upload_{model_key}.xlsx"

        if target_temp_path and os.path.exists(target_temp_path):
            file_size = os.path.getsize(target_temp_path)
            print(f"[TASK-UPLOAD] Archivo local a procesar: {orig_filename} ({target_temp_path}, Tamaño: {file_size} bytes)", flush=True)
            raw_file = open(target_temp_path, 'rb')
            file_to_process = File(raw_file, name=orig_filename)
        elif report.file:
            print(f"[TASK-UPLOAD] Archivo adjunto a procesar: {getattr(report.file, 'name', 'desconocido')}", flush=True)
            report.file.open('rb')
            file_to_process = report.file
        else:
            err_msg = "No se encontró el archivo temporal o adjunto para procesar la importación."
            print(f"[TASK-UPLOAD ERROR] #{report_id}: {err_msg}", flush=True)
            report.status = GeneratedReport.Status.FAILED
            report.error_message = err_msg
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            return False

        try:
            result = service.process_upload(model_key=model_key, file_obj=file_to_process)
        finally:
            if raw_file:
                raw_file.close()
            elif hasattr(report.file, 'close'):
                report.file.close()

            # clean up local temporary file to prevent disk bloat
            if target_temp_path and os.path.exists(target_temp_path):
                try:
                    os.remove(target_temp_path)
                    print(f"[TASK-UPLOAD] Archivo temporal eliminado con éxito: {target_temp_path}", flush=True)
                except Exception as rem_err:
                    print(f"[TASK-UPLOAD WARNING] No se pudo eliminar archivo temporal {target_temp_path}: {rem_err}", flush=True)

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

        if raw_file:
            try:
                raw_file.close()
            except Exception:
                pass
        if target_temp_path and os.path.exists(target_temp_path):
            try:
                os.remove(target_temp_path)
            except Exception:
                pass

        report.status = GeneratedReport.Status.FAILED
        report.error_message = f"Error inesperado durante la ejecución en segundo plano: {str(e)}"
        report.completed_at = timezone.now()
        report.is_seen = False
        report.save()
        return False


def save_generated_report_file_task(report_id: int, temp_file_path: str, filename: str):
    try:
        report = GeneratedReport.objects.get(id=report_id)
        if os.path.exists(temp_file_path):
            file_size = os.path.getsize(temp_file_path)
            with open(temp_file_path, 'rb') as f:
                report.file.save(filename, File(f), save=False)
            report.file_size = file_size
            report.status = GeneratedReport.Status.COMPLETED
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()

            try:
                os.remove(temp_file_path)
            except Exception as rem_err:
                print(f"[SAVE-REPORT WARNING] Could not remove temp file {temp_file_path}: {rem_err}", flush=True)
            return True
        else:
            err_msg = f"Archivo temporal no encontrado: {temp_file_path}"
            report.status = GeneratedReport.Status.FAILED
            report.error_message = err_msg
            report.completed_at = timezone.now()
            report.is_seen = False
            report.save()
            return False
    except Exception as e:
        if report_id:
            try:
                report = GeneratedReport.objects.get(id=report_id)
                report.status = GeneratedReport.Status.FAILED
                report.error_message = str(e)
                report.completed_at = timezone.now()
                report.is_seen = False
                report.save()
            except Exception:
                pass
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        raise e

