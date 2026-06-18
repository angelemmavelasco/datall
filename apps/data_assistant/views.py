from django.shortcuts import render
from django.http import HttpResponse
import asyncio
import markdown
from asgiref.sync import sync_to_async
from datetime import datetime, date
import time

#main service
from .prompts.view_rules import PROMPTS_REGISTRY
from .services.data_assistant.data_assistant import DataAssistant

# Create your views here.
async def data_assistant(request):
    start_time = time.perf_counter()
    report_type = request.GET.get('report_type')
    registry_entry = PROMPTS_REGISTRY.get(report_type)
    
    if not registry_entry:
        return HttpResponse("<p>Reporte no soportado por el asistente de datos.</p>")
    
    view_rules = registry_entry['system_context']
    builder_function = registry_entry['data_builder']
    data = {}

    user = await request.auser()


    @sync_to_async
    def fetch_report_data():
        params = request.GET.dict()
        params['user'] = user
        from apps.core.models import DataHistory
        from apps.data_admin.services.data_history.data_history_crud import DataHistoryCrud
        DataHistoryCrud().log_action(
            request=request,
            action=DataHistory.Action.READ,
            description="Generación de insights con el asistente de IA.",
            changes={"report_type": report_type, "params": request.GET.dict()}
        )
        return builder_function(params)

    data = data = await fetch_report_data()
    data['user_name'] = user.first_name.title()

    ia = DataAssistant(system_context=view_rules)
    insights_markdown = await ia.analyze_view_data(data)
    
    raw_html = markdown.markdown(insights_markdown)
    
    styled_html = f"""
    <div class="flex flex-col gap-4 text-sm text-body text-left">
        <style>
            .ai-response h3 {{ font-weight: 600; color: var(--text-title); margin-bottom: 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }}
            .ai-response p {{ margin-bottom: 0.75rem; line-height: 1.5; }}
            .ai-response ul {{ list-style-type: disc; padding-left: 1.25rem; margin-bottom: 1rem; }}
            .ai-response li {{ margin-bottom: 0.25rem; }}
            .ai-response strong {{ color: var(--text-strong); font-weight: 600; }}
        </style>
        <div class="ai-response">
            {raw_html}
        </div>
    </div>
    """
    end_time = time.perf_counter()
    execution_time = end_time - start_time

    print(f"exe time: {execution_time}")
    
    return HttpResponse(styled_html)