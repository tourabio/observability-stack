import json
import logging
import uuid
import math
from typing import Optional, Dict, Any, List
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
import structlog
from datetime import datetime

logger = structlog.get_logger()

class KafkaClient:
    def __init__(self, bootstrap_servers: str = "kafka:29092"):
        self.bootstrap_servers = bootstrap_servers
        self.producer_config = {
            'bootstrap.servers': bootstrap_servers,
            'client.id': 'observability-producer',
            'acks': 'all',
            'retries': 3,
            'batch.size': 16384,
            'linger.ms': 10,
            'message.max.bytes': 1000000,
        }
        
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True,
            'group.id': 'observability-consumer',
        }
        
        self.admin_config = {
            'bootstrap.servers': bootstrap_servers
        }

    def create_producer(self) -> Producer:
        """Create Kafka producer"""
        try:
            logger.info(f"Creating producer with config: {self.producer_config}")
            producer = Producer(self.producer_config)
            logger.info("Producer created successfully")
            return producer
        except Exception as e:
            logger.error(f"Failed to create Kafka producer: {e}")
            raise

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

    def chunk_data(self, data: dict, max_chunk_size: int = 50000) -> List[Dict]:
        """Split large data into smaller chunks"""
        try:
            # Serialize the full data to check size
            full_message = json.dumps(data, default=str)
            full_size = len(full_message.encode('utf-8'))
            
            # If message is small enough, return as single chunk
            if full_size <= max_chunk_size:
                return [data]
            
            # Split data into chunks
            chunk_id = str(uuid.uuid4())
            chunks = []
            
            # For log entries, split by individual log records if it's a list
            if isinstance(data, dict) and 'logs' in data and isinstance(data['logs'], list):
                logs = data['logs']
                total_logs = len(logs)
                
                # Calculate how many logs per chunk
                estimated_log_size = full_size // total_logs
                logs_per_chunk = max(1, max_chunk_size // estimated_log_size)
                
                # Split logs into chunks
                for i in range(0, total_logs, logs_per_chunk):
                    chunk_logs = logs[i:i + logs_per_chunk]
                    chunk_data = data.copy()
                    chunk_data['logs'] = chunk_logs
                    
                    chunk = {
                        'chunk_id': chunk_id,
                        'total_chunks': math.ceil(total_logs / logs_per_chunk),
                        'chunk_number': len(chunks) + 1,
                        'data': chunk_data,
                        'timestamp': datetime.now().isoformat(),
                        'source': 'kafka-chunking'
                    }
                    chunks.append(chunk)
            
            # For single log entries, split by fields if too large
            else:
                # Simple approach: create multiple chunks with partial data
                chunk_data = data.copy()
                
                chunk = {
                    'chunk_id': chunk_id,
                    'total_chunks': 1,
                    'chunk_number': 1,
                    'data': chunk_data,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'kafka-chunking'
                }
                chunks.append(chunk)
            
            logger.info(f"Split message into {len(chunks)} chunks", 
                       original_size=full_size, chunk_id=chunk_id)
            
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to chunk data: {e}")
            return [data]  # Return original data if chunking fails

    def produce_chunked_message(self, producer: Producer, topic: str, key: str, data: dict):
        """Produce a message, chunking if necessary"""
        try:
            if producer is None:
                raise ValueError("Producer is None - Kafka connection not initialized")
                
            chunks = self.chunk_data(data)
            
            for chunk in chunks:
                chunk_key = f"{key}:chunk:{chunk.get('chunk_number', 1)}"
                
                producer.produce(
                    topic=topic,
                    key=chunk_key,
                    value=json.dumps(chunk, default=str),
                    callback=self._delivery_callback
                )
                producer.poll(0)
                
            logger.info(f"Produced {len(chunks)} chunks to {topic}")
            
        except Exception as e:
            logger.error(f"Failed to produce chunked message: {e}")

    def reconstruct_chunked_message(self, chunks: List[dict]) -> Optional[dict]:
        """Reconstruct original message from chunks"""
        try:
            if not chunks:
                return None
            
            # Sort chunks by chunk_number
            sorted_chunks = sorted(chunks, key=lambda x: x.get('chunk_number', 0))
            
            # Verify we have all chunks
            first_chunk = sorted_chunks[0]
            total_chunks = first_chunk.get('total_chunks', 1)
            
            if len(sorted_chunks) != total_chunks:
                logger.warning(f"Missing chunks: expected {total_chunks}, got {len(sorted_chunks)}")
                return None
            
            # Reconstruct the original data
            if total_chunks == 1:
                return first_chunk.get('data')
            
            # For multi-chunk messages, combine the data
            reconstructed = first_chunk.get('data', {})
            
            # If chunks contain logs, combine them
            if 'logs' in reconstructed:
                all_logs = []
                for chunk in sorted_chunks:
                    chunk_data = chunk.get('data', {})
                    if 'logs' in chunk_data:
                        all_logs.extend(chunk_data['logs'])
                reconstructed['logs'] = all_logs
            
            logger.info(f"Reconstructed message from {total_chunks} chunks")
            return reconstructed
            
        except Exception as e:
            logger.error(f"Failed to reconstruct chunked message: {e}")
            return None