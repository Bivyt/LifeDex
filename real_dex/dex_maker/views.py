from django.shortcuts import render
from .dex_functions import analyze_location

def index(request):
    context = {}

    if request.method == "POST":
        location = request.POST.get("location")
        data = analyze_location(location)

        if not data:
            context["error"] = "Location not found"
        else:
            context.update(data)
            context["location"] = location

    return render(request, "index.html", context)
