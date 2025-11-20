# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

from sqlalchemy.orm import Session
from database.models import Service
from database.crud import save_request
from typing import Dict
from icecream import ic

_service_cache: Dict[str, int] = {}

def get_service_id_by_code(db: Session, service_code: str) -> int:
    """
    Retrieve the service ID based on the service code.
    Uses in-memory caching to reduce database queries.
    """
    # Check if the service code is already in the cache
    if service_code in _service_cache:
        return _service_cache[service_code]

    # Strip any leading/trailing whitespace and convert to lowercase for case-insensitive comparison
    service_code = service_code.strip().lower()

    # Query the database
    service_query = db.query(Service).filter(Service.code == service_code).first()

    if service_query:
        ic("service_code:", service_code)
        ic("service_query:", service_query.name)
        service_id = service_query.id
        # Cache the result
        _service_cache[service_code] = service_id

        return service_id
    else:
        raise ValueError(f"Service with code '{service_code}' not found.")


def handle_save_request(db: Session, title: str, user_id: str, service_code: str):
    try:
        service_id = get_service_id_by_code(db, service_code)
        request = save_request(db, title, user_id, service_id)
        ic("request_id:", request.id)
        return request.id
    except Exception as e:
        # Log the error or handle it as needed
        print(f"Error while saving request data: {e}")
