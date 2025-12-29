from django.shortcuts import render
from .dex_functions import analyze_location

def index(request):
    if request.method == "POST":
        location = request.POST.get("location")
        analysis = analyze_location(location)

        if not analysis:
            return render(request, "index.html", {
                "error": "Location not found"
            })

        return render(request, "results.html", {
            "location": location,
            "species_count": analysis["species_count"],
            "results": analysis["results"]
        })

    return render(request, "index.html")