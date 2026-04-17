from __future__ import annotations

_FLIGHTRADAR_BASE = "https://www.flightradar24.com"
_DATA_CLOUD_BASE = "https://data-cloud.flightradar24.com"
_DATA_LIVE_BASE = "https://data-live.flightradar24.com"
_API_BASE = "https://api.flightradar24.com/common/v1"


class Core:
    user_login_url = f"{_FLIGHTRADAR_BASE}/user/login"
    search_url = f"{_FLIGHTRADAR_BASE}/v1/search/web/find"
    real_time_flight_tracker_data_url = f"{_DATA_CLOUD_BASE}/zones/fcgi/feed.js"
    flight_data_url = f"{_DATA_LIVE_BASE}/clickhandler/"
    api_airport_data_url = f"{_API_BASE}/airport.json"
    most_tracked_url = f"{_FLIGHTRADAR_BASE}/flights/most-tracked"

    headers = {
        "accept-encoding": "gzip",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "origin": _FLIGHTRADAR_BASE,
        "referer": f"{_FLIGHTRADAR_BASE}/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    json_headers = {**headers, "accept": "application/json"}
