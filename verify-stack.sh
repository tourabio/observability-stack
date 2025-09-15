#!/bin/bash

echo "🔍 Vérification de la Stack d'Observabilité"
echo "============================================="

# Function to check if a service is responding
check_service() {
    local name=$1
    local url=$2
    local timeout=${3:-10}

    echo -n "Vérification $name ($url)... "
    if curl -f -s --max-time $timeout "$url" > /dev/null 2>&1; then
        echo "✅ OK"
        return 0
    else
        echo "❌ FAIL"
        return 1
    fi
}

# Function to check Docker container status
check_container() {
    local container=$1
    echo -n "Vérification container $container... "
    if docker-compose ps | grep -q "$container.*Up"; then
        echo "✅ Running"
        return 0
    else
        echo "❌ Not running"
        return 1
    fi
}

echo
echo "1️⃣ Vérification des containers Docker"
echo "------------------------------------"

containers=("zookeeper" "kafka" "producer" "consumer" "prometheus" "loki" "grafana" "kafka-ui" "promtail")
for container in "${containers[@]}"; do
    check_container "$container"
done

echo
echo "2️⃣ Vérification des services réseau"
echo "-----------------------------------"

# Wait a moment for services to be ready
echo "Attente de 10 secondes pour l'initialisation des services..."
sleep 10

# Check core services
check_service "Kafka UI" "http://localhost:8080"
check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Loki" "http://localhost:3100/ready"
check_service "Grafana" "http://localhost:3000/api/health"

# Check consumer metrics endpoint
check_service "Consumer Metrics" "http://localhost:8000/metrics"

echo
echo "3️⃣ Vérification des topics Kafka"
echo "--------------------------------"

# Check if topic exists
echo -n "Vérification topic 'ingestion-logs'... "
if docker-compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "ingestion-logs"; then
    echo "✅ Existe"
else
    echo "❌ N'existe pas - sera créé automatiquement"
fi

echo
echo "4️⃣ Test du Producer"
echo "-------------------"

echo "Exécution du producer pour traiter logs.json..."
if docker-compose run --rm producer python producer.py; then
    echo "✅ Producer exécuté avec succès"
else
    echo "❌ Erreur lors de l'exécution du producer"
fi

echo
echo "5️⃣ Vérification des métriques Prometheus"
echo "----------------------------------------"

# Wait for metrics to be collected
sleep 5

echo -n "Vérification des métriques ingestion_runs_total... "
if curl -s "http://localhost:9090/api/v1/query?query=ingestion_runs_total" | grep -q '"status":"success"'; then
    echo "✅ Métriques disponibles"
else
    echo "❌ Métriques non disponibles"
fi

echo
echo "6️⃣ Vérification des logs dans Loki"
echo "----------------------------------"

echo -n "Vérification des logs d'ingestion dans Loki... "
if curl -s "http://localhost:3100/loki/api/v1/query_range?query={job=\"ingestion-logs\"}&start=$(date -d '1 hour ago' -Iseconds)&end=$(date -Iseconds)" | grep -q '"status":"success"'; then
    echo "✅ Logs disponibles"
else
    echo "❌ Logs non disponibles"
fi

echo
echo "7️⃣ Vérification des datasources Grafana"
echo "---------------------------------------"

echo -n "Vérification datasource Prometheus... "
if curl -s -u admin:admin123 "http://localhost:3000/api/datasources" | grep -q '"type":"prometheus"'; then
    echo "✅ Configuré"
else
    echo "❌ Non configuré"
fi

echo -n "Vérification datasource Loki... "
if curl -s -u admin:admin123 "http://localhost:3000/api/datasources" | grep -q '"type":"loki"'; then
    echo "✅ Configuré"
else
    echo "❌ Non configuré"
fi

echo
echo "8️⃣ Résumé des accès"
echo "-------------------"
echo "🌐 Grafana Dashboard: http://localhost:3000 (admin/admin123)"
echo "📊 Prometheus: http://localhost:9090"
echo "📋 Kafka UI: http://localhost:8080"
echo "📝 Loki: http://localhost:3100"

echo
echo "✅ Vérification terminée!"
echo
echo "💡 Conseils:"
echo "- Si des services ne répondent pas, attendez quelques minutes supplémentaires"
echo "- Vérifiez les logs avec: docker-compose logs <service-name>"
echo "- Redémarrez un service avec: docker-compose restart <service-name>"