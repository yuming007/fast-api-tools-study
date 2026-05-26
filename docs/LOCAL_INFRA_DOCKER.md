# 基础设施单独启动说明

这个文档配合 `infra/` 目录使用。目标不是一键起全部服务，而是让你可以本地逐个 `build` / `run` 某个组件，单独验证它的行为。

## 1. 目录说明

```text
infra/
├── clickhouse
├── elasticsearch
├── mysql
├── rabbitmq
└── redis
```

你可以有两种启动方式：

- 方式 A：逐个 `docker build` + `docker run`
- 方式 B：使用 `docker-compose.infra.yml`，按服务名单独启动

## 2. MySQL

### 2.1 构建镜像

```bash
docker build -t study-mysql ./infra/mysql
```

### 2.2 启动容器

```bash
docker run -d \
  --name study-mysql \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=crawler \
  -e MYSQL_USER=study \
  -e MYSQL_PASSWORD=study \
  -v study_mysql_data:/var/lib/mysql \
  study-mysql
```

### 2.3 测试

```bash
docker exec -it study-mysql mysql -ustudy -pstudy crawler
```

## 3. Redis

### 3.1 构建镜像

```bash
docker build -t study-redis ./infra/redis
```

### 3.2 启动容器

```bash
docker run -d \
  --name study-redis \
  -p 6379:6379 \
  -v study_redis_data:/data \
  study-redis
```

### 3.3 测试

```bash
docker exec -it study-redis redis-cli ping
docker exec -it study-redis redis-cli set hello world
docker exec -it study-redis redis-cli get hello
```

## 4. RabbitMQ

### 4.1 构建镜像

```bash
docker build -t study-rabbitmq ./infra/rabbitmq
```

### 4.2 启动容器

```bash
docker run -d \
  --name study-rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=study \
  -e RABBITMQ_DEFAULT_PASS=study \
  -v study_rabbitmq_data:/var/lib/rabbitmq \
  study-rabbitmq
```

### 4.3 测试

```bash
docker exec -it study-rabbitmq rabbitmqctl status
```

管理台：

- `http://localhost:15672`
- 用户名：`study`
- 密码：`study`

## 5. ClickHouse

### 5.1 构建镜像

```bash
docker build -t study-clickhouse ./infra/clickhouse
```

### 5.2 启动容器

```bash
docker run -d \
  --name study-clickhouse \
  -p 8123:8123 \
  -p 9000:9000 \
  -e CLICKHOUSE_DB=crawler_analytics \
  -e CLICKHOUSE_USER=study \
  -e CLICKHOUSE_PASSWORD=study \
  -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 \
  -v study_clickhouse_data:/var/lib/clickhouse \
  study-clickhouse
```

### 5.3 测试

```bash
docker exec -it study-clickhouse clickhouse-client --user study --password study --query "SELECT 1"
```

## 6. Elasticsearch

### 6.1 构建镜像

```bash
docker build -t study-elasticsearch ./infra/elasticsearch
```

### 6.2 启动容器

```bash
docker run -d \
  --name study-elasticsearch \
  -p 9200:9200 \
  -e ES_JAVA_OPTS="-Xms512m -Xmx512m" \
  -v study_elasticsearch_data:/usr/share/elasticsearch/data \
  study-elasticsearch
```

### 6.3 测试

```bash
curl http://localhost:9200
```

## 7. 使用 docker-compose.infra.yml

如果你想少打一点命令，可以用这个文件按服务名启动：

```bash
docker compose -f docker-compose.infra.yml up --build mysql
docker compose -f docker-compose.infra.yml up --build redis
docker compose -f docker-compose.infra.yml up --build rabbitmq
docker compose -f docker-compose.infra.yml up --build clickhouse
docker compose -f docker-compose.infra.yml up --build elasticsearch
```

也可以一次起多个：

```bash
docker compose -f docker-compose.infra.yml up --build mysql redis rabbitmq
```

## 8. 适合你的测试顺序

建议顺序：

1. 先测 `MySQL` 和 `Redis`
2. 再测 `RabbitMQ`
3. 再测 `ClickHouse`
4. 最后测 `Elasticsearch`

原因：

- MySQL 和 Redis 最容易上手，也最容易快速验证
- RabbitMQ 可以帮助你理解 broker / queue / consumer
- ClickHouse 和 Elasticsearch 更吃资源，适合最后测试
