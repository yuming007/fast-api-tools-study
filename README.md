# fast-api-tools-study

一个面向学习的微服务项目：使用 `FastAPI + MySQL + Redis + RabbitMQ + Elasticsearch + ClickHouse + Docker Compose` 搭建一条完整的数据采集链路。

这个仓库不是为了追求“业务复杂度”，而是为了把每个中间件放到真实链路里，让你能本地启动、手动触发、观察调度、查看消息消费、做全文检索、做统计分析。

## 1. 项目目标

本项目模拟一个“分布式内容采集平台”：

- `gateway-service` 负责任务管理和手动触发
- `scheduler-service` 负责任务周期调度
- `worker-service` 负责消费任务并执行抓取
- `search-service` 负责全文检索和统计分析
- `mock-source-service` 负责模拟外部数据源

基础设施职责如下：

- `MySQL` 存任务、执行记录、文章元数据
- `Redis` 做缓存、分布式锁、去重
- `RabbitMQ` 做异步任务队列
- `Elasticsearch` 做全文搜索
- `ClickHouse` 存分析明细并做聚合统计
- `Docker Compose` 负责整套环境编排

## 2. 业务链路

完整执行链路如下：

1. 用户调用 `gateway-service` 创建采集任务
2. `scheduler-service` 周期性扫描 MySQL 中到期任务
3. 调度器使用 Redis 分布式锁防止重复调度
4. 网关或调度器把任务消息投递到 RabbitMQ
5. `worker-service` 消费消息，调用 `mock-source-service` 获取文章数据
6. worker 将结构化元数据写入 MySQL
7. worker 将正文索引写入 Elasticsearch
8. worker 将抓取统计事件写入 ClickHouse
9. worker 更新 Redis 中的搜索缓存版本
10. `search-service` 从 Elasticsearch 做全文检索，从 ClickHouse 做统计分析，并将热点搜索结果缓存到 Redis

## 3. 项目结构

```text
.
├── app
│   ├── bootstrap.py
│   ├── common
│   │   ├── bootstrap.py
│   │   ├── clickhouse_client.py
│   │   ├── config.py
│   │   ├── dispatching.py
│   │   ├── elasticsearch_client.py
│   │   ├── models.py
│   │   ├── mysql.py
│   │   ├── rabbitmq.py
│   │   ├── redis_client.py
│   │   ├── repositories.py
│   │   ├── schemas.py
│   │   └── time_utils.py
│   └── services
│       ├── gateway
│       ├── mock_source
│       ├── scheduler
│       ├── search
│       └── worker
├── docs
│   └── TECH_NOTES.md
├── docker-compose.yml
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
- 手动触发任务

关键学习点：

- FastAPI 路由设计
- MySQL 事务写入
- Redis 手动触发限流锁
- RabbitMQ 生产消息

访问地址：

- `http://localhost:8000/docs`

### 4.2 scheduler-service

职责：

- 周期扫描到期任务
- 使用 Redis 锁防止重复调度
- 将任务投递到 RabbitMQ

关键学习点：

- APScheduler 定时调度
- 多实例调度时的分布式锁
- MySQL 中任务调度时间推进

访问地址：

- `http://localhost:8001/docs`

### 4.3 worker-service

职责：

- 消费 RabbitMQ 消息
- 调用 mock source 获取文章
- 写入 MySQL、Elasticsearch、ClickHouse
- 更新 Redis 去重键与缓存版本

关键学习点：

- 消息消费模型
- 幂等和去重
- 多存储分层写入
- 任务运行状态流转

访问地址：

- `http://localhost:8002/docs`

### 4.4 search-service

职责：

- 基于 Elasticsearch 做全文检索
- 基于 ClickHouse 做趋势和统计分析
- 基于 Redis 做搜索缓存

关键学习点：

- ES 多字段搜索
- 高亮结果
- ClickHouse 聚合分析
- 缓存命中与缓存失效

访问地址：

- `http://localhost:8003/docs`

### 4.5 mock-source-service

职责：

- 模拟外部站点返回数据
- 生成稳定重复数据和新数据
- 帮你观察 Redis 去重行为

访问地址：

- `http://localhost:8004/docs`

## 5. 数据模型设计

### 5.1 MySQL

核心表：

- `crawl_tasks`
  任务定义，保存主题、批次大小、调度周期、是否启用等
- `crawl_runs`
  每次执行的运行记录，保存状态、抓取数、索引数、错误信息等
- `articles`
  文章元数据，保存标题、摘要、作者、来源、哈希等

### 5.2 Elasticsearch

索引：

- `articles`

字段重点：

- `title`
- `summary`
- `content`
- `topic`
- `source`
- `published_at`

### 5.3 ClickHouse

表：

- `crawl_metrics`

字段重点：

- `event_time`
- `task_id`
- `run_id`
- `article_external_id`
- `fetch_latency_ms`
- `body_length`
- `word_count`

## 6. Redis 在项目中的四种用法

### 6.1 手动触发限流

键示例：

- `manual-dispatch:{task_id}`

作用：

- 避免用户连续点击接口导致任务被短时间重复投递

### 6.2 调度分布式锁

键示例：

- `schedule-lock:{task_id}`

作用：

- 当 `scheduler-service` 多实例运行时，保证同一任务只被一个实例调度

### 6.3 文章去重

键示例：

- `article-dedupe:{external_id}`

作用：

- 避免重复文章在短时间内被重复写入多个系统

### 6.4 搜索缓存

键示例：

- `search:v{version}:q={q}:topic={topic}:source={source}:size={size}`

作用：

- 缓存热点搜索结果，减少 Elasticsearch 查询压力

## 7. RabbitMQ 在项目中的用法

交换机与队列：

- exchange: `crawl.direct`
- queue: `crawl.jobs`
- routing key: `crawl.execute`

消息流向：

- `gateway-service -> RabbitMQ -> worker-service`
- `scheduler-service -> RabbitMQ -> worker-service`

学习重点：

- 消息解耦
- 持久化队列
- 消费者预取数 `prefetch_count`

## 8. Elasticsearch 在项目中的用法

搜索逻辑：

- `title^3`
- `summary^2`
- `content`

说明：

- 标题权重最高
- 摘要次之
- 正文参与召回
- 返回高亮片段，便于观察搜索效果

## 9. ClickHouse 在项目中的用法

本项目使用 ClickHouse 记录分析事件，而不是业务主数据。

这样设计的原因：

- 分析数据写入量更大
- 聚合查询更多
- 不要求强事务

当前提供两个分析接口：

- `/analytics/summary`
- `/analytics/trend`

## 10. 快速开始

### 10.1 环境要求

- Docker Desktop 或 Docker Engine
- Docker Compose
- 建议内存至少 6GB

说明：

- Elasticsearch 和 ClickHouse 都比较占资源
- 当前仓库所在 WSL 环境未安装 `docker` 命令，因此我完成了代码与 Compose 编排，但没有在本环境实际拉起容器验收

### 10.2 启动项目

如果你需要自定义配置，先准备环境变量：

```bash
cp .env.example .env
```

说明：

- `docker-compose.yml` 当前默认直接读取 `.env.example`
- 如果你改成使用 `.env`，记得同步修改 `docker-compose.yml` 里的 `env_file`
- 本项目在 Docker 内运行时，Compose 注入的环境变量优先级高于代码里的默认值

然后启动整套服务：

```bash
docker compose up --build
```

首次启动会自动执行：

- 基础设施健康检查
- MySQL 表初始化
- Elasticsearch 索引初始化
- ClickHouse 数据库和表初始化
- RabbitMQ 拓扑初始化
- 演示任务初始化

### 10.3 查看服务

启动成功后可访问：

- Gateway: `http://localhost:8000/docs`
- Scheduler: `http://localhost:8001/docs`
- Worker: `http://localhost:8002/docs`
- Search: `http://localhost:8003/docs`
- Mock Source: `http://localhost:8004/docs`
- RabbitMQ 管理台: `http://localhost:15672`
  用户名：`study`
  密码：`study`

## 11. 体验完整链路

### 11.1 查看自动创建的任务

```bash
curl http://localhost:8000/tasks
```

项目启动后会自动创建 3 个演示任务：

- `AI Weekly Signals`
- `Python Service Digest`
- `Data Infra Watch`

### 11.2 手动触发任务

```bash
curl -X POST http://localhost:8000/tasks/1/dispatch
```

观察点：

- Gateway 返回 run id
- RabbitMQ 中消息数量变化
- Worker 开始消费

### 11.3 查看运行记录

```bash
curl http://localhost:8000/runs
```

状态会经历：

- `queued`
- `running`
- `succeeded` 或 `failed`

### 11.4 进行全文搜索

```bash
curl "http://localhost:8003/search?q=agent"
```

再执行一次同样请求，观察 Redis 缓存命中：

- 首次返回 `cached=false`
- 再次请求通常返回 `cached=true`

### 11.5 查看统计分析

```bash
curl "http://localhost:8003/analytics/summary?hours=24"
curl "http://localhost:8003/analytics/trend?hours=24"
```

观察点：

- `total_documents`
- `unique_runs`
- `avg_fetch_latency_ms`
- 每小时趋势变化

## 12. 如何验证每个中间件真的参与了链路

### 12.1 MySQL

执行任务后查看：

- `crawl_tasks`
- `crawl_runs`
- `articles`

### 12.2 Redis

查看键：

- `manual-dispatch:*`
- `schedule-lock:*`
- `article-dedupe:*`
- `search-cache-version`
- `search:v...`

### 12.3 RabbitMQ

查看：

- `crawl.jobs` 队列消息堆积
- consumer 数量
- 消费速率

### 12.4 Elasticsearch

搜索接口有结果时，说明 ES 已经参与索引和检索。

也可以直接请求：

```bash
curl http://localhost:9200/articles/_search
```

### 12.5 ClickHouse

分析接口返回结果时，说明 ClickHouse 已参与写入和聚合查询。

也可以手动执行 SQL：

```sql
SELECT count(*) FROM crawler_analytics.crawl_metrics;
```

## 13. 本项目适合学习的内容

- FastAPI 微服务拆分
- Docker Compose 编排
- MySQL 事务型元数据建模
- Redis 分布式锁、去重、缓存
- RabbitMQ 异步消息解耦
- Elasticsearch 全文搜索
- ClickHouse OLAP 分析
- 调度器与执行器分离
- 多存储分层设计

## 14. 后续可扩展方向

- 增加死信队列和重试队列
- 增加任务优先级
- 增加用户、权限、API Key
- 增加真实网页抓取器
- 增加代理池服务
- 增加前端管理台
- 引入 Alembic 管理数据库迁移
- 为 worker 增加并发执行和失败重试策略

## 15. 相关文档

- 技术知识点整理见 [docs/TECH_NOTES.md](/mnt/c/workspace_2/fast-api-tools-study/docs/TECH_NOTES.md)
