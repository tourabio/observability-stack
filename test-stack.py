#!/usr/bin/env python3
"""
Script de test pour valider le fonctionnement de la stack d'observabilité
"""

import json
import time
import requests
import sys
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

def test_kafka_connectivity():
    """Test de la connectivité Kafka"""
    print("🔍 Test de connectivité Kafka...")
    try:
        # Test producer connection
        producer = KafkaProducer(
            bootstrap_servers=['localhost:9092'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )

        # Send test message
        test_message = {
            "test": True,
            "timestamp": time.time(),
            "message": "Test connectivity"
        }

        future = producer.send('test-topic', test_message)
        record_metadata = future.get(timeout=10)

        producer.close()
        print("✅ Kafka connectivity: OK")
        return True

    except Exception as e:
        print(f"❌ Kafka connectivity: FAILED - {e}")
        return False

def test_prometheus_metrics():
    """Test des métriques Prometheus"""
    print("🔍 Test des métriques Prometheus...")
    try:
        # Check if Prometheus is accessible
        response = requests.get('http://localhost:9090/-/healthy', timeout=10)
        if response.status_code == 200:
            print("✅ Prometheus health: OK")

            # Check for ingestion metrics
            response = requests.get(
                'http://localhost:9090/api/v1/query',
                params={'query': 'up'},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'success':
                    print("✅ Prometheus queries: OK")
                    return True

        print("❌ Prometheus queries: FAILED")
        return False

    except Exception as e:
        print(f"❌ Prometheus: FAILED - {e}")
        return False

def test_loki_connectivity():
    """Test de la connectivité Loki"""
    print("🔍 Test de connectivité Loki...")
    try:
        # Check Loki ready endpoint
        response = requests.get('http://localhost:3100/ready', timeout=10)
        if response.status_code == 200:
            print("✅ Loki connectivity: OK")
            return True
        else:
            print(f"❌ Loki connectivity: FAILED - Status {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Loki connectivity: FAILED - {e}")
        return False

def test_grafana_connectivity():
    """Test de la connectivité Grafana"""
    print("🔍 Test de connectivité Grafana...")
    try:
        # Check Grafana health
        response = requests.get('http://localhost:3000/api/health', timeout=10)
        if response.status_code == 200:
            print("✅ Grafana connectivity: OK")

            # Check datasources
            response = requests.get(
                'http://localhost:3000/api/datasources',
                auth=('admin', 'admin123'),
                timeout=10
            )

            if response.status_code == 200:
                datasources = response.json()
                prometheus_found = any(ds['type'] == 'prometheus' for ds in datasources)
                loki_found = any(ds['type'] == 'loki' for ds in datasources)

                if prometheus_found and loki_found:
                    print("✅ Grafana datasources: OK")
                    return True
                else:
                    print("❌ Grafana datasources: Missing datasources")
                    return False
            else:
                print("❌ Grafana datasources: Access denied")
                return False

    except Exception as e:
        print(f"❌ Grafana connectivity: FAILED - {e}")
        return False

def test_consumer_metrics():
    """Test des métriques du consumer"""
    print("🔍 Test des métriques du consumer...")
    try:
        response = requests.get('http://localhost:8000/metrics', timeout=10)
        if response.status_code == 200:
            metrics_content = response.text
            if 'ingestion_runs_total' in metrics_content:
                print("✅ Consumer metrics: OK")
                return True
            else:
                print("❌ Consumer metrics: Missing expected metrics")
                return False
        else:
            print(f"❌ Consumer metrics: FAILED - Status {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Consumer metrics: FAILED - {e}")
        return False

def main():
    """Fonction principale de test"""
    print("🧪 Test de la Stack d'Observabilité")
    print("===================================")
    print()

    # Attendre que les services soient prêts
    print("⏳ Attente de 30 secondes pour l'initialisation des services...")
    time.sleep(30)
    print()

    tests = [
        test_kafka_connectivity,
        test_prometheus_metrics,
        test_loki_connectivity,
        test_grafana_connectivity,
        test_consumer_metrics
    ]

    results = []

    for test in tests:
        try:
            result = test()
            results.append(result)
            print()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
            print()

    # Résumé
    print("📋 Résumé des tests")
    print("==================")
    passed = sum(results)
    total = len(results)

    print(f"✅ Tests réussis: {passed}/{total}")

    if passed == total:
        print("🎉 Tous les tests sont passés! La stack est opérationnelle.")
        sys.exit(0)
    else:
        print("⚠️  Certains tests ont échoué. Vérifiez les logs des services.")
        sys.exit(1)

if __name__ == "__main__":
    main()