from kafka import KafkaConsumer
from json import load, loads

with open("config.json") as f:
    config = load(f)

topics = list(map(lambda account: account['ent_name'], config['accounts']))
consumer = KafkaConsumer(
    *topics,
    bootstrap_servers=[config['kafka_ip']],
    auto_offset_reset='earliest',
    enable_auto_commit=True,
    group_id='my-group',
    value_deserializer=lambda x: loads(x.decode('utf-8'))
)
for message in consumer:
    print(message.value)