import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
import uvicorn

# Add shared modules to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.models import RawLogEntry, StandardizedLogEntry, LogStatus, HealthCheck
from shared.kafka_client import KafkaClient
from shared.logger import configure_logging, get_logger
from shared.metrics import ServiceMetrics, RequestTimer, MessageTimer

# Configuration
SERVICE_NAME = "log-standardization"
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PORT = int(os.getenv("PORT", "8002"))
CONSUMER_GROUP = "standardization-consumer-group"

# Initialize components
logger = configure_logging(SERVICE_NAME, LOG_LEVEL)
metrics = ServiceMetrics(SERVICE_NAME)
kafka_client = KafkaClient(KAFKA_BOOTSTRAP_SERVERS)

# FastAPI app
app = FastAPI(
    title="Log Standardization Service",
    description="Microservice for standardizing raw log entries",
    version="1.0.0"
)

# Kafka topics configuration
KAFKA_TOPICS = {
    "standardized-logs": {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "cleanup.policy": "delete",
            "retention.ms": "604800000"  # 7 days
        }
    }
}

class LogStandardizationService:
    def __init__(self):
        self.producer = None
        self.consumer = None
        self.is_running = False
        self.is_healthy = False

    async def start(self):
        """Initialize the service"""
        try:
            # Create Kafka topics
            kafka_client.create_topics(KAFKA_TOPICS)
            
            # Create Kafka producer and consumer
            self.producer = kafka_client.create_producer()
            self.consumer = kafka_client.create_consumer(
                group_id=CONSUMER_GROUP,
                topics=["raw-logs"]
            )
            
            self.is_healthy = True
            logger.info("Log Standardization Service started successfully")
            
            # Start consuming messages
            self.is_running = True
            asyncio.create_task(self.consume_messages())
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            self.is_healthy = False

    async def stop(self):
        """Cleanup service resources"""
        self.is_running = False
        if self.producer:
            self.producer.flush()
        if self.consumer:
            self.consumer.close()
        logger.info("Log Standardization Service stopped")

    def parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime object"""
        try:
            # Handle the specific format: "05-09-2025 16:45:26.191702"
            return datetime.strptime(timestamp_str, "%d-%m-%Y %H:%M:%S.%f")
        except ValueError:
            try:
                # Fallback formats
                return datetime.strptime(timestamp_str, "%d-%m-%Y %H:%M:%S")
            except ValueError:
                logger.warning(f"Could not parse timestamp: {timestamp_str}")
                return datetime.now()

    def normalize_cpu_time(self, cpu_time: str) -> float:
        """Normalize CPU time to float"""
        try:
            if isinstance(cpu_time, (int, float)):
                return float(cpu_time)
            return float(cpu_time)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse CPU time: {cpu_time}")
            return 0.0

    def normalize_memory_usage(self, memory_usage: str) -> int:
        """Normalize memory usage to int"""
        try:
            if isinstance(memory_usage, (int, float)):
                return int(memory_usage)
            return int(memory_usage)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse memory usage: {memory_usage}")
            return 0

    def standardize_log_entry(self, raw_entry: RawLogEntry) -> StandardizedLogEntry:
        """Convert raw log entry to standardized format"""
        try:
            # Parse timestamps
            start_time = self.parse_timestamp(raw_entry.Debut)
            end_time = self.parse_timestamp(raw_entry.Fin)
            
            # Create sequence timestamp from date/hour/minute
            sequence_time = datetime.strptime(
                f"{raw_entry.Date_Sequence} {raw_entry.Heure_Sequence}:{raw_entry.Minute_Sequence}:00",
                "%Y-%m-%d %H:%M:%S"
            )
            
            # Extract error message if failed
            error_message = None
            if raw_entry.Etat == LogStatus.FAILED:
                error_message = raw_entry.Description if raw_entry.Description != "Tout roule, pas de stress!" else "Unknown error"

            # Create standardized entry
            standardized = StandardizedLogEntry(
                sequence_id=raw_entry.No_Sequence,
                timestamp=sequence_time,
                company=raw_entry.Entreprise,
                zone=raw_entry.Zone,
                source=raw_entry.Source,
                object_id=raw_entry.Objet_Id,
                object_type=raw_entry.Objet,
                transformation=raw_entry.Transformation,
                status=raw_entry.Etat,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=raw_entry.Duree_secondes,
                cpu_time_seconds=self.normalize_cpu_time(raw_entry.cpu_time_sec),
                memory_used_bytes=self.normalize_memory_usage(raw_entry.memory_used_bytes),
                description=raw_entry.Description,
                error_message=error_message
            )
            
            return standardized
            
        except Exception as e:
            logger.error(f"Failed to standardize log entry: {e}", raw_entry=raw_entry.dict())
            raise

    async def process_raw_log(self, raw_log_data: dict) -> bool:
        """Process a raw log message"""
        try:
            # Parse raw log entry
            raw_entry = RawLogEntry(**raw_log_data["data"])
            
            # Standardize the entry
            standardized = self.standardize_log_entry(raw_entry)
            
            # Create Kafka message
            message = {
                "timestamp": datetime.now().isoformat(),
                "data": standardized.dict(),
                "source": "log-standardization-service",
                "version": "1.0.0",
                "original_source": raw_log_data.get("source", "unknown")
            }
            
            # Produce to Kafka
            kafka_client.produce_message(
                producer=self.producer,
                topic="standardized-logs",
                key=f"{standardized.company}:{standardized.sequence_id}:{standardized.object_id}",
                value=message
            )
            
            # Record metrics
            metrics.record_log_entry(standardized.source, standardized.status.value)
            
            logger.info(
                "Log entry standardized",
                sequence=standardized.sequence_id,
                source=standardized.source,
                object_id=standardized.object_id,
                status=standardized.status
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to process raw log: {e}")
            metrics.record_error("standardization_failure")
            return False

    async def consume_messages(self):
        """Consume messages from Kafka"""
        logger.info("Started consuming messages from raw-logs topic")
        
        while self.is_running:
            try:
                with MessageTimer(metrics, "raw-logs"):
                    message = kafka_client.consume_messages(self.consumer, timeout=1.0)
                    
                    if message is None:
                        await asyncio.sleep(0.1)
                        continue
                    
                    success = await self.process_raw_log(message["value"])
                    
                    if success:
                        logger.debug(f"Processed message from {message['topic']}")
                    else:
                        logger.error(f"Failed to process message from {message['topic']}")
                        
            except Exception as e:
                logger.error(f"Error in message consumption loop: {e}")
                metrics.record_error("consumption_error")
                await asyncio.sleep(5)  # Back off on errors

# Initialize service
service = LogStandardizationService()

@app.on_event("startup")
async def startup():
    await service.start()

@app.on_event("shutdown")
async def shutdown():
    await service.stop()

@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint"""
    with RequestTimer(metrics, "GET", "/health"):
        return HealthCheck(
            service=SERVICE_NAME,
            status="healthy" if service.is_healthy else "unhealthy",
            timestamp=datetime.now(),
            version="1.0.0",
            dependencies={
                "kafka_producer": "connected" if service.producer else "disconnected",
                "kafka_consumer": "connected" if service.consumer else "disconnected"
            }
        )

@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint"""
    return metrics.get_metrics()

@app.post("/standardize/single")
async def standardize_single_log(raw_entry: RawLogEntry):
    """Standardize a single log entry (for testing)"""
    with RequestTimer(metrics, "POST", "/standardize/single") as timer:
        try:
            standardized = service.standardize_log_entry(raw_entry)
            return {
                "status": "success",
                "data": standardized.dict(),
                "message": "Log entry standardized successfully"
            }
        except Exception as e:
            timer.status = "error"
            logger.error(f"Failed to standardize log entry: {e}")
            raise HTTPException(status_code=500, detail=f"Standardization failed: {str(e)}")

@app.get("/status")
async def get_status():
    """Get service status"""
    with RequestTimer(metrics, "GET", "/status"):
        return {
            "service": SERVICE_NAME,
            "is_running": service.is_running,
            "is_healthy": service.is_healthy,
            "consumer_group": CONSUMER_GROUP,
            "subscribed_topics": ["raw-logs"],
            "produced_topics": ["standardized-logs"]
        }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level=LOG_LEVEL.lower()
    )