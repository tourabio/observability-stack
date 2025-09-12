from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import time
from typing import Dict, Any

class ServiceMetrics:
    """Prometheus metrics for microservices"""
    
    def __init__(self, service_name: str, registry: CollectorRegistry = None):
        self.service_name = service_name
        self.registry = registry or CollectorRegistry()
        
        # Define metrics
        self.requests_total = Counter(
            'requests_total',
            'Total number of requests processed',
            ['service', 'method', 'endpoint', 'status'],
            registry=self.registry
        )
        
        self.request_duration = Histogram(
            'request_duration_seconds',
            'Request duration in seconds',
            ['service', 'method', 'endpoint'],
            registry=self.registry
        )
        
        self.messages_processed = Counter(
            'messages_processed_total',
            'Total number of messages processed',
            ['service', 'topic', 'status'],
            registry=self.registry
        )
        
        self.message_processing_duration = Histogram(
            'message_processing_duration_seconds',
            'Message processing duration in seconds',
            ['service', 'topic'],
            registry=self.registry
        )
        
        self.active_connections = Gauge(
            'active_connections',
            'Number of active connections',
            ['service', 'connection_type'],
            registry=self.registry
        )
        
        self.log_entries_by_source = Counter(
            'log_entries_by_source_total',
            'Log entries processed by source',
            ['service', 'source', 'status'],
            registry=self.registry
        )
        
        self.processing_errors = Counter(
            'processing_errors_total',
            'Total processing errors',
            ['service', 'error_type'],
            registry=self.registry
        )

    def record_request(self, method: str, endpoint: str, status: str, duration: float = None):
        """Record HTTP request metrics"""
        self.requests_total.labels(
            service=self.service_name,
            method=method,
            endpoint=endpoint,
            status=status
        ).inc()
        
        if duration:
            self.request_duration.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint
            ).observe(duration)

    def record_message_processed(self, topic: str, status: str, duration: float = None):
        """Record message processing metrics"""
        self.messages_processed.labels(
            service=self.service_name,
            topic=topic,
            status=status
        ).inc()
        
        if duration:
            self.message_processing_duration.labels(
                service=self.service_name,
                topic=topic
            ).observe(duration)

    def record_log_entry(self, source: str, status: str):
        """Record log entry processing"""
        self.log_entries_by_source.labels(
            service=self.service_name,
            source=source,
            status=status
        ).inc()

    def record_error(self, error_type: str):
        """Record processing error"""
        self.processing_errors.labels(
            service=self.service_name,
            error_type=error_type
        ).inc()

    def set_active_connections(self, connection_type: str, count: int):
        """Set active connections count"""
        self.active_connections.labels(
            service=self.service_name,
            connection_type=connection_type
        ).set(count)

    def get_metrics(self) -> str:
        """Get metrics in Prometheus format"""
        return generate_latest(self.registry).decode('utf-8')

class RequestTimer:
    """Context manager for timing requests"""
    
    def __init__(self, metrics: ServiceMetrics, method: str, endpoint: str):
        self.metrics = metrics
        self.method = method
        self.endpoint = endpoint
        self.start_time = None
        self.status = "success"

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if exc_type:
            self.status = "error"
        
        self.metrics.record_request(
            method=self.method,
            endpoint=self.endpoint,
            status=self.status,
            duration=duration
        )

class MessageTimer:
    """Context manager for timing message processing"""
    
    def __init__(self, metrics: ServiceMetrics, topic: str):
        self.metrics = metrics
        self.topic = topic
        self.start_time = None
        self.status = "success"

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if exc_type:
            self.status = "error"
        
        self.metrics.record_message_processed(
            topic=self.topic,
            status=self.status,
            duration=duration
        )