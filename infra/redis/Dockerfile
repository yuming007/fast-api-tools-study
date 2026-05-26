FROM redis:7.4-alpine

# 把本地学习场景常用的 Redis 配置固化进镜像。
COPY redis.conf /usr/local/etc/redis/redis.conf

CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
