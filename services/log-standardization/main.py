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

from shared.models import RawLogEntry, StandardizedLogEntry, LogStatus, HealthCheck, ChunkedMessage
from shared.kafka_client import KafkaClient
from shared.logger import configure_logging, get_logger
from shared.metrics import ServiceMetrics, RequestTimer, MessageTimer

# Configuration
SERVICE_NAME = "log-standardization"
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
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
        self.chunk_buffer = {}  # Buffer for collecting chunks

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
            
            # Set Kafka connection metrics
            metrics.set_active_connections("kafka", 1)
            
            logger.info("Log Standardization Service started successfully")
            
            # Start consuming messages
            self.is_running = True
            asyncio.create_task(self.consume_messages())
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            self.is_healthy = False
            
            # Set Kafka connection metric to 0 if failed
            metrics.set_active_connections("kafka", 0)

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
            # Handle different message structures
            if "data" in raw_log_data and isinstance(raw_log_data["data"], dict):
                # Standard message format
                log_data = raw_log_data["data"]
            else:
                # Direct log data (for reconstructed messages)
                log_data = raw_log_data
            
            # Parse raw log entry
            raw_entry = RawLogEntry(**log_data)
            
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
            
            # Produce to Kafka using chunked messaging
            kafka_client.produce_chunked_message(
                producer=self.producer,
                topic="standardized-logs",
                key=f"{standardized.company}:{standardized.sequence_id}:{standardized.object_id}",
                data=message
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

    def is_chunked_message(self, message_data: dict) -> bool:
        """Check if the message is a chunked message"""
        return 'chunk_id' in message_data and 'total_chunks' in message_data and 'chunk_number' in message_data

    def collect_chunks(self, chunk_data: dict) -> Optional[dict]:
        """Collect chunks and return reconstructed message when complete"""
        try:
            chunk_id = chunk_data['chunk_id']
            chunk_number = chunk_data['chunk_number']
            total_chunks = chunk_data['total_chunks']
            
            # Initialize chunk collection for this chunk_id
            if chunk_id not in self.chunk_buffer:
                self.chunk_buffer[chunk_id] = {
                    'total_chunks': total_chunks,
                    'received_chunks': {},
                    'timestamp': datetime.now()
                }
            
            # Store this chunk
            self.chunk_buffer[chunk_id]['received_chunks'][chunk_number] = chunk_data
            
            # Check if we have all chunks
            received_count = len(self.chunk_buffer[chunk_id]['received_chunks'])
            if received_count == total_chunks:
                # Reconstruct the message
                chunks = list(self.chunk_buffer[chunk_id]['received_chunks'].values())
                reconstructed = kafka_client.reconstruct_chunked_message(chunks)
                
                # Clean up buffer
                del self.chunk_buffer[chunk_id]
                
                logger.info(f"Reconstructed message from {total_chunks} chunks", chunk_id=chunk_id)
                return reconstructed
            else:
                logger.debug(f"Collected chunk {chunk_number}/{total_chunks} for {chunk_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error collecting chunks: {e}")
            return None

    def cleanup_expired_chunks(self, max_age_minutes: int = 5):
        """Clean up chunks that are too old"""
        try:
            current_time = datetime.now()
            expired_chunks = []
            
            for chunk_id, chunk_info in self.chunk_buffer.items():
                age = (current_time - chunk_info['timestamp']).total_seconds() / 60
                if age > max_age_minutes:
                    expired_chunks.append(chunk_id)
            
            for chunk_id in expired_chunks:
                logger.warning(f"Removing expired chunk collection: {chunk_id}")
                del self.chunk_buffer[chunk_id]
                
        except Exception as e:
            logger.error(f"Error cleaning up expired chunks: {e}")

    async def process_batch_logs(self, batch_data: dict) -> bool:
        """Process a batch of logs from chunked message"""
        try:
            # Handle different batch data structures
            logs = None
            if 'logs' in batch_data:
                logs = batch_data['logs']
            elif 'data' in batch_data and 'logs' in batch_data['data']:
                logs = batch_data['data']['logs']
            
            if not logs:
                logger.warning(f"Batch data missing 'logs' field. Available keys: {list(batch_data.keys())}")
                return False
            success_count = 0
            
            for log_data in logs:
                try:
                    raw_entry = RawLogEntry(**log_data)
                    standardized = self.standardize_log_entry(raw_entry)
                    
                    # Create Kafka message
                    message = {
                        "timestamp": datetime.now().isoformat(),
                        "data": standardized.dict(),
                        "source": "log-standardization-service",
                        "version": "1.0.0",
                        "original_source": batch_data.get("source", "unknown"),
                        "batch_info": {
                            "batch_number": batch_data.get("batch_number"),
                            "total_batches": batch_data.get("total_batches")
                        }
                    }
                    
                    # Use chunked messaging for output as well
                    kafka_client.produce_chunked_message(
                        producer=self.producer,
                        topic="standardized-logs",
                        key=f"{standardized.company}:{standardized.sequence_id}:{standardized.object_id}",
                        data=message
                    )
                    
                    # Record metrics
                    metrics.record_log_entry(standardized.source, standardized.status.value)
                    success_count += 1
                    
                    logger.debug(
                        "Log entry standardized",
                        sequence=standardized.sequence_id,
                        source=standardized.source,
                        object_id=standardized.object_id,
                        status=standardized.status
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to process individual log in batch: {e}")
                    metrics.record_error("batch_log_processing_failure")
            
            logger.info(f"Processed batch: {success_count}/{len(logs)} logs successful")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Failed to process batch logs: {e}")
            metrics.record_error("batch_processing_failure")
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
                        # Periodically clean up expired chunks
                        if hasattr(self, '_last_cleanup'):
                            if (datetime.now() - self._last_cleanup).total_seconds() > 300:  # Every 5 minutes
                                self.cleanup_expired_chunks()
                                self._last_cleanup = datetime.now()
                        else:
                            self._last_cleanup = datetime.now()
                        continue
                    
                    message_data = message["value"]
                    success = False
                    
                    # Check if this is a chunked message
                    if self.is_chunked_message(message_data):
                        logger.debug(f"Received chunk {message_data.get('chunk_number')}/{message_data.get('total_chunks')}")
                        
                        # Collect chunks and try to reconstruct
                        reconstructed = self.collect_chunks(message_data)
                        
                        if reconstructed:
                            # Process the reconstructed message
                            if 'logs' in reconstructed:
                                # This is a batch of logs
                                success = await self.process_batch_logs(reconstructed)
                            elif 'data' in reconstructed and isinstance(reconstructed['data'], dict):
                                # This is a single log entry wrapped in message format
                                success = await self.process_raw_log(reconstructed)
                            else:
                                # This might be direct log data
                                success = await self.process_raw_log(reconstructed)
                        else:
                            # Still waiting for more chunks
                            success = True  # Not an error, just incomplete
                            
                    else:
                        # Regular (non-chunked) message
                        logger.debug(f"Processing non-chunked message with keys: {list(message_data.keys())}")
                        if 'logs' in message_data.get('data', {}):
                            # This is a batch of logs
                            success = await self.process_batch_logs(message_data)
                        else:
                            # This is a single log entry
                            success = await self.process_raw_log(message_data)
                    
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