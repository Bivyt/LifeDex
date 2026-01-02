from django.shortcuts import render
from .dex_functions import analyze_location

def index(request):
    if request.method == "POST":
        location = request.POST.get("location")
        percentile = request.POST.get("pcent")
        if not percentile:
            analysis = analyze_location(location, 100)
        else:
            analysis = analyze_location(location, percentile)
        
        if not analysis:
            return render(request, "index.html", {
                "error": "Location not found"
            })

        return render(request, "results.html", {
            "location": location,
            "species_count": analysis["species_count"],
            "results": analysis["results"],
            "p_count": analysis["p_count"]
        })

    return render(request, "index.html")