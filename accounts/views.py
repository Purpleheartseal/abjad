from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy

from .forms import PersianAuthenticationForm


class AbjadLoginView(LoginView):
    form_class = PersianAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("entries:dashboard")


@login_required
def logout_view(request):
    logout(request)
    return redirect("accounts:login")
