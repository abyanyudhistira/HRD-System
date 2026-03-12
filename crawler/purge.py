import pika
import ssl

QUEUE_NAME = "nama_queue_kamu"

credentials = pika.PlainCredentials(
    "fexihtwb",
    "ETd7Y9BSMTZWZnKtqGQr5ikP4o63oB0u"
)

ssl_context = ssl.create_default_context()

parameters = pika.ConnectionParameters(
    host="leopard.lmq.cloudamqp.com",
    port=5671,
    virtual_host="fexihtwb",
    credentials=credentials,
    ssl_options=pika.SSLOptions(ssl_context)
)

connection = pika.BlockingConnection(parameters)
channel = connection.channel()

channel.queue_purge(queue=QUEUE_NAME)

print("PURGED:", QUEUE_NAME)

connection.close()