import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services.mapser import MapserService


@login_required
def mapser_view(request):
    '''
    renders mapser dashboard with customer geo profiles and denue points
    '''
    template = 'mapser/mapser.html'
    req_data = request.GET.dict()

    mapser_service = MapserService(
        user=request.user,
        cleaned_data=req_data,
    )

    kpis = mapser_service.get_stats()
    geo_data = mapser_service.read_geo_profiles()
    denue_points = mapser_service.read_denues()

    context = {
        'kpis': kpis,
        'geo_data_json': json.dumps(geo_data),
        'denue_points_json': json.dumps(denue_points),
        'default_center': list(mapser_service.default_center),
    }

    return render(request, template, context)
