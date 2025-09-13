import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn

# Add shared modules to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.models import RawLogEntry, HealthCheck
from shared.kafka_client import KafkaClient
from shared.logger import configure_logging, get_logger
from shared.metrics import ServiceMetrics, RequestTimer

# Configuration
SERVICE_NAME = "log-ingestion"
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PORT = int(os.getenv("PORT", "8001"))

# Initialize components
logger = configure_logging(SERVICE_NAME, LOG_LEVEL)
metrics = ServiceMetrics(SERVICE_NAME)
kafka_client = KafkaClient(KAFKA_BOOTSTRAP_SERVERS)

# FastAPI app
app = FastAPI(
    title="Log Ingestion Service",
    description="Microservice for ingesting raw log entries and publishing to Kafka",
    version="1.0.0"
)

# Kafka topics configuration
KAFKA_TOPICS = {
    "raw-logs": {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "cleanup.policy": "delete",
            "retention.ms": "604800000"  # 7 days
        }
    }
}

class LogIngestionService:
    def __init__(self):
        self.producer = None
        self.is_healthy = False

    async def start(self):
        """Initialize the service"""
        try:
            # Create Kafka topics
            logger.info("Creating Kafka topics...")
            kafka_client.create_topics(KAFKA_TOPICS)
            logger.info("Kafka topics created successfully")
            
            # Create Kafka producer with retries
            logger.info("Creating Kafka producer...")
            max_retries = 5
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    self.producer = kafka_client.create_producer()
                    
                    if self.producer is None:
                        raise Exception("Kafka producer is None after creation")
                    
                    # Test the producer by getting metadata
                    metadata = self.producer.list_topics(timeout=5)
                    logger.info("Kafka producer created and connected successfully")
                    break
                    
                except Exception as e:
                    logger.warning(f"Producer creation attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error("All producer creation attempts failed")
                        raise
            self.is_healthy = True
            logger.info("Log Ingestion Service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            self.is_healthy = False
            self.producer = None

    async def stop(self):
        """Cleanup service resources"""
        if self.producer:
            self.producer.flush()
        logger.info("Log Ingestion Service stopped")

    async def ingest_log_entry(self, log_entry: RawLogEntry) -> bool:
        """Ingest a single log entry"""
        try:
            if self.producer is None:
                logger.error("Cannot ingest log entry: Kafka producer not initialized")
                return False
            # Create Kafka message
            message = {
                "timestamp": datetime.now().isoformat(),
                "data": log_entry.dict(by_alias=True),
                "source": "log-ingestion-service",
                "version": "1.0.0"
            }
            
            # Use chunked messaging to handle any size
            kafka_client.produce_chunked_message(
                producer=self.producer,
                topic="raw-logs",
                key=f"{log_entry.Entreprise}:{log_entry.No_Sequence}:{log_entry.Objet_Id}",
                data=message
            )
            
            # Record metrics
            metrics.record_log_entry(log_entry.Source, log_entry.Etat.value)
            
            logger.info(
                "Log entry ingested",
                sequence=log_entry.No_Sequence,
                source=log_entry.Source,
                object_id=log_entry.Objet_Id,
                status=log_entry.Etat
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to ingest log entry: {e}", log_entry=log_entry.dict())
            metrics.record_error("ingestion_failure")
            return False

    async def ingest_log_file(self, file_path: str) -> dict:
        """Ingest logs from a JSON file using chunked processing"""
        results = {"total": 0, "successful": 0, "failed": 0}
        
        try:
            if self.producer is None:
                logger.error("Cannot ingest log file: Kafka producer not initialized")
                raise HTTPException(status_code=500, detail="Kafka producer not available")
            # Read all log entries first
            log_entries = []
            with open(file_path, 'r', encoding='utf-8') as file:
                # Read each line as a separate JSON object
                for line_num, line in enumerate(file, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        log_data = json.loads(line)
                        log_entry = RawLogEntry(**log_data)
                        log_entries.append(log_entry)
                        results["total"] += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to parse line {line_num}: {e}")
                        results["failed"] += 1
            
            # Process logs individually to avoid chunking complexity
            for entry in log_entries:
                try:
                    success = await self.ingest_log_entry(entry)
                    if success:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                        
                except Exception as e:
                    logger.error(f"Failed to process log entry {entry.No_Sequence}: {e}")
                    results["failed"] += 1
                        
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Log file not found")
        except Exception as e:
            logger.error(f"Failed to process log file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process log file: {e}")
        
        return results

# Initialize service
service = LogIngestionService()

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
                "kafka": "connected" if service.producer else "disconnected"
            }
        )

@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint"""
    return metrics.get_metrics()

@app.post("/ingest/single")
async def ingest_single_log(log_entry: RawLogEntry):
    """Ingest a single log entry"""
    with RequestTimer(metrics, "POST", "/ingest/single") as timer:
        success = await service.ingest_log_entry(log_entry)
        if not success:
            timer.status = "error"
            raise HTTPException(status_code=500, detail="Failed to ingest log entry")
        
        return {"status": "success", "message": "Log entry ingested successfully"}

@app.post("/ingest/file")
async def ingest_log_file(background_tasks: BackgroundTasks, file_path: str = "logs.json"):
    """Ingest logs from a file"""
    with RequestTimer(metrics, "POST", "/ingest/file"):
        # Use absolute path relative to project root
        project_root = Path(__file__).parent.parent.parent
        full_path = project_root / file_path
        
        results = await service.ingest_log_file(str(full_path))
        
        return {
            "status": "completed",
            "results": results,
            "message": f"Processed {results['total']} log entries"
        }

@app.get("/ingest/trigger")
async def trigger_ingestion():
    """Trigger ingestion of the default logs.json file"""
    with RequestTimer(metrics, "GET", "/ingest/trigger"):
        project_root = Path(__file__).parent.parent.parent
        log_file_path = project_root / "logs.json"
        
        if not log_file_path.exists():
            raise HTTPException(status_code=404, detail="logs.json file not found")
        
        results = await service.ingest_log_file(str(log_file_path))
        
        return {
            "status": "completed",
            "results": results,
            "message": f"Successfully ingested {results['successful']} out of {results['total']} log entries"
        }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level=LOG_LEVEL.lower()
    )