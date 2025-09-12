# Observability Stack

A production-ready microservices-based observability stack for processing and monitoring API execution logs. This system ingests raw logs, standardizes them, processes them for analytics, and provides comprehensive monitoring and visualization capabilities.

## 🎯 **Project Overview**

This project implements a complete data processing pipeline that takes raw API execution logs (like those from Zoho, PowerBI, Efficy, SharePoint, EasyProjects) and transforms them into actionable insights. The system demonstrates modern microservices architecture, event-driven processing, and comprehensive observability practices.

### **Key Capabilities**
- **Real-time log processing** with sub-second latency
- **Automatic anomaly detection** for failed operations and performance issues
- **Comprehensive analytics** including efficiency scores and resource utilization
- **Production-grade monitoring** with metrics, dashboards, and alerting
- **Scalable architecture** supporting horizontal scaling and high throughput

## Architecture

The stack consists of 3 Python microservices:

1. **Log Ingestion Service** (Port 8001)
   - Ingests raw log entries from files or API endpoints
   - Validates and publishes to Kafka `raw-logs` topic
   - Provides REST API for single log ingestion and batch file processing

2. **Log Standardization Service** (Port 8002) 
   - Consumes raw logs from Kafka
   - Normalizes and standardizes log format
   - Publishes to `standardized-logs` topic
   - Handles timestamp parsing, data type normalization, error extraction

3. **Log Processing Service** (Port 8003)
   - Consumes standardized logs from Kafka
   - Generates analytics and metrics (efficiency scores, throughput, resource utilization)
   - Detects anomalies and sends alerts
   - Publishes processed metrics to `processed-metrics` topic
   - Provides analytics REST APIs

## 🛠️ **Technology Stack**

### **Core Microservices (Python)**
- **FastAPI**: Modern, fast web framework for building APIs
- **Pydantic**: Data validation and serialization using Python type hints
- **Structlog**: Structured logging for better observability
- **Confluent Kafka Python**: High-performance Kafka client
- **Prometheus Client**: Metrics instrumentation and export
- **Uvicorn**: ASGI web server for FastAPI applications

### **Infrastructure Components**
- **Apache Kafka + Zookeeper**: Distributed event streaming platform
  - Handles high-throughput message processing
  - Provides durability, fault tolerance, and horizontal scaling
  - Decouples microservices for better resilience

- **Prometheus**: Systems monitoring and alerting toolkit
  - Time-series database for metrics storage
  - Pull-based metrics collection from services
  - PromQL query language for complex metric analysis

- **Grafana**: Analytics and interactive visualization web application
  - Pre-configured dashboards for real-time monitoring
  - Advanced alerting capabilities
  - Multiple data source support

- **Kafka UI**: Web-based management interface for Kafka
  - Topic management and monitoring
  - Consumer group tracking
  - Message browsing and debugging

### **Container Orchestration**
- **Docker**: Application containerization
- **Docker Compose**: Multi-container application orchestration
- **Health Checks**: Built-in container health monitoring
- **Volume Persistence**: Data persistence across container restarts

## 🚀 **Quick Start Guide**

### **Prerequisites**
- **Docker** (version 20.10+) and **Docker Compose** (version 2.0+)
- **Minimum 4GB RAM** available for containers
- **Ports available**: 3000, 8001-8003, 8080, 9090, 9092
- **Optional**: `curl` and `jq` for testing API endpoints

### **Step-by-Step Setup**

1. **Clone and Navigate**
   ```bash
   cd observability-stack
   ```

2. **Start the Complete Stack**
   ```bash
   # Option 1: Using Docker Compose
   docker-compose up -d
   
   # Option 2: Using the Makefile
   make up
   ```

3. **Wait for Services to Initialize** (approximately 60 seconds)
   ```bash
   # Check container status
   docker-compose ps
   
   # Or use the health check command
   make health
   ```

4. **Trigger Log Processing**
   ```bash
   # Process the included logs.json file
   curl -X GET "http://localhost:8001/ingest/trigger"
   
   # Or use the Makefile command
   make ingest
   ```

5. **Access the Dashboards**
   - **Grafana**: http://localhost:3000 (admin/admin123)
   - **Kafka UI**: http://localhost:8080
   - **Prometheus**: http://localhost:9090

### **Verification Steps**

```bash
# Check if all services are healthy
make health

# View real-time logs
make logs

# Get analytics summary
make analytics

# Check for detected anomalies
make anomalies
```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Log Ingestion | http://localhost:8001 | Ingest logs via API |
| Log Standardization | http://localhost:8002 | Standardization service status |
| Log Processing | http://localhost:8003 | Analytics and metrics |
| Grafana Dashboard | http://localhost:3000 | Visualization (admin/admin123) |
| Prometheus | http://localhost:9090 | Metrics storage |
| Kafka UI | http://localhost:8080 | Kafka management |

## API Endpoints

### Log Ingestion Service (8001)
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /ingest/single` - Ingest single log entry
- `POST /ingest/file` - Ingest from file
- `GET /ingest/trigger` - Process default logs.json

### Log Standardization Service (8002)
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /standardize/single` - Test standardization
- `GET /status` - Service status

### Log Processing Service (8003)
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /analytics/sources` - Source analytics
- `GET /analytics/recent` - Recent processed logs
- `GET /analytics/anomalies` - Detected anomalies
- `GET /analytics/summary` - Overall summary
- `GET /status` - Service status

## 🔄 **System Architecture & Data Flow**

### **High-Level Architecture**
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   logs.json     │───▶│  Log Ingestion   │───▶│     Kafka       │
│   (Raw Data)    │    │    Service       │    │  (raw-logs)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Prometheus     │    │ Standardization │
                       │   (Metrics)      │    │    Service      │
                       └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │     Grafana      │    │     Kafka       │
                       │   (Dashboards)   │    │(standardized-   │
                       └──────────────────┘    │    logs)        │
                                               └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  Processing     │
                                               │    Service      │
                                               └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │     Kafka       │
                                               │ (processed-     │
                                               │   metrics)      │
                                               └─────────────────┘
```

### **Detailed Data Processing Pipeline**

1. **Data Ingestion Phase**
   - Raw logs.json file contains API execution records
   - Log Ingestion Service validates and publishes to Kafka `raw-logs` topic
   - Each log entry gets a unique key based on company, sequence, and object ID

2. **Data Standardization Phase**
   - Standardization Service consumes from `raw-logs` topic
   - Normalizes timestamps, data types, and extracts error information
   - Publishes clean data to `standardized-logs` topic

3. **Analytics & Processing Phase**
   - Processing Service consumes standardized logs
   - Calculates efficiency scores, throughput, resource utilization
   - Detects anomalies (failures, long durations, high memory usage)
   - Publishes analytics to `processed-metrics` topic
   - Sends alerts to `alerts` topic for anomalies

4. **Monitoring & Observability**
   - All services expose Prometheus metrics
   - Grafana pulls metrics from Prometheus every 15 seconds
   - Real-time dashboards show system health and log analytics

## Sample Log Entry

The system processes logs with this structure:
```json
{
  "No_Sequence": "2025-09-05-16-45",
  "Date_Sequence": "2025-09-05",
  "Heure_Sequence": "16",
  "Minute_Sequence": "45",
  "Entreprise": "akonovia",
  "Zone": "1-Raw",
  "Source": "zohoprojects",
  "Objet_Id": 1995,
  "Objet": "projects", 
  "Transformation": "Zoho_API_get_data",
  "Etat": "SUCCESS",
  "Debut": "05-09-2025 16:45:26.191702",
  "Fin": "05-09-2025 16:45:27.089917",
  "Duree secondes": 0.898215,
  "Description": "Tout roule, pas de stress!",
  "cpu_time (sec)": "0.09",
  "memory_used (bytes)": 5517312
}
```

## Monitoring

### Grafana Dashboards
- **Request Rate by Service**: HTTP request metrics
- **Log Entries by Source**: Distribution of log sources
- **Message Processing Duration**: Kafka processing latencies
- **Processing Errors**: Error rates by service
- **Success Rate**: Overall system success rate
- **Active Kafka Connections**: Connection health

### Prometheus Metrics
Each service exposes:
- `requests_total` - HTTP requests by endpoint and status
- `request_duration_seconds` - Request processing time
- `messages_processed_total` - Kafka messages by topic and status
- `message_processing_duration_seconds` - Message processing time
- `log_entries_by_source_total` - Log entries by source system
- `processing_errors_total` - Processing errors by type
- `active_connections` - Active connection counts

## Kafka Topics

- `raw-logs` (3 partitions): Raw log entries from ingestion service
- `standardized-logs` (3 partitions): Normalized log entries
- `processed-metrics` (3 partitions): Analytics and metrics
- `alerts` (1 partition): Anomaly alerts

## 🔧 **How the Setup Works**

### **Container Orchestration**
The `docker-compose.yml` file defines 7 services that work together:

1. **Zookeeper** - Kafka's coordination service
   - Manages Kafka cluster metadata
   - Handles leader election for Kafka partitions
   - Stores consumer group offsets

2. **Kafka** - Message streaming platform
   - Automatically creates topics when services start
   - Configured with 3 partitions per topic for parallel processing
   - Data retention set to 7 days with 1GB size limit per topic

3. **Three Python Microservices**
   - Each runs in its own container with health checks
   - Connected via shared Docker network
   - Auto-restart on failure

4. **Prometheus** - Metrics collection
   - Scrapes metrics from all services every 15 seconds
   - Stores time-series data for 15 days
   - Provides query interface for Grafana

5. **Grafana** - Visualization platform
   - Auto-provisions Prometheus as data source
   - Loads pre-built dashboard on startup
   - Admin credentials: admin/admin123

6. **Kafka UI** - Management interface
   - Provides web interface for Kafka operations
   - Shows topics, partitions, consumer groups
   - Useful for debugging message flow

### **Startup Sequence**
1. Zookeeper starts first (required by Kafka)
2. Kafka starts and waits for Zookeeper
3. Python services wait for Kafka health check
4. Prometheus starts after all services are ready
5. Grafana starts last and connects to Prometheus

### **Data Processing Flow**
```
Raw Log Entry → Validation → Kafka Topic → Consumer → Processing → Analytics → Metrics → Dashboard
```

### **Automatic Features**
- **Topic Creation**: Kafka automatically creates topics when services publish
- **Consumer Groups**: Each service has its own consumer group for load balancing
- **Health Monitoring**: All containers have built-in health checks
- **Data Persistence**: Volumes ensure data survives container restarts
- **Network Isolation**: Services communicate via dedicated Docker network

### **Monitoring & Alerting**
- **Service Metrics**: Request rates, response times, error counts
- **Business Metrics**: Log processing rates, success/failure ratios
- **Infrastructure Metrics**: Memory usage, CPU utilization, disk space
- **Custom Metrics**: Efficiency scores, anomaly detection rates

## 📊 **Understanding the Analytics**

### **Calculated Metrics**
- **Efficiency Score** (0-100): Based on execution time vs. resource usage
- **Throughput**: Objects processed per minute
- **Resource Utilization**: CPU time vs. total execution time ratio
- **Success Rate**: Percentage of successful vs. failed operations

### **Anomaly Detection Rules**
- **Execution Failures**: Status = "FAILED"
- **Long Execution**: Duration > 1 hour
- **High Memory Usage**: Memory > 100MB
- **Data Quality Issues**: Negative memory values
- **Low Efficiency**: Efficiency score < 20%

### **Dashboard Panels**
- **Request Rate**: Real-time API call volume
- **Source Distribution**: Pie chart of log sources (Zoho, PowerBI, etc.)
- **Processing Duration**: Response time percentiles
- **Error Tracking**: Failed operations by service
- **Success Gauge**: Overall system health indicator

## 🧪 **Testing the System**

### **Manual Testing Commands**
```bash
# Test single log ingestion
make test-ingestion

# View analytics
curl http://localhost:8003/analytics/summary | jq

# Check for anomalies
curl http://localhost:8003/analytics/anomalies | jq

# View recent processed logs
curl "http://localhost:8003/analytics/recent?limit=10" | jq
```

### **Monitoring System Health**
```bash
# Check all service health
make health

# View container status
docker-compose ps

# Monitor logs in real-time
make logs

# Check Kafka topics
make kafka-topics
```

## Production Considerations

### Scaling
- Each microservice can be horizontally scaled
- Kafka partitions allow parallel processing
- Consumer groups enable load balancing

### Persistence
- Kafka data persisted with 7-day retention
- Prometheus data retained for 15 days  
- Grafana dashboards and configuration persisted

### Security
- Services run as non-root users
- No secrets in environment variables (use secrets management in production)
- Network isolation with Docker networks

### Monitoring
- Comprehensive health checks on all services
- Prometheus metrics for observability
- Grafana alerting (configure SMTP for notifications)
- Log aggregation via structured JSON logging

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run individual services
cd services/log-ingestion && python main.py
cd services/log-standardization && python main.py
cd services/log-processor && python main.py
```

### Testing
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests (when implemented)
pytest tests/
```

## Troubleshooting

### Common Issues
1. **Services not starting**: Check Docker logs with `docker-compose logs <service>`
2. **Kafka connection errors**: Ensure Kafka is healthy before services start
3. **No data in Grafana**: Check Prometheus targets are UP
4. **High memory usage**: Adjust container limits in docker-compose.yml

### Useful Commands
```bash
# View logs for all services
docker-compose logs -f

# Restart a specific service
docker-compose restart log-ingestion

# Scale a service
docker-compose up -d --scale log-processor=3

# Stop all services
docker-compose down

# Stop and remove volumes (data loss!)
docker-compose down -v
```

## 🎯 **Use Cases & Benefits**

### **Business Use Cases**
- **API Performance Monitoring**: Track execution times across different data sources
- **Resource Optimization**: Identify inefficient operations consuming excessive CPU/memory
- **SLA Compliance**: Monitor success rates and response times for service agreements
- **Capacity Planning**: Analyze throughput patterns to predict scaling needs
- **Incident Response**: Automatic anomaly detection and alerting for failures

### **Technical Benefits**
- **Real-time Insights**: Sub-second processing from log ingestion to dashboard
- **Scalability**: Horizontal scaling support via Kafka partitioning
- **Reliability**: Built-in health checks and automatic service recovery
- **Observability**: Comprehensive metrics and structured logging
- **Maintainability**: Clean microservices architecture with clear boundaries

### **Operational Advantages**
- **Zero Downtime Deployments**: Rolling updates supported via container orchestration
- **Data Persistence**: No data loss during system restarts
- **Easy Debugging**: Kafka UI and structured logs for troubleshooting
- **Cost Optimization**: Identify resource-hungry operations for optimization
- **Compliance**: Audit trail of all operations and system changes

## 🚀 **Getting Started Checklist**

- [ ] Install Docker and Docker Compose
- [ ] Clone the repository
- [ ] Run `docker-compose up -d`
- [ ] Wait for services to start (60 seconds)
- [ ] Trigger log ingestion: `make ingest`
- [ ] Open Grafana: http://localhost:3000
- [ ] Explore analytics: `make analytics`
- [ ] Check for anomalies: `make anomalies`
- [ ] Review Kafka topics: http://localhost:8080

## 📚 **Additional Resources**

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Prometheus Monitoring](https://prometheus.io/docs/)
- [Grafana Dashboard Guide](https://grafana.com/docs/)
- [Docker Compose Reference](https://docs.docker.com/compose/)

## 🤝 **Contributing**

This project demonstrates best practices for:
- Microservices architecture
- Event-driven processing
- Observability and monitoring
- Container orchestration
- API design and documentation

Feel free to extend the system with additional features like:
- Alert notifications (Slack, email)
- Data export capabilities
- Advanced analytics models
- Machine learning-based anomaly detection

## License

This project is provided as-is for educational and development purposes.