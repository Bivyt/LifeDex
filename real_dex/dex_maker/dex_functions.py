import csv
import json
import os
import time
import asyncio
import aiohttp
import requests
import numpy
from collections import defaultdict
from pathlib import Path

# =================================================================
# CACHE FILES (GBIF + iNaturalist)
# =================================================================

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(exist_ok=True)

GBIF_CACHE_FILE = CACHE_DIR / "gbif_taxonomy_cache.json"
INAT_CACHE_FILE = CACHE_DIR / "inat_species_cache.json"


# Load GBIF taxonomy cache into memory
if os.path.exists(GBIF_CACHE_FILE):
    with open(GBIF_CACHE_FILE, "r", encoding="utf-8") as f:
        LOCAL_GBIF_CACHE = json.load(f)
else:
    LOCAL_GBIF_CACHE = {}

def save_gbif_cache():
    """Persist GBIF taxonomy cache to disk."""
    with open(GBIF_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(LOCAL_GBIF_CACHE, f, indent=2)

BASE_DIR = Path(__file__).resolve().parent
PKMN_CSV_PATH = BASE_DIR / "data" / "pkmndat.csv"

# =================================================================
# iNaturalist species download (auto-pagination + disk cache)
# =================================================================

def get_species_for_place(place_id, use_cache=True):
    """
    Fetch ALL species observed in an iNaturalist place.
    Uses per_page=500 and paginates until no more results.
    Results are cached to disk for faster repeated runs.
    """

    # Return cached results if available
    if use_cache and os.path.exists(INAT_CACHE_FILE):
        with open(INAT_CACHE_FILE, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        if str(place_id) in cached_data:
            print("Loaded iNaturalist species from cache.")
            return set(cached_data[str(place_id)])

    base_url = "https://api.inaturalist.org/v1/observations/species_counts"
    session = requests.Session()
    per_page = 500
    page_number = 1
    species_set = set()

    print("Fetching species from iNaturalist...")
    while True:
        params = {
            "place_id": place_id,
            "per_page": per_page,
            "page": page_number
        }

        response = session.get(base_url, params=params)

        # Handle rate limits
        if response.status_code == 429:
            print("Rate limit hit, pausing…")
            time.sleep(2)
            continue

        response.raise_for_status()

        results = response.json().get("results", [])
        if not results:
            break  # No more pages

        for item in results:
            taxon_name = item.get("taxon", {}).get("name")
            if taxon_name:
                species_set.add(taxon_name.lower())

        print(f"Fetched page {page_number}: {len(results)} species", end="\r")
        page_number += 1
        time.sleep(0.2)

    # Write cache to disk
    if os.path.exists(INAT_CACHE_FILE):
        with open(INAT_CACHE_FILE, "r", encoding="utf-8") as f:
            cache_file = json.load(f)
    else:
        cache_file = {}

    cache_file[str(place_id)] = list(species_set)

    with open(INAT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_file, f, indent=2)

    return species_set



# =================================================================
# POKÉMON CSV LOADER
# =================================================================

def load_pokemon_csv(csv_file):
    """Load Pokémon taxonomy mappings from CSV into a structured list of dicts."""
    pokedex = []

    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            pokedex.append({
                "pokemon": row["pokemon"].strip(),
                "species": row["species"].strip().lower() or None,
                "genus": row["genus"].strip().lower() or None,
                "family": row["family"].strip().lower() or None
            })

    return pokedex



# =================================================================
# ASYNC GBIF LOOKUP
# =================================================================

async def fetch_gbif_taxonomy(session, name):
    """
    Query GBIF for the taxonomy of a given name.
    Uses disk+memory cache to avoid repeated lookups.
    """
    name = name.lower().strip()

    # Use cache first
    if name in LOCAL_GBIF_CACHE:
        return name, LOCAL_GBIF_CACHE[name]

    url = "https://api.gbif.org/v1/species/search"
    params = {"q": name, "limit": 1}

    try:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                LOCAL_GBIF_CACHE[name] = {}
                return name, {}
            data = await resp.json()
    except:
        LOCAL_GBIF_CACHE[name] = {}
        return name, {}

    if not data.get("results"):
        LOCAL_GBIF_CACHE[name] = {}
        return name, {}

    top_result = data["results"][0]
    taxonomy = {
        "species": (top_result.get("species") or "").lower(),
        "genus":   (top_result.get("genus") or "").lower(),
        "family":  (top_result.get("family") or "").lower(),
    }

    LOCAL_GBIF_CACHE[name] = taxonomy
    return name, taxonomy


async def bulk_gbif_lookup_async(names):
    """
    Resolve taxonomy for many names simultaneously using async GBIF API calls.
    Reuses cached entries and only fetches what is missing.
    """
    clean_names = {n.strip().lower() for n in names if n and n.strip()}
    missing_names = [n for n in clean_names if n not in LOCAL_GBIF_CACHE]

    print(f"GBIF lookups needed: {len(missing_names)}")

    resolved = {}

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_gbif_taxonomy(session, n) for n in missing_names]

        for future in asyncio.as_completed(tasks):
            name, taxonomy = await future
            resolved[name] = taxonomy

    # Add entries that were already cached
    for n in clean_names:
        if n in LOCAL_GBIF_CACHE:
            resolved[n] = LOCAL_GBIF_CACHE[n]

    save_gbif_cache()
    return resolved



# =================================================================
# RESOLVE OBSERVED TAXA FROM GBIF
# =================================================================

async def expand_observed_taxa(observed_species):
    """Resolve full GBIF taxonomy for all iNaturalist species."""
    print("Resolving taxonomy for observed species...")

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_gbif_taxonomy(session, s.lower()) for s in observed_species]
        results = await asyncio.gather(*tasks)

    observed_taxonomy = {name: info for name, info in results if info}
    return observed_taxonomy



# =================================================================
# MATCHING / SCORING
# =================================================================

def score_pokemon(pokedex, gbif_taxa, observed_taxa):
    """
    Score Pokémon based on taxonomic matches:
      species = 15 points
      genus   = 7 points
      family  = 1 point
    """
    scores = defaultdict(int)

    for entry in pokedex:
        pokemon_name = entry["pokemon"]

        # Pokémon's canonical species name (preferred over CSV genus/family)
        pokemon_species = entry["species"]

        if pokemon_species:
            pokemon_genus = gbif_taxa.get(pokemon_species, {}).get("genus")
            pokemon_family = gbif_taxa.get(pokemon_species, {}).get("family")
        else:
            pokemon_genus = entry["genus"]
            pokemon_family = entry["family"]

        if pokemon_genus:
            pokemon_genus = pokemon_genus.lower()
        if pokemon_family:
            pokemon_family = pokemon_family.lower()

        # Compare Pokémon taxon to each observed species' taxon
        for observed_name, observed_info in observed_taxa.items():

            # Species-level match
            if pokemon_species and observed_info.get("species") == pokemon_species:
                scores[pokemon_name] += 15

            # Genus-level match
            if pokemon_genus and observed_info.get("genus") == pokemon_genus:
                scores[pokemon_name] += 7

            # Family-level match
            if pokemon_family and observed_info.get("family") == pokemon_family:
                scores[pokemon_name] += 1

    # Calculate encounter rate
    total_score = sum(scores.values())
    encounter_rate = {name: round((score / total_score * 100), 6) if total_score else 0 for name, score in scores.items()}

    # Sort by scores and encounter rates
    results = [(name, scores[name], encounter_rate[name]) for name in scores]
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def get_place_id(location_name, exact=False):
    """
    Retrieve the iNaturalist place_id for a given location name.

    Args:
        location_name (str): Name of the place (e.g., "Texas", "Austin, TX")
        exact (bool): If True, only return exact name matches

    Returns:
        int or None: place_id if found, otherwise None
    """
    url = "https://api.inaturalist.org/v1/places/autocomplete"
    params = {
        "q": location_name,
        "per_page": 5
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    results = response.json().get("results", [])

    if not results:
        return None

    if exact:
        for place in results:
            if place.get("display_name", "").lower() == location_name.lower():
                return place["id"]
        return None

    # Otherwise return the top-ranked result
    return results[0]["id"]


# =================================================================
# MAIN SCRIPT EXECUTION
# =================================================================

# matcher/logic.py

def analyze_location(location, percentile):
    place_id = get_place_id(location)
    if not place_id:
        return None

    observed_species = get_species_for_place(place_id)
    pokedex = load_pokemon_csv(PKMN_CSV_PATH)

    taxon_names = {
        p[k] for p in pokedex for k in ("species", "genus", "family") if p[k]
    }

    gbif_taxa = asyncio.run(
        bulk_gbif_lookup_async(taxon_names)
    )
    observed_taxa = asyncio.run(
        expand_observed_taxa(observed_species)
    )

    results = score_pokemon(pokedex, gbif_taxa, observed_taxa)

    # Filter results to only show Pokémon with a positive score
    scores = [score for _, score, _ in results]
    cut_off = numpy.percentile(scores, 100 - int(percentile))
    results = [(name, score, rate) for name, score, rate in results if score > cut_off]

    return {
        "place_id": place_id,
        "species_count": len(observed_species),
        "results": results,
        "p_count": len(results)
    }
