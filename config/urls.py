from django.urls import path
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView
from crm import views, api
urlpatterns=[
path('',RedirectView.as_view(url='/dashboard/',permanent=False)),
path('health/',views.health),
path('login/',views.SecureLoginView.as_view(),name='login'),path('logout/',LogoutView.as_view(),name='logout'),
path('dashboard/',views.dashboard,name='dashboard'),path('pipeline/',views.pipeline),path('search/',views.search),path('reports/',views.reports),path('settings/',views.settings_view),path('privacy/',views.privacy),
path('aftercare/',views.aftercare,{'module':'aftercare'}),path('reactivation/',views.aftercare,{'module':'reactivation'}),
path('api/leads/',api.capture_lead),path('webhooks/meta/',api.meta_webhook),
path('proposals/<uuid:pk>/print/',views.print_proposal),
path('<slug:module>/<uuid:pk>/image/',views.image),path('<slug:module>/<uuid:pk>/images/<uuid:attachment>/',views.image),
path('<slug:module>/filters/save/',views.save_filter),
path('<slug:module>/new/',views.edit),path('<slug:module>/<uuid:pk>/edit/',views.edit),path('<slug:module>/<int:pk>/edit/',views.edit),
path('<slug:module>/<uuid:pk>/delete/',views.delete),
path('<slug:module>/<uuid:pk>/<slug:action>/',views.action),
path('<slug:module>/<uuid:pk>/',views.detail),path('<slug:module>/<int:pk>/',views.detail),path('<slug:module>/',views.listing)]
