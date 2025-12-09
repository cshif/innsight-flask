import os
import requests
from typing import List, Dict, Any

from .exceptions import NetworkError, APIError

def fetch_overpass(query: str, timeout: int = 25, max_tries: int = 3) -> List[Dict[str, Any]]:
    if "[timeout:" not in query:
        query = query.replace("[out:json]", f"[out:json][timeout:{timeout}]")

    for attempt in range(1, max_tries + 1):
        try:
            resp = requests.post(os.getenv("OVERPASS_URL"), data={"data": query}, timeout=timeout + 5)
            resp.raise_for_status()
            data = resp.json()
            return data.get("elements", [])
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt == max_tries:
                raise NetworkError(f"Connection timeout or failure: {e}")
        except requests.exceptions.HTTPError as e:
            # HTTP 429 / 504 常見：流量超限或查詢太大
            status = e.response.status_code
            if status in (429, 504) and attempt < max_tries:
                continue
            raise  # 其他錯誤直接拋出
        except ValueError as e:
            raise APIError(f"Invalid response format: {e}")
    raise NetworkError("Unable to fetch data after multiple retries")
