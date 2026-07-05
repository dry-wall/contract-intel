from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.documents_list, name="list"),
    path("upload/", views.upload_document, name="upload"),
    path("<int:job_id>/status/", views.job_status_page, name="status"),
    path("<int:job_id>/status.json", views.job_status_json, name="status_json"),
    path("<int:job_id>/results/", views.job_results_page, name="results"),
]
