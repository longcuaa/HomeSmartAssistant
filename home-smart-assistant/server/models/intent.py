"""Mo hinh du lieu y dinh (intent) — ket qua phan giai mot cau noi.

Day la 'hop dong' chung cho ca 4 tang: Tier 0/1/2/3 deu tra ve mot Intent. Truong 'tier' va
'latency_ms' do resolver dien them de do dac, khong phai do model sinh.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Intent(BaseModel):
    intent: str = "UNKNOWN"          # CONTROL | QUERY | GROUP | SCENE | UNKNOWN
    action: Optional[str] = None     # ON|OFF|SET|GET|TOGGLE|GROUP_ON|GROUP_OFF
    device_type: Optional[str] = None
    device_id: Optional[str] = None
    room: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    response_vi: str = ""
    confidence: float = 0.0
    # Do resolver dien:
    tier: Optional[int] = None       # tang nao phan giai (0-3)
    latency_ms: Optional[float] = None
    # Cho lenh nhom/scene: danh sach (device_id, action, params) da khai trien.
    targets: Optional[list] = None

    def is_actionable(self):
        """Co the thuc thi (co thiet bi/nhom/scene ro rang) hay khong."""
        return self.intent in ("CONTROL", "GROUP", "SCENE") and self.action is not None


def unknown(response_vi, confidence=0.3):
    """Tao nhanh mot Intent UNKNOWN (hoi lai/khong ro)."""
    return Intent(intent="UNKNOWN", response_vi=response_vi, confidence=confidence)
