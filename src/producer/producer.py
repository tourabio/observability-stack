#!/usr/bin/env python3
"""
Producer Python → Kafka : script producer.py qui lit logs.json et publie sur le topic ingestion-logs.
As specified in exercice_grafana_pipeline.md
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, List
from kafka import KafkaProducer
from kafka.errors import KafkaError
import sys

# Configuration from environment variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'ingestion-logs')
LOGS_FILE_PATH = os.getenv('LOGS_FILE_PATH', '/app/data/logs.json')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class IngestionLogProducer:
    """Producer pour publier les logs d'ingestion vers Kafka"""

    def __init__(self):
        self.producer = None
        self.topic = KAFKA_TOPIC
        self.connect_to_kafka()

    def connect_to_kafka(self) -> None:
        """Établit la connexion avec Kafka"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',  # Attendre la confirmation de tous les replicas
                retries=3,
                max_block_ms=30000,
                request_timeout_ms=30000,
                metadata_max_age_ms=300000,
                api_version=(2, 6, 0)
            )
            logger.info(f"Connecté au cluster Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"Erreur de connexion à Kafka: {e}")
            sys.exit(1)

    def improve_log_structure(self, original_log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Propose une structure améliorée des événements (logs) en JSON
        Suivant les bonnes pratiques pour l'observabilité
        """
        # Extraction et normalisation des métriques
        try:
            cpu_time = float(original_log.get('cpu_time (sec)', 0))
        except (ValueError, TypeError):
            cpu_time = 0.0

        try:
            memory_used = int(original_log.get('memory_used (bytes)', 0))
        except (ValueError, TypeError):
            memory_used = 0

        try:
            duree_secondes = float(original_log.get('Duree secondes', 0))
        except (ValueError, TypeError):
            duree_secondes = 0.0

        # Structure améliorée pour l'observabilité
        improved_log = {
            # Métadonnées d'événement
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "@version": "1",
            "event": {
                "dataset": "ingestion-logs",
                "kind": "event",
                "category": ["process"],
                "type": ["info" if original_log.get('Etat') == 'SUCCESS' else "error"],
                "outcome": "success" if original_log.get('Etat') == 'SUCCESS' else "failure"
            },

            # Informations de séquence et timing
            "sequence": {
                "no_sequence": original_log.get('No_Sequence'),
                "date_sequence": original_log.get('Date_Sequence'),
                "heure_sequence": original_log.get('Heure_Sequence'),
                "minute_sequence": original_log.get('Minute_Sequence')
            },

            # Contexte d'entreprise et zone
            "entreprise": original_log.get('Entreprise'),
            "zone": original_log.get('Zone'),

            # Source et objet traité
            "source": {
                "name": original_log.get('Source'),
                "type": "api"
            },
            "objet": {
                "id": original_log.get('Objet_Id'),
                "name": original_log.get('Objet'),
                "transformation": original_log.get('Transformation')
            },

            # État et résultat
            "etat": original_log.get('Etat'),
            "description": original_log.get('Description'),

            # Métriques de performance
            "performance": {
                "debut": original_log.get('Debut'),
                "fin": original_log.get('Fin'),
                "duree_secondes": duree_secondes,
                "cpu_time_sec": cpu_time,
                "memory_used_bytes": memory_used,
                "memory_used_mb": round(memory_used / (1024 * 1024), 2) if memory_used > 0 else 0
            },

            # Labels pour Grafana et alerting
            "labels": {
                "etat": original_log.get('Etat', 'UNKNOWN'),
                "source": original_log.get('Source', 'unknown'),
                "zone": original_log.get('Zone', 'unknown'),
                "entreprise": original_log.get('Entreprise', 'unknown'),
                "objet": original_log.get('Objet', 'unknown'),
                "transformation": original_log.get('Transformation', 'unknown')
            },

            # Métriques calculées pour les alertes
            "metrics": {
                "is_failed": 1 if original_log.get('Etat') == 'FAILED' else 0,
                "is_success": 1 if original_log.get('Etat') == 'SUCCESS' else 0,
                "duration_seconds": duree_secondes,
                "cpu_usage_seconds": cpu_time,
                "memory_usage_bytes": memory_used,
                "high_memory_usage": 1 if memory_used > 150 * 1024 * 1024 else 0,  # > 150MB
                "high_cpu_usage": 1 if cpu_time > 60 else 0,  # > 60s
                "slow_execution": 1 if duree_secondes > 30 else 0  # > 30s
            }
        }

        return improved_log

    def load_logs_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Charge les logs depuis le fichier JSON"""
        logs = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Le fichier contient une ligne JSON par log
                for line in content.split('\n'):
                    if line.strip():
                        try:
                            log_entry = json.loads(line.strip())
                            logs.append(log_entry)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Ligne JSON invalide ignorée: {line[:100]}... - Erreur: {e}")

            logger.info(f"Chargé {len(logs)} entrées de log depuis {file_path}")
            return logs

        except FileNotFoundError:
            logger.error(f"Fichier de logs non trouvé: {file_path}")
            return []
        except Exception as e:
            logger.error(f"Erreur lors du chargement des logs: {e}")
            return []

    def send_log_to_kafka(self, log_data: Dict[str, Any]) -> bool:
        """Envoie un log vers Kafka"""
        try:
            # Utilise le No_Sequence comme clé pour le partitioning
            key = log_data.get('sequence', {}).get('no_sequence', 'unknown')

            future = self.producer.send(
                self.topic,
                value=log_data,
                key=key
            )

            # Attendre la confirmation d'envoi
            record_metadata = future.get(timeout=10)

            logger.debug(f"Log envoyé vers topic {record_metadata.topic}, "
                        f"partition {record_metadata.partition}, "
                        f"offset {record_metadata.offset}")
            return True

        except KafkaError as e:
            logger.error(f"Erreur Kafka lors de l'envoi: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du log: {e}")
            return False

    def run_producer(self, simulate_realtime: bool = False) -> None:
        """Execute le producteur principal"""
        logger.info("Démarrage du producteur de logs d'ingestion")

        # Charger les logs depuis le fichier
        original_logs = self.load_logs_from_file(LOGS_FILE_PATH)

        if not original_logs:
            logger.error("Aucun log à traiter, arrêt du producteur")
            return

        success_count = 0
        error_count = 0

        for i, original_log in enumerate(original_logs):
            try:
                # Améliorer la structure du log
                improved_log = self.improve_log_structure(original_log)

                # Envoyer vers Kafka
                if self.send_log_to_kafka(improved_log):
                    success_count += 1
                    logger.info(f"Log {i+1}/{len(original_logs)} envoyé: "
                              f"Source={improved_log['source']['name']}, "
                              f"Objet={improved_log['objet']['name']}, "
                              f"État={improved_log['etat']}")
                else:
                    error_count += 1

                # Simulation temps réel si demandé (pour les tests)
                if simulate_realtime and i < len(original_logs) - 1:
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Erreur lors du traitement du log {i+1}: {e}")
                error_count += 1

        # Forcer l'envoi de tous les messages en attente
        self.producer.flush()

        logger.info(f"Producteur terminé: {success_count} succès, {error_count} erreurs")

    def close(self) -> None:
        """Ferme proprement les connexions"""
        if self.producer:
            self.producer.close()
            logger.info("Connexions fermées")

def main():
    """Point d'entrée principal"""
    producer = None
    try:
        producer = IngestionLogProducer()

        # Mode simulation temps réel si variable d'environnement définie
        simulate_realtime = os.getenv('SIMULATE_REALTIME', 'false').lower() == 'true'

        producer.run_producer(simulate_realtime=simulate_realtime)

    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
    finally:
        if producer:
            producer.close()

if __name__ == "__main__":
    main()