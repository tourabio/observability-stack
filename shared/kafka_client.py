import json
import logging
from typing import Optional, Dict, Any
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
import structlog

logger = structlog.get_logger()

class KafkaClient:
    def __init__(self, bootstrap_servers: str = "kafka:9092"):
        self.bootstrap_servers = bootstrap_servers
        self.producer_config = {
            'bootstrap.servers': bootstrap_servers,
            'client.id': 'observability-producer',
            'acks': 'all',
            'retries': 3,
            'batch.size': 16384,
            'linger.ms': 10,
            'buffer.memory': 33554432,
            'message.max.bytes': 1000000,
        }
        
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True,
            'group.id': 'observability-consumer',
            'fetch.message.max.bytes': 1048576,
        }
        
        self.admin_config = {
            'bootstrap.servers': bootstrap_servers
        }

    def create_producer(self) -> Producer:
        """Create Kafka producer"""
        return Producer(self.producer_config)

    def create_consumer(self, group_id: str, topics: list) -> Consumer:
        """Create Kafka consumer"""
        config = self.consumer_config.copy()
        config['group.id'] = group_id
        consumer = Consumer(config)
        consumer.subscribe(topics)
        return consumer

    def create_topics(self, topics: Dict[str, Dict[str, Any]]):
        """Create Kafka topics if they don't exist"""
        admin_client = AdminClient(self.admin_config)
        
        # Get existing topics
        cluster_metadata = admin_client.list_topics(timeout=10)
        existing_topics = set(cluster_metadata.topics.keys())
        
        # Create new topics
        new_topics = []
        for topic_name, config in topics.items():
            if topic_name not in existing_topics:
                topic = NewTopic(
                    topic=topic_name,
                    num_partitions=config.get('partitions', 3),
                    replication_factor=config.get('replication_factor', 1),
                    config=config.get('config', {})
                )
                new_topics.append(topic)
        
        if new_topics:
            try:
                futures = admin_client.create_topics(new_topics)
                for topic, future in futures.items():
                    future.result()
                    logger.info(f"Topic {topic} created successfully")
            except KafkaException as e:
                logger.error(f"Failed to create topics: {e}")

    def produce_message(self, producer: Producer, topic: str, key: str, value: dict):
        """Produce a message to Kafka"""
        try:
            producer.produce(
                topic=topic,
                key=key,
                value=json.dumps(value, default=str),
                callback=self._delivery_callback
            )
            producer.poll(0)
        except Exception as e:
            logger.error(f"Failed to produce message: {e}")

    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation"""
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def consume_messages(self, consumer: Consumer, timeout: float = 1.0):
        """Consume messages from Kafka"""
        try:
            msg = consumer.poll(timeout=timeout)
            if msg is None:
                return None
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.info(f"End of partition reached {msg.topic()}/{msg.partition()}")
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                return None
            
            return {
                'topic': msg.topic(),
                'partition': msg.partition(),
                'offset': msg.offset(),
                'key': msg.key().decode('utf-8') if msg.key() else None,
                'value': json.loads(msg.value().decode('utf-8')),
                'timestamp': msg.timestamp()
            }
        except Exception as e:
            logger.error(f"Error consuming message: {e}")
            return None