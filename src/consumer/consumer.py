#!/usr/bin/env python3
"""
Consumer/Traitement : consomme les événements depuis le topic Kafka ingestion-logs,
parse le JSON, définit les labels, et pousse vers Loki pour Grafana.
Suivant les spécifications de exercice_grafana_pipeline.md
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import requests
import sys
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import threading

# Configuration from environment variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'ingestion-logs')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'ingestion-consumer-group')
LOKI_URL = os.getenv('LOKI_URL', 'http://localhost:3100')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics (suivant les spécifications du dashboard Grafana)
# Métriques pour "Vue d'ensemble --- Ingestion: Health"
ingestion_runs_total = Counter(
    'ingestion_runs_total',
    'Nombre total d\'exécutions d\'ingestion',
    ['etat', 'source', 'zone', 'entreprise', 'objet']
)

ingestion_duration_seconds = Histogram(
    'ingestion_duration_seconds',
    'Durée des exécutions d\'ingestion en secondes',
    ['source', 'zone', 'entreprise', 'objet'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float('inf')]
)

ingestion_memory_usage_bytes = Histogram(
    'ingestion_memory_usage_bytes',
    'Utilisation mémoire en bytes',
    ['source', 'zone', 'entreprise', 'objet'],
    buckets=[1024*1024, 5*1024*1024, 10*1024*1024, 50*1024*1024, 100*1024*1024,
             150*1024*1024, 200*1024*1024, float('inf')]
)

ingestion_cpu_usage_seconds = Histogram(
    'ingestion_cpu_usage_seconds',
    'Utilisation CPU en secondes',
    ['source', 'zone', 'entreprise', 'objet'],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, float('inf')]
)

# Métriques pour les alertes
ingestion_failures_total = Counter(
    'ingestion_failures_total',
    'Nombre total d\'échecs d\'ingestion',
    ['source', 'zone', 'entreprise', 'objet', 'description']
)

ingestion_last_run_timestamp = Gauge(
    'ingestion_last_run_timestamp',
    'Timestamp de la dernière exécution par source',
    ['source', 'zone', 'entreprise']
)

ingestion_slow_executions_total = Counter(
    'ingestion_slow_executions_total',
    'Nombre total d\'exécutions lentes (p95 > baseline)',
    ['source', 'zone', 'entreprise', 'objet']
)

ingestion_high_memory_usage_total = Counter(
    'ingestion_high_memory_usage_total',
    'Nombre total d\'utilisations mémoire élevées (>150MB)',
    ['source', 'zone', 'entreprise', 'objet']
)

class IngestionLogConsumer:
    """Consumer pour traiter les logs d'ingestion depuis Kafka"""

    def __init__(self):
        self.consumer = None
        self.loki_url = LOKI_URL
        self.running = True
        self.connect_to_kafka()

    def connect_to_kafka(self) -> None:
        """Établit la connexion avec Kafka"""
        try:
            self.consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
                group_id=KAFKA_GROUP_ID,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                key_deserializer=lambda k: k.decode('utf-8') if k else None,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                auto_commit_interval_ms=5000,
                max_poll_records=100,
                api_version=(2, 6, 0)
            )
            logger.info(f"Connecté au topic Kafka: {KAFKA_TOPIC}")
        except Exception as e:
            logger.error(f"Erreur de connexion à Kafka: {e}")
            sys.exit(1)

    def extract_labels_for_loki(self, log_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Extrait et définit les labels pour Loki et Grafana
        Suivant les conventions du dashboard _MConverter
        """
        labels = {
            'job': 'ingestion-logs',
            'etat': log_data.get('etat', 'UNKNOWN'),
            'source': log_data.get('source', {}).get('name', 'unknown'),
            'zone': log_data.get('zone', 'unknown'),
            'entreprise': log_data.get('entreprise', 'unknown'),
            'objet': log_data.get('objet', {}).get('name', 'unknown'),
            'transformation': log_data.get('objet', {}).get('transformation', 'unknown'),
            'level': 'info' if log_data.get('etat') == 'SUCCESS' else 'error'
        }

        # Ajouter des labels spécifiques pour les métriques
        performance = log_data.get('performance', {})
        if performance.get('duree_secondes', 0) > 30:
            labels['slow_execution'] = 'true'

        if performance.get('memory_used_bytes', 0) > 150 * 1024 * 1024:
            labels['high_memory'] = 'true'

        if performance.get('cpu_time_sec', 0) > 60:
            labels['high_cpu'] = 'true'

        return labels

    def update_prometheus_metrics(self, log_data: Dict[str, Any]) -> None:
        """Met à jour les métriques Prometheus pour Grafana"""
        try:
            # Extraire les labels
            etat = log_data.get('etat', 'UNKNOWN')
            source = log_data.get('source', {}).get('name', 'unknown')
            zone = log_data.get('zone', 'unknown')
            entreprise = log_data.get('entreprise', 'unknown')
            objet = log_data.get('objet', {}).get('name', 'unknown')

            performance = log_data.get('performance', {})
            duree_secondes = performance.get('duree_secondes', 0)
            memory_bytes = performance.get('memory_used_bytes', 0)
            cpu_seconds = performance.get('cpu_time_sec', 0)

            # Métriques de base
            ingestion_runs_total.labels(
                etat=etat,
                source=source,
                zone=zone,
                entreprise=entreprise,
                objet=objet
            ).inc()

            # Métriques de performance
            if duree_secondes > 0:
                ingestion_duration_seconds.labels(
                    source=source,
                    zone=zone,
                    entreprise=entreprise,
                    objet=objet
                ).observe(duree_secondes)

            if memory_bytes > 0:
                ingestion_memory_usage_bytes.labels(
                    source=source,
                    zone=zone,
                    entreprise=entreprise,
                    objet=objet
                ).observe(memory_bytes)

            if cpu_seconds > 0:
                ingestion_cpu_usage_seconds.labels(
                    source=source,
                    zone=zone,
                    entreprise=entreprise,
                    objet=objet
                ).observe(cpu_seconds)

            # Métriques pour les alertes
            if etat == 'FAILED':
                description = log_data.get('description', 'unknown_error')
                ingestion_failures_total.labels(
                    source=source,
                    zone=zone,
                    entreprise=entreprise,
                    objet=objet,
                    description=description
                ).inc()

            # Timestamp de dernière exécution (pour détecter les sources muettes)
            ingestion_last_run_timestamp.labels(
                source=source,
                zone=zone,
                entreprise=entreprise
            ).set_to_current_time()

            # Métriques d'alertes spécifiques
            if duree_secondes > 30:  # Exécution lente
                ingestion_slow_executions_total.labels(
                    source=source,
                    zone=zone,
                    entreprise=entreprise,
                    objet=objet
                ).inc()

            if memory_bytes > 150 * 1024 * 1024:  # Haute consommation mémoire
                ingestion_high_memory_usage_total.labels(
                    source=source,
                    zone=zone,
                    entreprise=entreprise,
                    objet=objet
                ).inc()

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des métriques Prometheus: {e}")

    def send_to_loki(self, log_data: Dict[str, Any]) -> bool:
        """Envoie les logs vers Loki pour Grafana"""
        try:
            # Extraire les labels
            labels = self.extract_labels_for_loki(log_data)

            # Formatage du timestamp pour Loki (nanoseconds)
            timestamp_ns = str(int(time.time() * 1_000_000_000))

            # Message de log structuré pour Grafana
            log_line = {
                'etat': log_data.get('etat'),
                'source': labels['source'],
                'objet': labels['objet'],
                'duree_secondes': log_data.get('performance', {}).get('duree_secondes'),
                'memory_mb': log_data.get('performance', {}).get('memory_used_mb'),
                'cpu_time_sec': log_data.get('performance', {}).get('cpu_time_sec'),
                'description': log_data.get('description'),
                'debut': log_data.get('performance', {}).get('debut'),
                'fin': log_data.get('performance', {}).get('fin')
            }

            # Payload pour Loki
            loki_payload = {
                'streams': [
                    {
                        'stream': labels,
                        'values': [
                            [timestamp_ns, json.dumps(log_line, ensure_ascii=False)]
                        ]
                    }
                ]
            }

            # Envoi vers Loki
            response = requests.post(
                f"{self.loki_url}/loki/api/v1/push",
                json=loki_payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            if response.status_code == 204:
                logger.debug(f"Log envoyé vers Loki: {labels['source']}/{labels['objet']}")
                return True
            else:
                logger.warning(f"Erreur Loki: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Erreur de connexion à Loki: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi vers Loki: {e}")
            return False

    def process_log_message(self, message) -> None:
        """Traite un message de log reçu de Kafka"""
        try:
            log_data = message.value

            logger.info(f"Traitement log: {log_data.get('source', {}).get('name', 'unknown')}/"
                       f"{log_data.get('objet', {}).get('name', 'unknown')} - "
                       f"État: {log_data.get('etat', 'UNKNOWN')}")

            # Mettre à jour les métriques Prometheus
            self.update_prometheus_metrics(log_data)

            # Envoyer vers Loki pour Grafana
            if self.send_to_loki(log_data):
                logger.debug("Log traité avec succès")
            else:
                logger.warning("Échec de l'envoi vers Loki")

        except Exception as e:
            logger.error(f"Erreur lors du traitement du message: {e}")

    def run_consumer(self) -> None:
        """Execute le consumer principal"""
        logger.info("Démarrage du consumer de logs d'ingestion")

        try:
            for message in self.consumer:
                if not self.running:
                    break

                self.process_log_message(message)

        except KafkaError as e:
            logger.error(f"Erreur Kafka: {e}")
        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur")
        except Exception as e:
            logger.error(f"Erreur dans le consumer: {e}")
        finally:
            self.close()

    def close(self) -> None:
        """Ferme proprement les connexions"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("Consumer fermé")

def start_metrics_server():
    """Démarre le serveur de métriques Prometheus"""
    try:
        start_http_server(METRICS_PORT)
        logger.info(f"Serveur de métriques Prometheus démarré sur le port {METRICS_PORT}")
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du serveur de métriques: {e}")

def main():
    """Point d'entrée principal"""
    # Démarrer le serveur de métriques Prometheus dans un thread séparé
    metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    metrics_thread.start()

    consumer = None
    try:
        # Attendre un peu que les services soient prêts
        time.sleep(5)

        consumer = IngestionLogConsumer()
        consumer.run_consumer()

    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
    finally:
        if consumer:
            consumer.close()

if __name__ == "__main__":
    main()