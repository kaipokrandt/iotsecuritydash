from pydantic import BaseModel
from typing import Dict

class EventIn(BaseModel):
    device_id: str
    metrics: Dict[str, float]