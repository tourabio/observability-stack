from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Union
from enum import Enum

class LogStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class RawLogEntry(BaseModel):
    """Raw log entry as it comes from the source"""
    No_Sequence: str = Field(..., description="Sequence identifier")
    Date_Sequence: str = Field(..., description="Date component")
    Heure_Sequence: str = Field(..., description="Hour component") 
    Minute_Sequence: str = Field(..., description="Minute component")
    Entreprise: str = Field(..., description="Company identifier")
    Zone: str = Field(..., description="Processing zone")
    Source: str = Field(..., description="Data source system")
    Objet_Id: int = Field(..., description="Object identifier")
    Objet: str = Field(..., description="Object type")
    Transformation: str = Field(..., description="Transformation method")
    Parametres: str = Field(..., description="Parameters")
    Etat: LogStatus = Field(..., description="Execution status")
    Debut: str = Field(..., description="Start timestamp")
    Fin: str = Field(..., description="End timestamp")
    Duree_secondes: float = Field(..., alias="Duree secondes", description="Duration in seconds")
    Description: str = Field(..., description="Status description")
    cpu_time_sec: Union[str, float] = Field(..., alias="cpu_time (sec)", description="CPU time in seconds")
    memory_used_bytes: Union[str, int] = Field(..., alias="memory_used (bytes)", description="Memory used in bytes")

class StandardizedLogEntry(BaseModel):
    """Standardized log entry after normalization"""
    sequence_id: str
    timestamp: datetime
    company: str
    zone: str
    source: str
    object_id: int
    object_type: str
    transformation: str
    status: LogStatus
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    cpu_time_seconds: float
    memory_used_bytes: int
    description: str
    error_message: Optional[str] = None

class ProcessedMetrics(BaseModel):
    """Processed metrics for analytics"""
    sequence_id: str
    timestamp: datetime
    company: str
    source: str
    object_type: str
    status: LogStatus
    duration_seconds: float
    cpu_time_seconds: float
    memory_used_bytes: int
    throughput_objects_per_minute: float
    efficiency_score: float
    resource_utilization: float
    is_anomaly: bool = False
    anomaly_reason: Optional[str] = None

class KafkaMessage(BaseModel):
    """Generic Kafka message wrapper"""
    topic: str
    key: str
    value: dict
    timestamp: datetime
    partition: Optional[int] = None

class ChunkedMessage(BaseModel):
    """Chunked message for handling large payloads"""
    chunk_id: str
    total_chunks: int
    chunk_number: int
    data: dict
    original_key: str
    timestamp: datetime
    source: str
    version: str = "1.0.0"

class HealthCheck(BaseModel):
    """Health check response"""
    service: str
    status: str
    timestamp: datetime
    version: str
    dependencies: dict