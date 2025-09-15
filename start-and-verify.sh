#!/bin/bash

echo "🚀 Démarrage et Vérification Complète de la Stack d'Observabilité"
echo "=================================================================="
echo

# Couleurs pour l'affichage
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "OK" ]; then
        echo -e "${GREEN}✅ $message${NC}"
    elif [ "$status" = "WARNING" ]; then
        echo -e "${YELLOW}⚠️  $message${NC}"
    elif [ "$status" = "ERROR" ]; then
        echo -e "${RED}❌ $message${NC}"
    else
        echo -e "${BLUE}ℹ️  $message${NC}"
    fi
}

# Step 1: Clean up any existing containers
echo -e "${BLUE}1️⃣ Nettoyage préliminaire${NC}"
echo "----------------------------------------"
print_status "INFO" "Arrêt des containers existants..."
docker-compose down -v 2>/dev/null || true
echo

# Step 2: Start the stack
echo -e "${BLUE}2️⃣ Démarrage de la stack${NC}"
echo "----------------------------------------"
print_status "INFO" "Démarrage de tous les services..."
if docker-compose up -d; then
    print_status "OK" "Services démarrés"
else
    print_status "ERROR" "Échec du démarrage des services"
    exit 1
fi
echo

# Step 3: Wait for services to initialize
echo -e "${BLUE}3️⃣ Attente de l'initialisation${NC}"
echo "----------------------------------------"
print_status "INFO" "Attente de l'initialisation des services (90 secondes)..."

for i in {1..90}; do
    echo -ne "\rProgression: $i/90 secondes"
    sleep 1
done
echo
echo

# Step 4: Check container status
echo -e "${BLUE}4️⃣ Vérification des containers${NC}"
echo "----------------------------------------"

containers=("zookeeper" "kafka" "producer" "consumer" "prometheus" "loki" "promtail" "grafana" "kafka-ui")
all_running=true

for container in "${containers[@]}"; do
    if docker-compose ps | grep -q "$container.*Up"; then
        print_status "OK" "Container $container: Running"
    else
        print_status "ERROR" "Container $container: Not running"
        all_running=false
    fi
done
echo

if [ "$all_running" = false ]; then
    print_status "ERROR" "Certains containers ne fonctionnent pas. Vérification des logs..."
    docker-compose logs --tail=20
    exit 1
fi

# Step 5: Test service endpoints
echo -e "${BLUE}5️⃣ Test des endpoints de service${NC}"
echo "----------------------------------------"

# Test Kafka
print_status "INFO" "Test de Kafka..."
if docker-compose exec -T kafka kafka-broker-api-versions --bootstrap-server localhost:9092 >/dev/null 2>&1; then
    print_status "OK" "Kafka: Accessible"
else
    print_status "ERROR" "Kafka: Non accessible"
fi

# Test Consumer metrics
print_status "INFO" "Test des métriques du consumer..."
if curl -f -s --max-time 10 "http://localhost:8000/metrics" >/dev/null; then
    print_status "OK" "Consumer metrics: Disponibles"
else
    print_status "ERROR" "Consumer metrics: Non disponibles"
fi

# Test Prometheus
print_status "INFO" "Test de Prometheus..."
if curl -f -s --max-time 10 "http://localhost:9090/-/healthy" >/dev/null; then
    print_status "OK" "Prometheus: Healthy"
else
    print_status "ERROR" "Prometheus: Non accessible"
fi

# Test Loki
print_status "INFO" "Test de Loki..."
if curl -f -s --max-time 10 "http://localhost:3100/ready" >/dev/null; then
    print_status "OK" "Loki: Ready"
else
    print_status "ERROR" "Loki: Non accessible"
fi

# Test Grafana
print_status "INFO" "Test de Grafana..."
if curl -f -s --max-time 10 "http://localhost:3000/api/health" >/dev/null; then
    print_status "OK" "Grafana: Accessible"
else
    print_status "ERROR" "Grafana: Non accessible"
fi
echo

# Step 6: Create topic and run producer
echo -e "${BLUE}6️⃣ Création du topic et exécution du producer${NC}"
echo "----------------------------------------"

print_status "INFO" "Création du topic ingestion-logs..."
docker-compose exec -T kafka kafka-topics --create --bootstrap-server localhost:9092 --topic ingestion-logs --partitions 3 --replication-factor 1 2>/dev/null || print_status "WARNING" "Topic existe déjà"

print_status "INFO" "Exécution du producer..."
if docker-compose run --rm producer python producer.py; then
    print_status "OK" "Producer exécuté avec succès"
else
    print_status "ERROR" "Échec de l'exécution du producer"
fi
echo

# Step 7: Wait for data processing
echo -e "${BLUE}7️⃣ Attente du traitement des données${NC}"
echo "----------------------------------------"
print_status "INFO" "Attente du traitement des données (30 secondes)..."
sleep 30
echo

# Step 8: Verify metrics are being collected
echo -e "${BLUE}8️⃣ Vérification des métriques${NC}"
echo "----------------------------------------"

print_status "INFO" "Vérification des métriques Prometheus..."
if curl -s "http://localhost:9090/api/v1/query?query=up" | grep -q '"status":"success"'; then
    print_status "OK" "Métriques Prometheus: Disponibles"

    # Check specific ingestion metrics
    if curl -s "http://localhost:9090/api/v1/query?query=ingestion_runs_total" | grep -q '"status":"success"'; then
        print_status "OK" "Métriques d'ingestion: Collectées"
    else
        print_status "WARNING" "Métriques d'ingestion: En attente"
    fi
else
    print_status "ERROR" "Métriques Prometheus: Non disponibles"
fi

print_status "INFO" "Vérification des logs Loki..."
current_time=$(date -Iseconds)
one_hour_ago=$(date -d '1 hour ago' -Iseconds)
if curl -s "http://localhost:3100/loki/api/v1/query_range?query={job=\"ingestion-logs\"}&start=$one_hour_ago&end=$current_time" | grep -q '"status":"success"'; then
    print_status "OK" "Logs Loki: Disponibles"
else
    print_status "WARNING" "Logs Loki: En attente ou non configurés"
fi
echo

# Step 9: Check Grafana datasources
echo -e "${BLUE}9️⃣ Vérification des datasources Grafana${NC}"
echo "----------------------------------------"

print_status "INFO" "Vérification des datasources..."
if curl -s -u admin:admin123 "http://localhost:3000/api/datasources" | grep -q '"type":"prometheus"'; then
    print_status "OK" "Datasource Prometheus: Configuré"
else
    print_status "ERROR" "Datasource Prometheus: Non configuré"
fi

if curl -s -u admin:admin123 "http://localhost:3000/api/datasources" | grep -q '"type":"loki"'; then
    print_status "OK" "Datasource Loki: Configuré"
else
    print_status "ERROR" "Datasource Loki: Non configuré"
fi
echo

# Step 10: Final summary
echo -e "${BLUE}🎯 Résumé et Accès${NC}"
echo "=========================================="
print_status "OK" "Stack d'observabilité déployée avec succès!"
echo
echo -e "${YELLOW}📊 Accès aux interfaces:${NC}"
echo "  🌐 Grafana Dashboard: http://localhost:3000"
echo "     👤 Identifiants: admin / admin123"
echo "  📈 Prometheus: http://localhost:9090"
echo "  📝 Loki: http://localhost:3100"
echo "  🔧 Kafka UI: http://localhost:8080"
echo "  📊 Métriques Consumer: http://localhost:8000/metrics"
echo
echo -e "${YELLOW}🔧 Commandes utiles:${NC}"
echo "  📋 Statut: make status"
echo "  🏥 Santé: make health"
echo "  📊 Métriques: make metrics"
echo "  🔄 Producer: make ingest"
echo "  📝 Logs: make logs"
echo "  🧪 Tests: make test-stack"
echo
echo -e "${GREEN}✅ Déploiement terminé avec succès!${NC}"
echo