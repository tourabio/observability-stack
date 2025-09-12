# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an observability stack project focused on building a production-ready microservice for processing and monitoring data ingestion logs. The project is part of a technical challenge with the objective of creating a comprehensive solution with Docker containerization, Kafka integration, and observability features.

## Key Project Requirements

- Build a production-ready microservice for log processing and monitoring
- Implement Docker containerization with docker-compose for easy deployment  
- Create Kafka producers to simulate ingestion, standardization, and application microservices
- Develop observability and monitoring capabilities
- Include proper documentation, tests, and CI/CD considerations

## Data Structure

The `logs.json` file contains sample log entries with this schema:
- `No_Sequence`: Sequence identifier (format: YYYY-MM-DD-HH-MM)
- `Date_Sequence`, `Heure_Sequence`, `Minute_Sequence`: Time components
- `Entreprise`: Company identifier (e.g., "akonovia")  
- `Zone`: Processing zone (e.g., "1-Raw")
- `Source`: Data source system (PowerBI, Zoho, Efficy, SharePoint, EasyProjects)
- `Objet_Id`: Object identifier
- `Objet`: Object type being processed
- `Transformation`: API transformation method used
- `Etat`: Status (SUCCESS/FAILED)
- `Debut`, `Fin`: Start and end timestamps
- `Duree secondes`: Duration in seconds
- `Description`: Status description ("Tout roule, pas de stress!" for success, error message for failures)
- `cpu_time (sec)`, `memory_used (bytes)`: Performance metrics

## Architecture Considerations

When developing this observability stack:

1. **Microservice Design**: The solution should handle log ingestion, processing, and monitoring as separate concerns
2. **Event-Driven Architecture**: Use Kafka for decoupling components and handling high-throughput log processing
3. **Containerization**: All components should be Docker-containerized for consistent deployment
4. **Monitoring**: Implement comprehensive monitoring and alerting for system health and performance
5. **Data Pipeline**: Design for handling various data sources (APIs from multiple systems) with different processing requirements

## Development Approach

Since this is a greenfield project starting from basic requirements and sample data:

1. First analyze the log structure and identify key metrics to monitor
2. Design the microservice architecture with proper separation of concerns
3. Implement Docker and docker-compose configuration
4. Create Kafka integration for event streaming
5. Build monitoring and observability features
6. Add comprehensive testing and documentation

## Language and Framework Selection

**Primary Language: Python**

All microservices should be implemented in Python. Consider these Python-specific tools and frameworks:
- **FastAPI** or **Flask** for REST API services
- **Kafka-python** or **confluent-kafka-python** for Kafka integration
- **Pydantic** for data validation and serialization
- **SQLAlchemy** for database operations if needed
- **Pytest** for testing
- **Poetry** or **pip-tools** for dependency management
- **Prometheus client library** for metrics collection
- **Structlog** or standard logging for structured logging

Additional considerations:
- Performance requirements for log processing
- Ecosystem compatibility with observability tools (Grafana, Prometheus, etc.)
- Docker and Kubernetes deployment considerations
- Python best practices for microservice development

The sample data suggests this handles enterprise data integration scenarios, so reliability and observability are critical design considerations.