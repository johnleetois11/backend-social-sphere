import redis

try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=2)
    redis_client.ping()
except:
    redis_client = None