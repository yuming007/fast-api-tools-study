# 技术知识点整理

本文档帮助你结合当前项目理解各个技术在真实链路里的职责。

## 1. FastAPI

- `gateway-service`：接入层
- `scheduler-service`：调度观察与手动触发
- `worker-service`：Celery worker 观察面
- `search-service`：查询层
- `mock-source-service`：模拟数据源

重点：

- `lifespan`
- `Depends(get_db)`
- `AsyncSession`
- Pydantic 模型分离请求/响应

## 2. MySQL

职责：

- 保存任务定义
- 保存运行记录
- 保存文章元数据

最佳实践点：

- `asyncmy`
- `SQLAlchemy AsyncEngine`
- `AsyncSession`
- 每请求一个独立 session

## 3. Redis

当前项目已切到 `redis.asyncio`。

职责：

- 分布式锁
- 文章去重
- 搜索缓存
- Celery result backend
- worker/scheduler 状态存储

重点：

- 带 token 的锁
- Lua 安全解锁
- 命名空间 key
- 细粒度缓存版本失效
- 缓存重建锁防击穿
- TTL 抖动降低雪崩风险

## 4. Celery

当前项目已正式接入 Celery。

职责：

- `celery-worker` 执行抓取任务
- `celery-beat` 触发调度扫描
- `flower` 观察任务执行

重点：

- RabbitMQ 作为 broker
- Redis 作为 result backend
- `task_acks_late=True`
- `worker_prefetch_multiplier=1`
- `autoretry_for + retry_backoff`
- `celery beat` 做周期调度
- `flower` 做可观测性

## 5. RabbitMQ

职责：

- 作为 Celery 的 broker 承载任务消息

重点：

- queue / exchange / routing key
- durable queue
- Celery 与 RabbitMQ 的协作关系

## 6. Elasticsearch

职责：

- 保存全文索引
- 提供标题/摘要/正文搜索
- 返回高亮片段

重点：

- 多字段检索
- 倒排索引
- 高亮

## 7. ClickHouse

职责：

- 保存分析事件
- 支持趋势和汇总查询

重点：

- `MergeTree`
- 按天分区
- 批量插入
- 聚合查询

## 8. 当前架构思路

写路径：

- `gateway/scheduler -> Celery -> RabbitMQ -> celery-worker -> MySQL/ES/ClickHouse/Redis`

读路径：

- `search-service -> Redis/ES/ClickHouse`

控制面：

- 任务创建
- 调度观察
- worker 观察

执行面：

- Celery worker
- 抓取
- 写入多存储

补充：

- `search-service` 内部对同步 ES/ClickHouse 客户端做了 `asyncio.to_thread` 包装，避免直接阻塞 FastAPI 事件循环
- `gateway-service` 和 `scheduler-service` 对 Celery broker 投递同样做了线程化包装
