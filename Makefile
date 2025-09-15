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
	@echo "$(YELLOW)Kafka:$(NC)"
	@docker-compose ps kafka | grep -q "Up" && echo "✅ Running" || echo "❌ Not running"
	@echo ""
	@echo "$(YELLOW)Producer:$(NC)"
	@docker-compose ps producer | grep -q "Up" && echo "✅ Running" || echo "❌ Not running"
	@echo ""
	@echo "$(YELLOW)Consumer:$(NC)"
	@docker-compose ps consumer | grep -q "Up" && echo "✅ Running" || echo "❌ Not running"
	@echo ""
	@echo "$(YELLOW)Consumer Metrics:$(NC)"
	@curl -s http://localhost:8000/metrics > /dev/null && echo "✅ Available" || echo "❌ Not available"
	@echo ""
	@echo "$(YELLOW)Prometheus:$(NC)"
	@curl -s http://localhost:9090/-/healthy > /dev/null && echo "✅ Healthy" || echo "❌ Not healthy"
	@echo ""
	@echo "$(YELLOW)Loki:$(NC)"
	@curl -s http://localhost:3100/ready > /dev/null && echo "✅ Ready" || echo "❌ Not ready"
	@echo ""
	@echo "$(YELLOW)Grafana:$(NC)"
	@curl -s http://localhost:3000/api/health > /dev/null && echo "✅ Healthy" || echo "❌ Not healthy"
	@echo ""

ingest: ## Run producer to ingest logs
	@echo "$(GREEN)Running producer to ingest logs...$(NC)"
	docker-compose --profile tools run --rm producer python producer.py
	@echo ""

metrics: ## Show consumer metrics
	@echo "$(GREEN)Consumer Metrics:$(NC)"
	@curl -s http://localhost:8000/metrics | grep ingestion_ | head -20

verify: ## Verify complete stack functionality
	@echo "$(GREEN)Running complete stack verification...$(NC)"
	@./verify-stack.sh

kafka-topics: ## List Kafka topics
	@echo "$(GREEN)Kafka Topics:$(NC)"
	docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

test-stack: ## Test stack functionality
	@echo "$(GREEN)Running automated stack tests...$(NC)"
	python3 test-stack.py

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
	@echo "Grafana Dashboard: http://localhost:3000 (admin/admin123)"
	@echo "Prometheus:       http://localhost:9090"
	@echo "Loki:             http://localhost:3100"
	@echo "Kafka UI:         http://localhost:8080"
	@echo "Consumer Metrics: http://localhost:8000/metrics"

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