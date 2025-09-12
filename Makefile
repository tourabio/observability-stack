.PHONY: help build up down logs clean test ingest health

# Colors for output
GREEN=\033[0;32m
YELLOW=\033[1;33m
RED=\033[0;31m
NC=\033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)Observability Stack - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build all Docker images
	@echo "$(YELLOW)Building Docker images...$(NC)"
	docker-compose build --no-cache

up: ## Start all services
	@echo "$(GREEN)Starting observability stack...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)Services started! Waiting for health checks...$(NC)"
	@sleep 30
	@make health

down: ## Stop all services
	@echo "$(YELLOW)Stopping observability stack...$(NC)"
	docker-compose down

restart: ## Restart all services
	@echo "$(YELLOW)Restarting observability stack...$(NC)"
	docker-compose restart

logs: ## View logs from all services
	docker-compose logs -f

logs-service: ## View logs from specific service (usage: make logs-service SERVICE=log-ingestion)
	docker-compose logs -f $(SERVICE)

clean: ## Stop services and remove all volumes (WARNING: Data loss!)
	@echo "$(RED)This will remove all data! Press Ctrl+C to cancel or wait 5 seconds...$(NC)"
	@sleep 5
	docker-compose down -v
	docker system prune -f

status: ## Check status of all containers
	@echo "$(GREEN)Container Status:$(NC)"
	docker-compose ps

health: ## Check health of all services
	@echo "$(GREEN)Checking service health...$(NC)"
	@echo ""
	@echo "$(YELLOW)Log Ingestion Service:$(NC)"
	@curl -s http://localhost:8001/health | jq . || echo "$(RED)Service not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)Log Standardization Service:$(NC)" 
	@curl -s http://localhost:8002/health | jq . || echo "$(RED)Service not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)Log Processing Service:$(NC)"
	@curl -s http://localhost:8003/health | jq . || echo "$(RED)Service not responding$(NC)"
	@echo ""

ingest: ## Trigger log ingestion
	@echo "$(GREEN)Triggering log ingestion...$(NC)"
	curl -X GET "http://localhost:8001/ingest/trigger"
	@echo ""

analytics: ## Get analytics summary
	@echo "$(GREEN)Analytics Summary:$(NC)"
	curl -s http://localhost:8003/analytics/summary | jq .

anomalies: ## Check for anomalies
	@echo "$(GREEN)Recent Anomalies:$(NC)"
	curl -s http://localhost:8003/analytics/anomalies | jq .

kafka-topics: ## List Kafka topics
	@echo "$(GREEN)Kafka Topics:$(NC)"
	docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

test-ingestion: ## Test ingestion with sample data
	@echo "$(GREEN)Testing single log ingestion...$(NC)"
	curl -X POST "http://localhost:8001/ingest/single" \
		-H "Content-Type: application/json" \
		-d '{
			"No_Sequence": "test-$(shell date +%s)",
			"Date_Sequence": "$(shell date +%Y-%m-%d)",
			"Heure_Sequence": "$(shell date +%H)",
			"Minute_Sequence": "$(shell date +%M)",
			"Entreprise": "test-company",
			"Zone": "1-Raw",
			"Source": "test-source",
			"Objet_Id": 9999,
			"Objet": "test-object",
			"Transformation": "test_transformation",
			"Parametres": "test parameters",
			"Etat": "SUCCESS",
			"Debut": "$(shell date "+%d-%m-%Y %H:%M:%S.000000")",
			"Fin": "$(shell date "+%d-%m-%Y %H:%M:%S.999999")",
			"Duree secondes": 1.0,
			"Description": "Test log entry",
			"cpu_time (sec)": "0.1",
			"memory_used (bytes)": 1000000
		}'
	@echo ""

open-grafana: ## Open Grafana in browser
	@echo "$(GREEN)Opening Grafana dashboard...$(NC)"
	@echo "URL: http://localhost:3000 (admin/admin123)"
	@command -v open >/dev/null 2>&1 && open http://localhost:3000 || \
	command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:3000 || \
	echo "Please open http://localhost:3000 in your browser"

open-kafka-ui: ## Open Kafka UI in browser
	@echo "$(GREEN)Opening Kafka UI...$(NC)"
	@echo "URL: http://localhost:8080"
	@command -v open >/dev/null 2>&1 && open http://localhost:8080 || \
	command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:8080 || \
	echo "Please open http://localhost:8080 in your browser"

urls: ## Show all service URLs
	@echo "$(GREEN)Service URLs:$(NC)"
	@echo "Log Ingestion:     http://localhost:8001"
	@echo "Log Standardization: http://localhost:8002"  
	@echo "Log Processing:    http://localhost:8003"
	@echo "Grafana:          http://localhost:3000 (admin/admin123)"
	@echo "Prometheus:       http://localhost:9090"
	@echo "Kafka UI:         http://localhost:8080"

scale: ## Scale services (usage: make scale SERVICE=log-processor REPLICAS=3)
	docker-compose up -d --scale $(SERVICE)=$(REPLICAS)

dev-setup: ## Setup development environment
	@echo "$(GREEN)Setting up development environment...$(NC)"
	pip install -r requirements.txt
	@echo "$(GREEN)Development environment ready!$(NC)"

lint: ## Run code linting (requires ruff)
	@echo "$(GREEN)Running code linting...$(NC)"
	ruff check shared/ services/
	ruff format --check shared/ services/

format: ## Format code (requires ruff)
	@echo "$(GREEN)Formatting code...$(NC)"
	ruff format shared/ services/

backup: ## Backup volumes
	@echo "$(GREEN)Creating backup of volumes...$(NC)"
	@mkdir -p backups
	docker run --rm -v observability-stack_kafka-data:/data -v $(PWD)/backups:/backup busybox tar czf /backup/kafka-data-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	docker run --rm -v observability-stack_prometheus-data:/data -v $(PWD)/backups:/backup busybox tar czf /backup/prometheus-data-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@echo "$(GREEN)Backup completed in ./backups/$(NC)"