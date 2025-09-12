import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
import statistics

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
import uvicorn

# Add shared modules to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.models import StandardizedLogEntry, ProcessedMetrics, LogStatus, HealthCheck
from shared.kafka_client import KafkaClient
from shared.logger import configure_logging, get_logger
from shared.metrics import ServiceMetrics, RequestTimer, MessageTimer

# Configuration
SERVICE_NAME = "log-processor"
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PORT = int(os.getenv("PORT", "8003"))
CONSUMER_GROUP = "processor-consumer-group"

# Initialize components
logger = configure_logging(SERVICE_NAME, LOG_LEVEL)
metrics = ServiceMetrics(SERVICE_NAME)
kafka_client = KafkaClient(KAFKA_BOOTSTRAP_SERVERS)

# FastAPI app
app = FastAPI(
    title="Log Processing Service",
    description="Microservice for processing standardized logs and generating analytics",
    version="1.0.0"
)

# Kafka topics configuration
KAFKA_TOPICS = {
    "processed-metrics": {
        "partitions": 3,
        "replication_factor": 1,
        "config": {
            "cleanup.policy": "delete",
            "retention.ms": "2592000000"  # 30 days
        }
    },
    "alerts": {
        "partitions": 1,
        "replication_factor": 1,
        "config": {
            "cleanup.policy": "delete",
            "retention.ms": "86400000"  # 1 day
        }
    }
}

class LogProcessorService:
    def __init__(self):
        self.producer = None
        self.consumer = None
        self.is_running = False
        self.is_healthy = False
        
        # In-memory storage for analytics (in production, use a database)
        self.processed_logs: List[ProcessedMetrics] = []
        self.source_stats: Dict[str, Dict] = defaultdict(lambda: {
            'total_count': 0,
            'success_count': 0,
            'failed_count': 0,
            'avg_duration': 0,
            'avg_cpu_time': 0,
            'avg_memory': 0,
            'last_updated': datetime.now()
        })

    async def start(self):
        """Initialize the service"""
        try:
            # Create Kafka topics
            kafka_client.create_topics(KAFKA_TOPICS)
            
            # Create Kafka producer and consumer
            self.producer = kafka_client.create_producer()
            self.consumer = kafka_client.create_consumer(
                group_id=CONSUMER_GROUP,
                topics=["standardized-logs"]
            )
            
            self.is_healthy = True
            logger.info("Log Processor Service started successfully")
            
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
        logger.info("Log Processor Service stopped")

    def calculate_efficiency_score(self, log_entry: StandardizedLogEntry) -> float:
        """Calculate efficiency score based on duration and resource usage"""
        # Simple efficiency calculation: lower duration and resource usage = higher efficiency
        # Normalize to 0-100 scale
        try:
            base_duration = 10.0  # Expected base duration in seconds
            base_memory = 10000000  # Expected base memory in bytes (10MB)
            
            duration_score = max(0, 100 - (log_entry.duration_seconds / base_duration) * 50)
            memory_score = max(0, 100 - (log_entry.memory_used_bytes / base_memory) * 50)
            
            return (duration_score + memory_score) / 2
        except:
            return 50.0  # Default neutral score

    def calculate_resource_utilization(self, log_entry: StandardizedLogEntry) -> float:
        """Calculate resource utilization score"""
        try:
            # Simple calculation based on CPU time vs duration ratio
            if log_entry.duration_seconds > 0:
                cpu_utilization = (log_entry.cpu_time_seconds / log_entry.duration_seconds) * 100
                return min(100, cpu_utilization)
            return 0
        except:
            return 0

    def calculate_throughput(self, log_entry: StandardizedLogEntry) -> float:
        """Calculate throughput in objects per minute"""
        try:
            if log_entry.duration_seconds > 0:
                return 60.0 / log_entry.duration_seconds  # Objects per minute
            return 0
        except:
            return 0

    def detect_anomalies(self, log_entry: StandardizedLogEntry, processed: ProcessedMetrics) -> tuple[bool, str]:
        """Detect anomalies in log entry"""
        anomalies = []
        
        # Check for failures
        if log_entry.status == LogStatus.FAILED:
            anomalies.append("execution_failure")
        
        # Check for long duration (> 1 hour)
        if log_entry.duration_seconds > 3600:
            anomalies.append("long_execution_time")
        
        # Check for high memory usage (> 100MB)
        if log_entry.memory_used_bytes > 100000000:
            anomalies.append("high_memory_usage")
        
        # Check for negative memory usage (data quality issue)
        if log_entry.memory_used_bytes < 0:
            anomalies.append("negative_memory_usage")
        
        # Check for very low efficiency
        if processed.efficiency_score < 20:
            anomalies.append("low_efficiency")
        
        return len(anomalies) > 0, "; ".join(anomalies) if anomalies else None

    def process_log_entry(self, standardized_entry: StandardizedLogEntry) -> ProcessedMetrics:
        """Process a standardized log entry and generate metrics"""
        try:
            # Calculate metrics
            efficiency_score = self.calculate_efficiency_score(standardized_entry)
            resource_utilization = self.calculate_resource_utilization(standardized_entry)
            throughput = self.calculate_throughput(standardized_entry)
            
            # Create processed metrics
            processed = ProcessedMetrics(
                sequence_id=standardized_entry.sequence_id,
                timestamp=standardized_entry.timestamp,
                company=standardized_entry.company,
                source=standardized_entry.source,
                object_type=standardized_entry.object_type,
                status=standardized_entry.status,
                duration_seconds=standardized_entry.duration_seconds,
                cpu_time_seconds=standardized_entry.cpu_time_seconds,
                memory_used_bytes=standardized_entry.memory_used_bytes,
                throughput_objects_per_minute=throughput,
                efficiency_score=efficiency_score,
                resource_utilization=resource_utilization
            )
            
            # Detect anomalies
            is_anomaly, anomaly_reason = self.detect_anomalies(standardized_entry, processed)
            processed.is_anomaly = is_anomaly
            processed.anomaly_reason = anomaly_reason
            
            return processed
            
        except Exception as e:
            logger.error(f"Failed to process log entry: {e}")
            raise

    def update_source_statistics(self, processed: ProcessedMetrics):
        """Update running statistics for data source"""
        source = processed.source
        stats = self.source_stats[source]
        
        # Update counters
        stats['total_count'] += 1
        if processed.status == LogStatus.SUCCESS:
            stats['success_count'] += 1
        else:
            stats['failed_count'] += 1
        
        # Update running averages (simple approach)
        total = stats['total_count']
        stats['avg_duration'] = ((stats['avg_duration'] * (total - 1)) + processed.duration_seconds) / total
        stats['avg_cpu_time'] = ((stats['avg_cpu_time'] * (total - 1)) + processed.cpu_time_seconds) / total
        stats['avg_memory'] = ((stats['avg_memory'] * (total - 1)) + processed.memory_used_bytes) / total
        stats['last_updated'] = datetime.now()

    async def send_alert(self, processed: ProcessedMetrics):
        """Send alert for anomalous log entries"""
        try:
            alert = {
                "timestamp": datetime.now().isoformat(),
                "type": "anomaly_detected",
                "severity": "high" if processed.status == LogStatus.FAILED else "medium",
                "source": processed.source,
                "sequence_id": processed.sequence_id,
                "company": processed.company,
                "anomaly_reason": processed.anomaly_reason,
                "metrics": {
                    "duration_seconds": processed.duration_seconds,
                    "efficiency_score": processed.efficiency_score,
                    "memory_used_bytes": processed.memory_used_bytes
                }
            }
            
            # Send to alerts topic
            kafka_client.produce_message(
                producer=self.producer,
                topic="alerts",
                key=f"alert:{processed.sequence_id}",
                value=alert
            )
            
            logger.warning(
                "Anomaly detected",
                sequence_id=processed.sequence_id,
                source=processed.source,
                reason=processed.anomaly_reason
            )
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    async def process_standardized_log(self, standardized_log_data: dict) -> bool:
        """Process a standardized log message"""
        try:
            # Parse standardized log entry
            standardized_entry = StandardizedLogEntry(**standardized_log_data["data"])
            
            # Process the entry
            processed = self.process_log_entry(standardized_entry)
            
            # Update statistics
            self.update_source_statistics(processed)
            
            # Store processed log (in production, save to database)
            self.processed_logs.append(processed)
            
            # Keep only recent logs in memory (last 10000)
            if len(self.processed_logs) > 10000:
                self.processed_logs = self.processed_logs[-5000:]
            
            # Send alert if anomaly detected
            if processed.is_anomaly:
                await self.send_alert(processed)
            
            # Create Kafka message
            message = {
                "timestamp": datetime.now().isoformat(),
                "data": processed.dict(),
                "source": "log-processor-service",
                "version": "1.0.0",
                "original_source": standardized_log_data.get("source", "unknown")
            }
            
            # Produce to Kafka
            kafka_client.produce_message(
                producer=self.producer,
                topic="processed-metrics",
                key=f"{processed.company}:{processed.sequence_id}:{processed.source}",
                value=message
            )
            
            # Record metrics
            metrics.record_log_entry(processed.source, processed.status.value)
            
            logger.info(
                "Log entry processed",
                sequence=processed.sequence_id,
                source=processed.source,
                efficiency_score=processed.efficiency_score,
                is_anomaly=processed.is_anomaly
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to process standardized log: {e}")
            metrics.record_error("processing_failure")
            return False

    async def consume_messages(self):
        """Consume messages from Kafka"""
        logger.info("Started consuming messages from standardized-logs topic")
        
        while self.is_running:
            try:
                with MessageTimer(metrics, "standardized-logs"):
                    message = kafka_client.consume_messages(self.consumer, timeout=1.0)
                    
                    if message is None:
                        await asyncio.sleep(0.1)
                        continue
                    
                    success = await self.process_standardized_log(message["value"])
                    
                    if success:
                        logger.debug(f"Processed message from {message['topic']}")
                    else:
                        logger.error(f"Failed to process message from {message['topic']}")
                        
            except Exception as e:
                logger.error(f"Error in message consumption loop: {e}")
                metrics.record_error("consumption_error")
                await asyncio.sleep(5)  # Back off on errors

# Initialize service
service = LogProcessorService()

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

@app.get("/analytics/sources")
async def get_source_analytics():
    """Get analytics by data source"""
    with RequestTimer(metrics, "GET", "/analytics/sources"):
        return dict(service.source_stats)

@app.get("/analytics/recent")
async def get_recent_logs(limit: int = Query(100, le=1000)):
    """Get recent processed logs"""
    with RequestTimer(metrics, "GET", "/analytics/recent"):
        recent_logs = service.processed_logs[-limit:] if service.processed_logs else []
        return {
            "total_logs": len(service.processed_logs),
            "requested_limit": limit,
            "returned_count": len(recent_logs),
            "logs": [log.dict() for log in recent_logs]
        }

@app.get("/analytics/anomalies")
async def get_anomalies(limit: int = Query(50, le=500)):
    """Get recent anomalies"""
    with RequestTimer(metrics, "GET", "/analytics/anomalies"):
        anomalies = [log for log in service.processed_logs if log.is_anomaly][-limit:]
        return {
            "total_anomalies": sum(1 for log in service.processed_logs if log.is_anomaly),
            "recent_anomalies": [anomaly.dict() for anomaly in anomalies]
        }

@app.get("/analytics/summary")
async def get_analytics_summary():
    """Get overall analytics summary"""
    with RequestTimer(metrics, "GET", "/analytics/summary"):
        total_logs = len(service.processed_logs)
        if total_logs == 0:
            return {"message": "No processed logs available"}
        
        success_count = sum(1 for log in service.processed_logs if log.status == LogStatus.SUCCESS)
        failed_count = total_logs - success_count
        anomaly_count = sum(1 for log in service.processed_logs if log.is_anomaly)
        
        avg_efficiency = statistics.mean([log.efficiency_score for log in service.processed_logs])
        avg_duration = statistics.mean([log.duration_seconds for log in service.processed_logs])
        
        return {
            "total_logs_processed": total_logs,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": (success_count / total_logs) * 100,
            "anomaly_count": anomaly_count,
            "anomaly_rate": (anomaly_count / total_logs) * 100,
            "average_efficiency_score": round(avg_efficiency, 2),
            "average_duration_seconds": round(avg_duration, 2),
            "total_sources": len(service.source_stats),
            "last_updated": datetime.now().isoformat()
        }

@app.get("/status")
async def get_status():
    """Get service status"""
    with RequestTimer(metrics, "GET", "/status"):
        return {
            "service": SERVICE_NAME,
            "is_running": service.is_running,
            "is_healthy": service.is_healthy,
            "consumer_group": CONSUMER_GROUP,
            "subscribed_topics": ["standardized-logs"],
            "produced_topics": ["processed-metrics", "alerts"],
            "processed_logs_count": len(service.processed_logs),
            "tracked_sources": len(service.source_stats)
        }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level=LOG_LEVEL.lower()
    )