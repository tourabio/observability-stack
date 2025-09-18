# CI/CD Pipeline - Observability Stack

This document outlines the complete CI/CD workflow for the observability stack project, designed to ensure reliable, automated deployments to production while maintaining code quality and system reliability.

## Pipeline Architecture Overview

```
Development → CI/CD Pipeline → Staging → Production
     ↓              ↓             ↓          ↓
  Local Tests   Automated      E2E Tests   Blue-Green
   + Linting     Testing       + Smoke      Deployment
                + Security     Tests       + Monitoring
                + Build
                + Package
```

## Technology Stack

- **Version Control**: Git (GitLab)
- **CI/CD Platform**: GitLab CI/CD
- **Containerization**: Docker + Docker Compose
- **Container Registry**: Docker Hub / AWS ECR / Harbor
- **Orchestration**: Docker Swarm / Kubernetes
- **Infrastructure**: Terraform (for cloud resources)
- **Monitoring**: Prometheus + Grafana + Loki
- **Security Scanning**: Trivy, Hadolint
- **Code Quality**: Ruff (Python), SonarQube

## Environment Strategy

### 1. Development Environment
- **Purpose**: Local development and initial testing
- **Infrastructure**: Docker Compose on developer machines
- **Data**: Sample data from `logs.json`
- **Configuration**: `.env.dev` with development settings

### 2. Staging Environment
- **Purpose**: Pre-production testing and validation
- **Infrastructure**: Cloud-based containers (AWS ECS/EKS, Azure ACI/AKS)
- **Data**: Anonymized production-like data
- **Configuration**: `.env.staging` with staging settings
- **Database**: Separate staging database instances

### 3. Production Environment
- **Purpose**: Live system serving real traffic
- **Infrastructure**: High-availability cloud deployment
- **Data**: Real production data with proper security
- **Configuration**: `.env.prod` with production settings
- **Scaling**: Auto-scaling enabled
- **Monitoring**: Full observability stack

## Branch Strategy

### GitFlow Model
```
main (production)
├── develop (integration)
├── feature/* (new features)
├── release/* (release preparation)
└── hotfix/* (emergency fixes)
```

### Branch Protection Rules
- **main**: Requires MR approval, status checks, no direct pushes
- **develop**: Requires MR approval, automated testing
- All branches: Require linear history, up-to-date before merge

## CI/CD Pipeline Stages

### Stage 1: Code Quality & Security

```yaml
# .gitlab-ci.yml
stages:
  - quality
  - test
  - build
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

code-quality:
  stage: quality
  image: python:3.11-slim
  cache:
    paths:
      - .cache/pip/
  before_script:
    - apt-get update && apt-get install -y git
    - pip install --upgrade pip
  script:
    - pip install ruff pytest bandit safety
    - pip install -r src/producer/requirements.txt
    - pip install -r src/consumer/requirements.txt
    - ruff check src/
    - ruff format --check src/
    - bandit -r src/ -f json -o bandit-report.json
    - safety check --json --output safety-report.json
  artifacts:
    reports:
      junit: bandit-report.json
    paths:
      - bandit-report.json
      - safety-report.json
    expire_in: 1 week
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_COMMIT_BRANCH == "develop"
```

### Stage 2: Testing

```yaml
.test-template: &test-template
  stage: test
  services:
    - docker:20.10.16-dind
  before_script:
    - apt-get update && apt-get install -y docker-compose curl
    - pip install --upgrade pip
    - pip install pytest pytest-cov
    - pip install -r src/producer/requirements.txt
    - pip install -r src/consumer/requirements.txt
  after_script:
    - docker-compose down -v
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
      junit: test-results.xml
    paths:
      - coverage.xml
      - test-results.xml
    expire_in: 1 week

test-python-3.9:
  <<: *test-template
  image: python:3.9-slim
  script:
    - docker-compose -f docker-compose.test.yml up -d kafka zookeeper loki prometheus
    - sleep 30
    - ./scripts/wait-for-services.sh
    - pytest tests/unit/ -v --cov=src --cov-report=xml --junit-xml=test-results.xml
    - pytest tests/integration/ -v
    - python test-stack.py

test-python-3.10:
  <<: *test-template
  image: python:3.10-slim
  script:
    - docker-compose -f docker-compose.test.yml up -d kafka zookeeper loki prometheus
    - sleep 30
    - ./scripts/wait-for-services.sh
    - pytest tests/unit/ -v --cov=src --cov-report=xml --junit-xml=test-results.xml
    - pytest tests/integration/ -v
    - python test-stack.py

test-python-3.11:
  <<: *test-template
  image: python:3.11-slim
  script:
    - docker-compose -f docker-compose.test.yml up -d kafka zookeeper loki prometheus
    - sleep 30
    - ./scripts/wait-for-services.sh
    - pytest tests/unit/ -v --cov=src --cov-report=xml --junit-xml=test-results.xml
    - pytest tests/integration/ -v
    - python test-stack.py
```

### Stage 3: Container Build & Security

```yaml
build-images:
  stage: build
  image: docker:20.10.16
  services:
    - docker:20.10.16-dind
  variables:
    DOCKER_BUILDKIT: 1
  before_script:
    - echo $CI_REGISTRY_PASSWORD | docker login -u $CI_REGISTRY_USER --password-stdin $CI_REGISTRY
  script:
    # Lint Dockerfiles
    - docker run --rm -i hadolint/hadolint < src/producer/Dockerfile
    - docker run --rm -i hadolint/hadolint < src/consumer/Dockerfile

    # Build images
    - docker build -t $CI_REGISTRY_IMAGE/producer:$CI_COMMIT_SHA -f src/producer/Dockerfile .
    - docker build -t $CI_REGISTRY_IMAGE/consumer:$CI_COMMIT_SHA -f src/consumer/Dockerfile .

    # Security scan with Trivy
    - apk add --no-cache curl
    - curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
    - trivy image --format sarif --output producer-trivy-results.sarif $CI_REGISTRY_IMAGE/producer:$CI_COMMIT_SHA
    - trivy image --format sarif --output consumer-trivy-results.sarif $CI_REGISTRY_IMAGE/consumer:$CI_COMMIT_SHA

    # Tag and push images
    - docker tag $CI_REGISTRY_IMAGE/producer:$CI_COMMIT_SHA $CI_REGISTRY_IMAGE/producer:latest
    - docker tag $CI_REGISTRY_IMAGE/consumer:$CI_COMMIT_SHA $CI_REGISTRY_IMAGE/consumer:latest
    - docker push $CI_REGISTRY_IMAGE/producer:$CI_COMMIT_SHA
    - docker push $CI_REGISTRY_IMAGE/consumer:$CI_COMMIT_SHA

    # Push latest tags for main branch
    - |
      if [[ "$CI_COMMIT_BRANCH" == "main" ]]; then
        docker push $CI_REGISTRY_IMAGE/producer:latest
        docker push $CI_REGISTRY_IMAGE/consumer:latest
      fi
  artifacts:
    reports:
      sast:
        - producer-trivy-results.sarif
        - consumer-trivy-results.sarif
    paths:
      - producer-trivy-results.sarif
      - consumer-trivy-results.sarif
    expire_in: 1 week
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_COMMIT_BRANCH == "develop"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

### Stage 4: Deployment

```yaml
deploy-staging:
  stage: deploy
  image: docker:20.10.16
  services:
    - docker:20.10.16-dind
  environment:
    name: staging
    url: https://staging.observability.company.com
  before_script:
    - apk add --no-cache curl envsubst python3 py3-pip
    - pip3 install pytest
    - echo $CI_REGISTRY_PASSWORD | docker login -u $CI_REGISTRY_USER --password-stdin $CI_REGISTRY
  script:
    # Set environment variables
    - export IMAGE_TAG=$CI_COMMIT_SHA
    - export CONTAINER_REGISTRY=$CI_REGISTRY_IMAGE

    # Deploy using docker-compose with staging configuration
    - envsubst < docker-compose.staging.yml > docker-compose.deploy.yml
    - docker-compose -f docker-compose.deploy.yml up -d

    # Wait for services to be ready
    - sleep 60

    # Run smoke tests
    - ./scripts/smoke-tests.sh staging

    # Run E2E tests
    - pytest tests/e2e/ --env=staging
  rules:
    - if: $CI_COMMIT_BRANCH == "develop"
      when: on_success
    - if: $CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "develop"
      when: manual

deploy-production:
  stage: deploy
  image: docker:20.10.16
  services:
    - docker:20.10.16-dind
  environment:
    name: production
    url: https://observability.company.com
  before_script:
    - apk add --no-cache curl bash
    - echo $CI_REGISTRY_PASSWORD | docker login -u $CI_REGISTRY_USER --password-stdin $CI_REGISTRY
  script:
    # Blue-Green Deployment
    - ./scripts/blue-green-deploy.sh $CI_COMMIT_SHA

    # Health check
    - ./scripts/health-check.sh production

    # Run production smoke tests
    - ./scripts/smoke-tests.sh production
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: manual
  needs:
    - job: build-images
      artifacts: false
```

## Infrastructure as Code

### Docker Compose Configurations

**docker-compose.staging.yml**
```yaml
version: '3.8'
services:
  producer:
    image: ${CONTAINER_REGISTRY}/observability-producer:${IMAGE_TAG}
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
      - LOG_LEVEL=INFO
      - ENVIRONMENT=staging

  consumer:
    image: ${CONTAINER_REGISTRY}/observability-consumer:${IMAGE_TAG}
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
      - LOKI_URL=http://loki:3100
      - LOG_LEVEL=INFO
      - ENVIRONMENT=staging

  # Infrastructure services with staging-specific configurations
  kafka:
    environment:
      KAFKA_LOG_RETENTION_HOURS: 72  # Shorter retention for staging

  prometheus:
    command:
      - '--storage.tsdb.retention.time=7d'  # Shorter retention for staging
```

**docker-compose.production.yml**
```yaml
version: '3.8'
services:
  producer:
    image: ${CONTAINER_REGISTRY}/observability-producer:${IMAGE_TAG}
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
      - LOG_LEVEL=WARNING
      - ENVIRONMENT=production
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
      restart_policy:
        condition: on-failure

  consumer:
    image: ${CONTAINER_REGISTRY}/observability-consumer:${IMAGE_TAG}
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
      - LOKI_URL=http://loki:3100
      - LOG_LEVEL=WARNING
      - ENVIRONMENT=production
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
      restart_policy:
        condition: on-failure
```

## Security Considerations

### 1. Secrets Management
```bash
# Use environment-specific secret management
# GitLab CI/CD Variables for secrets
# HashiCorp Vault or AWS Secrets Manager for production

# Required GitLab CI/CD Variables:
- CI_REGISTRY (GitLab Container Registry URL)
- CI_REGISTRY_USER (GitLab Registry username)
- CI_REGISTRY_PASSWORD (GitLab Registry password)
- KAFKA_SSL_CERTIFICATES (Protected, File variable)
- GRAFANA_ADMIN_PASSWORD (Protected, Masked)
- DATABASE_CREDENTIALS (Protected, Masked)
- SLACK_WEBHOOK (Protected, Masked)

# Variable Settings:
# - Set as "Protected" for main/develop branches only
# - Set as "Masked" to hide values in job logs
# - Use "File" type for certificates and config files
```

### 2. Container Security
```dockerfile
# Multi-stage builds for minimal attack surface
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
RUN useradd --create-home --shell /bin/bash app
USER app
WORKDIR /app
COPY --from=builder /root/.local /home/app/.local
COPY . .
EXPOSE 8000
CMD ["python", "consumer.py"]
```

### 3. Network Security
```yaml
# Network isolation and security groups
networks:
  observability-network:
    driver: overlay
    encrypted: true
    attachable: false
```

## Monitoring & Alerting

### 1. Pipeline Monitoring
```yaml
# Add monitoring to CI/CD pipeline
.notify-slack:
  image: alpine:latest
  before_script:
    - apk add --no-cache curl
  script:
    - |
      if [ "$CI_JOB_STATUS" = "success" ]; then
        EMOJI=":white_check_mark:"
        COLOR="good"
      else
        EMOJI=":x:"
        COLOR="danger"
      fi
      curl -X POST -H 'Content-type: application/json' \
        --data "{\"channel\":\"#deployments\",\"text\":\"$EMOJI $CI_PROJECT_NAME - $CI_JOB_NAME: $CI_JOB_STATUS\",\"color\":\"$COLOR\"}" \
        $SLACK_WEBHOOK
  when: always

# Add to deployment jobs:
after_script:
  - !reference [.notify-slack, script]
```

### 2. Application Monitoring
```yaml
# Production monitoring alerts
groups:
- name: observability-stack
  rules:
  - alert: ProducerDown
    expr: up{job="producer"} == 0
    for: 5m
    annotations:
      summary: "Producer service is down"

  - alert: ConsumerLag
    expr: kafka_consumer_lag_sum > 1000
    for: 2m
    annotations:
      summary: "Consumer lag is high"

  - alert: ErrorRateHigh
    expr: rate(ingestion_errors_total[5m]) > 0.1
    for: 1m
    annotations:
      summary: "Error rate is above threshold"
```

### 3. Infrastructure Monitoring
```yaml
# Infrastructure health checks
- alert: DiskSpaceHigh
  expr: disk_used_percent > 85
  for: 5m

- alert: MemoryUsageHigh
  expr: memory_used_percent > 90
  for: 2m

- alert: KafkaTopicLag
  expr: kafka_topic_partition_current_offset - kafka_topic_partition_oldest_offset > 10000
  for: 5m
```

## Rollback Strategy

### 1. Automated Rollback
```bash
#!/bin/bash
# scripts/rollback.sh

PREVIOUS_VERSION=$1
ENVIRONMENT=$2

echo "Rolling back to version: $PREVIOUS_VERSION"

# Update image tags to previous version
export IMAGE_TAG=$PREVIOUS_VERSION

# Deploy previous version
docker-compose -f docker-compose.${ENVIRONMENT}.yml up -d

# Verify health
./scripts/health-check.sh $ENVIRONMENT

if [ $? -eq 0 ]; then
    echo "Rollback successful"
    exit 0
else
    echo "Rollback failed - manual intervention required"
    exit 1
fi
```

### 2. Database Migration Rollback
```python
# Database rollback strategy for schema changes
def rollback_migration(version):
    """Rollback to previous database schema version"""
    # Implement database rollback logic
    pass
```

## Performance Testing

### 1. Load Testing
```yaml
# Add load testing to pipeline
load-test:
  stage: test
  image: grafana/k6:latest
  script:
    - k6 run tests/load/ingestion-load-test.js
  artifacts:
    reports:
      performance: k6-results.json
    paths:
      - k6-results.json
    expire_in: 1 week
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_COMMIT_BRANCH == "develop"
    - when: manual
```

### 2. Performance Benchmarks
```python
# tests/performance/benchmark.py
import pytest
import time
from kafka import KafkaProducer

def test_producer_throughput():
    """Test producer can handle required throughput"""
    producer = KafkaProducer(bootstrap_servers=['kafka:29092'])

    start_time = time.time()
    messages_sent = 0

    for i in range(1000):
        producer.send('test-topic', {'message': f'test_{i}'})
        messages_sent += 1

    end_time = time.time()
    throughput = messages_sent / (end_time - start_time)

    assert throughput >= 100  # messages per second
```

## Maintenance & Operations

### 1. Scheduled Maintenance
```yaml
# .gitlab-ci.yml - Scheduled pipeline
scheduled-maintenance:
  stage: maintenance
  image: alpine:latest
  before_script:
    - apk add --no-cache bash curl python3 py3-pip docker
  script:
    - ./scripts/cleanup-logs.sh
    - ./scripts/update-dependencies.sh
    - ./scripts/security-scan.sh
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  artifacts:
    paths:
      - maintenance-report.txt
    expire_in: 30 days

# Create a pipeline schedule in GitLab:
# Go to CI/CD > Schedules
# Set to run weekly: "0 2 * * 0" (Every Sunday at 2 AM)
```

### 2. Disaster Recovery
```bash
#!/bin/bash
# scripts/disaster-recovery.sh

# Backup current state
./scripts/backup-volumes.sh

# Restore from backup
./scripts/restore-from-backup.sh $BACKUP_VERSION

# Verify system health
./scripts/health-check.sh production
```

## Tools & Scripts

### Required Scripts

1. **scripts/wait-for-services.sh** - Wait for services to be ready
2. **scripts/health-check.sh** - Comprehensive health checks
3. **scripts/smoke-tests.sh** - Basic functionality tests
4. **scripts/blue-green-deploy.sh** - Blue-green deployment
5. **scripts/backup-volumes.sh** - Backup persistent data
6. **scripts/cleanup-logs.sh** - Log cleanup and rotation

### Required Test Suites

1. **tests/unit/** - Unit tests for individual components
2. **tests/integration/** - Integration tests between services
3. **tests/e2e/** - End-to-end tests for complete workflows
4. **tests/load/** - Load and performance tests
5. **tests/security/** - Security and penetration tests

## Configuration Management

### Environment Variables

```bash
# .env.production
ENVIRONMENT=production
LOG_LEVEL=WARNING
KAFKA_BOOTSTRAP_SERVERS=kafka-prod:29092
CONTAINER_REGISTRY=your-registry.com
GRAFANA_ADMIN_PASSWORD=${GRAFANA_PROD_PASSWORD}
PROMETHEUS_RETENTION=30d
LOKI_RETENTION=30d
```

### Feature Flags

```python
# Feature flag management for gradual rollouts
FEATURE_FLAGS = {
    'new_kafka_consumer': os.getenv('FEATURE_NEW_CONSUMER', 'false').lower() == 'true',
    'enhanced_metrics': os.getenv('FEATURE_ENHANCED_METRICS', 'false').lower() == 'true',
}
```

This comprehensive CI/CD workflow ensures reliable, secure, and monitored deployments of the observability stack while maintaining high code quality and system reliability throughout the development lifecycle.