from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("jobs/<int:job_id>/benchmark/", views.job_benchmark, name="job_benchmark"),
]
