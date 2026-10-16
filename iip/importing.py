import json

from iip.models import Institution


def parse_profiles(payload):
    if len(payload) > 10_000_000:
        raise ValueError("Profile import exceeds 10 MB.")
    data = json.loads(payload.decode("utf-8-sig"))
    rows = data.get("institutions") if isinstance(data, dict) and "institutions" in data else data
    rows = rows if isinstance(rows, list) else [rows]
    if not 1 <= len(rows) <= 100:
        raise ValueError("Import between 1 and 100 institution profiles.")
    institutions = [Institution.model_validate(row) for row in rows]
    if len({i.id for i in institutions}) != len(institutions):
        raise ValueError("The import contains duplicate institution IDs.")
    return institutions
