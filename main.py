from json import dump, load, dumps, loads
from threading import Thread, Event
from time import sleep
from traceback import format_exc
from kafka import KafkaProducer
import logging
from os.path import isfile

import handlers

class Monitor:
    
    def run(logging_level=logging.ERROR):
        with open("debug.log", "w"):
            pass
        logging.basicConfig(filename='debug.log', level=logging_level, filemode='a', datefmt='%Y-%m-%d %H:%M:%S', format='[%(asctime)s,%(msecs)d](%(levelname)s) - %(message)s')
        logger = logging.getLogger('vm_monitoring')
        try:
            with open("config.json") as f:
                config = load(f)
            Monitor._monitor(config, logger)
        except Exception as e:
            logger.error(f"Exception: {str(e)}\nTraceback: \n{format_exc()}")
            
    def _monitor(config, logger):
        with open("metrics.json") as f:
            metrics = load(f)
        accounts = list(Monitor._add_handlers(Monitor._filter_disable(config["accounts"])))
        event = Event()
        threads = Monitor._init_threads(event, accounts, metrics, config, logger)
        Monitor._start_threads(threads)
        input("Press any key to stop...")
        event.set()
        print("Waiting for threads to exit properly...")

    def _start_threads(threads):
        for thread in threads:
            thread.start()

    def _init_threads(event, accounts, metrics, config, logger):
        return list(map(lambda account: Thread(target=Monitor._task, args=(event, account, metrics, config, logger)), accounts))

    def _task(event, account, metrics, config, logger):
        account["metrics"] = metrics
        account["template"] = Monitor._load_template(account["template"])
        try:
            producer = KafkaProducer(bootstrap_servers=[config["kafka_ip"]], value_serializer=lambda m: dumps(m).encode('ascii'), api_version=(0, 10, 1))
        except Exception as e:
            logger.error(f"Not able to initialize Kafka producer: {str(e)}\n{format_exc()}")
            producer = None
        while not event.is_set():
            transformed = account["handler"].transform(account, logger)
            if transformed is not None:
                if account["log_to_file"]:
                    logger.info(f"Logging output result in '{account['output_file']}'.")
                    if not isfile(account["output_file"]):
                        with open(account["output_file"], "w"):
                            pass
                    with open(account["output_file"]) as f:
                        content = f.read()
                        if content == "":
                            data = []
                        else:
                            data = loads(content)
                    data.append(transformed)
                    with open(account["output_file"], 'w') as f:
                        dump(data, f, indent=4)
                if account["send_to_kafka"]:
                    if producer is None:
                        logger.warning("Cannot send to Kakfa because the producer has not been properly initialized.")
                    else:
                        logger.info(f"Sending to Kafka for '{account['ent_name']}'.")
                        for elt in transformed:
                            producer.send(account["ent_name"], elt)
            else:
                logger.warning(f"Handler returned null result for '{account['ent_name']}'.")
            sleep(config['polling_interval'])

    def _filter_disable(accounts):
        return filter(lambda x: x["enable"], accounts)

    def _add_handlers(accounts):
        return map(lambda account: {**account, "handler": getattr(handlers, account["provider"])}, accounts)

    def _load_template(template):
        with open(template) as f:
            return load(f)
        
if __name__ == "__main__":
    Monitor.run(logging_level=logging.DEBUG)

