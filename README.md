# fast-api-tools-study

一个面向学习的微服务项目：使用 `FastAPI + asyncmy + SQLAlchemy Async ORM + redis.asyncio + Celery + RabbitMQ + Redis + Elasticsearch + ClickHouse + Docker Compose` 搭建一条完整的数据采集链路。

这个仓库的目标不是堆技术名词，而是让每个中间件都在一条真实链路里发挥作用，并且让你可以本地逐个观察。

## 1. 项目目标

本项目模拟一个“分布式内容采集平台”：

- `gateway-service` 负责任务管理和手动触发
- `scheduler-service` 负责观察调度状态和手动触发调度扫描
- `worker-service` 负责暴露 Celery worker 运行状态
- `search-service` 负责全文检索和统计分析
- `mock-source-service` 负责模拟外部数据源
- `celery-worker` 负责真正执行抓取、索引和分析写入
- `celery-beat` 负责周期触发调度扫描
- `flower` 负责观察 Celery 任务执行情况

基础设施职责如下：

- `MySQL` 存任务、执行记录、文章元数据
- `Redis` 做异步缓存、分布式锁、去重、Celery result backend
- `RabbitMQ` 做 Celery broker
- `Elasticsearch` 做全文搜索
- `ClickHouse` 存分析明细并做聚合统计
- `Docker Compose` 负责整套环境编排

## 2. 业务链路

完整执行链路如下：

1. 用户调用 `gateway-service` 创建采集任务
2. `celery-beat` 周期性触发 `run_scheduler_scan` 任务
3. 调度任务扫描 MySQL 中到期任务，并使用 Redis 分布式锁防止重复调度
4. 调度任务把抓取执行任务投递到 Celery
5. Celery 通过 RabbitMQ broker 把消息分发给 `celery-worker`
6. `celery-worker` 调用 `mock-source-service` 获取文章数据
7. `celery-worker` 将结构化元数据写入 MySQL
8. `celery-worker` 将正文索引写入 Elasticsearch
9. `celery-worker` 将抓取统计事件写入 ClickHouse
10. `celery-worker` 使用 `redis.asyncio` 更新去重状态和搜索缓存版本
11. `search-service` 从 Elasticsearch 做全文检索，从 ClickHouse 做统计分析，并将热点搜索结果缓存到 Redis

## 3. 项目结构

```text
.
├── app
│   ├── bootstrap.py
│   ├── common
│   │   ├── bootstrap.py
│   │   ├── celery_app.py
│   │   ├── clickhouse_client.py
│   │   ├── config.py
│   │   ├── dispatching.py
│   │   ├── elasticsearch_client.py
│   │   ├── models.py
│   │   ├── mysql.py
│   │   ├── rabbitmq.py
│   │   ├── redis_client.py
│   │   ├── redis_state.py
│   │   ├── repositories.py
│   │   ├── schemas.py
│   │   └── time_utils.py
│   ├── services
│   └── tasks
├── docs
├── infra
├── docker-compose.yml
├── docker-compose.infra.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## 4. 服务说明

### 4.1 gateway-service

职责：

- 创建任务
- 查看任务
- 查看执行记录
- 手动触发 Celery 执行任务

关键学习点：

- FastAPI 异步依赖注入
- AsyncSession
- `redis.asyncio` 锁
- `asyncio.to_thread` 包装同步 broker 调用
- Celery 任务投递

访问地址：

- `http://localhost:8000/docs`

### 4.2 scheduler-service

职责：

- 观察调度状态
- 手动触发 Celery 调度扫描任务

关键学习点：

- Celery Beat 与 API 协同
- Redis 分布式锁状态观察
- 调度状态持久化到 Redis
- 手动触发调度扫描任务

访问地址：

- `http://localhost:8001/docs`

### 4.3 worker-service

职责：

- 暴露 Celery worker 最近的处理状态
- 便于观察成功数、失败数、最后一次错误

关键学习点：

- 用 FastAPI 做 worker 观察面
- Redis 记录 worker 执行状态

访问地址：

- `http://localhost:8002/docs`

### 4.4 search-service

职责：

- 基于 Elasticsearch 做全文检索
- 基于 ClickHouse 做趋势和统计分析
- 基于 `redis.asyncio` 做搜索缓存

关键学习点：

- 缓存优先读取
- 缓存重建锁防击穿
- TTL 抖动
- `asyncio.to_thread` 包装同步 ES/ClickHouse 客户端

访问地址：

- `http://localhost:8003/docs`

### 4.5 mock-source-service

职责：

- 模拟外部站点返回数据
- 生成稳定重复数据和新数据
- 帮你观察 Redis 去重行为

访问地址：

- `http://localhost:8004/docs`

### 4.6 celery-worker / celery-beat / flower

职责：

- `celery-worker`：执行抓取任务
- `celery-beat`：周期触发调度扫描
- `flower`：观察 Celery 执行状态

访问地址：

- Flower: `http://localhost:5555`

## 5. Redis 在项目中的几种用法

### 5.1 手动触发限流锁

键示例：

- `study:lock:manual-dispatch:{task_id}`

### 5.2 调度分布式锁

键示例：

- `study:lock:schedule:{task_id}`

### 5.3 文章去重

键示例：

- `study:dedupe:article:{external_id}`

### 5.4 搜索缓存

键示例：

- `study:search:cache:...`
- `study:search:version:global:all`
- `study:search:version:topic:{topic}`
- `study:search:version:source:{source}`
- `study:lock:search-cache-rebuild:{sha1}`

### 5.5 Celery 结果和 worker 统计

- Redis DB 1 作为 Celery result backend
- `study:worker:stats`
- `study:scheduler:state`

## 6. Celery 在项目中的用法

当前项目已经正式引入 Celery：

- broker: `RabbitMQ`
- result backend: `Redis`
- worker: `celery-worker`
- beat: `celery-beat`
- 监控: `flower`

当前包含两个核心任务：

- `app.tasks.crawl_tasks.execute_crawl_run`
- `app.tasks.scheduler_tasks.run_scheduler_scan`

关键配置：

- `task_acks_late=True`
- `worker_prefetch_multiplier=1`
- `autoretry_for`
- `retry_backoff=True`
- `Redis` 作为 result backend
- `Flower` 做可视化观察

## 7. 快速开始

### 7.1 环境要求

- Docker Desktop 或 Docker Engine
- Docker Compose
- 建议内存至少 6GB

### 7.2 启动整套项目

```bash
cp .env.example .env
docker compose up --build
```

启动后可访问：

- Gateway: `http://localhost:8000/docs`
- Scheduler: `http://localhost:8001/docs`
- Worker Stats: `http://localhost:8002/docs`
- Search: `http://localhost:8003/docs`
- Mock Source: `http://localhost:8004/docs`
- RabbitMQ 管理台: `http://localhost:15672`
- Flower: `http://localhost:5555`

## 8. 体验完整链路

### 8.1 查看自动创建的任务

```bash
curl http://localhost:8000/tasks
```

### 8.2 手动触发任务

```bash
curl -X POST http://localhost:8000/tasks/1/dispatch
```

返回值里会包含：

- `run_id`
- `celery_task_id`

### 8.3 手动触发调度扫描

```bash
curl -X POST http://localhost:8001/scheduler/tick
```

### 8.4 查看 Celery worker 状态

```bash
curl http://localhost:8002/worker/stats
```

### 8.5 搜索并观察缓存命中

```bash
curl "http://localhost:8003/search?q=agent&topic=ai"
```

第一次通常会回源 Elasticsearch，第二次可以观察到 `cached=true`。

### 8.5 进行全文搜索

```bash
curl "http://localhost:8003/search?q=agent"
```

首次通常返回 `cached=false`，再次请求通常返回 `cached=true`。

## 9. 单独测试基础设施

如果你想单独起 MySQL、Redis、RabbitMQ、ClickHouse、Elasticsearch，请看：

- [docs/LOCAL_INFRA_DOCKER.md](/mnt/c/workspace_2/fast-api-tools-study/docs/LOCAL_INFRA_DOCKER.md)

## 10. 相关文档

- 技术知识点整理见 [docs/TECH_NOTES.md](/mnt/c/workspace_2/fast-api-tools-study/docs/TECH_NOTES.md)
- 最佳实践评估见 [docs/BEST_PRACTICE_REVIEW.md](/mnt/c/workspace_2/fast-api-tools-study/docs/BEST_PRACTICE_REVIEW.md)
- 基础设施单独启动说明见 [docs/LOCAL_INFRA_DOCKER.md](/mnt/c/workspace_2/fast-api-tools-study/docs/LOCAL_INFRA_DOCKER.md)
