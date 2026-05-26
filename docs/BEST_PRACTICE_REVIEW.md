# 最佳实践评估

这份文档关注的是“当前项目实现离生产级最佳实践还有多远”，不是否定当前代码。当前仓库定位是学习项目，所以有些做法是刻意简化过的，适合入门，但不应该直接搬去生产环境。

## 1. 总结

结论先说：

- `FastAPI + MySQL(asyncmy + AsyncSession)`：方向正确，已经接近最佳实践基线。
- `Redis`：已经切到 `redis.asyncio`，锁和缓存策略比之前成熟不少，但还没到生产级。
- `RabbitMQ`：当前主要作为 Celery broker 使用，职责比之前更清晰，但可靠性策略仍可继续加强。
- `ClickHouse`：表引擎和批量写入思路是对的，但建模和查询形态还比较初级。
- `Elasticsearch`：能工作，但索引策略、写入刷新策略和安全配置都偏“本地学习版”。
- `Celery`：已经接入并承担异步执行与调度扫描，是当前异步任务体系的核心。

## 2. FastAPI + MySQL

当前状态：

- 已使用 `asyncmy`
- 已使用 `SQLAlchemy AsyncEngine + AsyncSession`
- 已有连接池参数
- 已用 `Depends(get_db)` 做依赖注入

这部分是当前项目里最接近最佳实践的一块。

还差什么：

- 没有引入 `Alembic` 做迁移管理
- 没有把事务边界进一步细化到 service 层
- 任务写库和 RabbitMQ 发消息之间没有 outbox 模式，不能保证绝对一致性

结论：

- 学习项目：合格
- 生产项目：建议补 `Alembic + outbox + 更明确的事务边界`

## 3. Redis

当前做法：

- `study:lock:manual-dispatch:*` 用作接口防抖锁
- `study:lock:schedule:*` 用作调度分布式锁
- `study:dedupe:article:*` 用作文章去重
- `study:search:cache:*` 用作搜索缓存
- `study:lock:search-cache-rebuild:*` 用作缓存重建锁

优点：

- 这些都是 Redis 很典型的使用场景
- `SET key value EX ttl NX` 选型方向是对的
- 已经切到 `redis.asyncio`，不会在 FastAPI 请求里继续使用同步 Redis 客户端
- 锁已经带唯一 token，并使用 Lua 做安全释放
- 搜索缓存已经支持按全局、topic、source 三个层级做版本失效

问题：

- 搜索缓存还是“缓存 aside”模型，没有引入更完整的热点 key 监控或预热策略
- 去重 key 仍然只靠 TTL 控制，跨更长时间窗口时会重新接收旧数据
- 还没有基于业务事件总线做主动失效，当前仍是版本号推进方案
- worker/scheduler 的状态统计还是轻量 hash 结构，没有时序化指标体系

结论：

- 学习 Redis 基础能力：是好例子
- 生产最佳实践：还不够

建议：

- 当前已经补了 `redis.asyncio + token 锁 + Lua 解锁`
- 如果继续提升，可以补“逻辑过期 + 后台刷新”或“热点缓存预热”
- 如果继续提升，可以把 worker 指标接到 Prometheus，而不是只放 Redis hash

## 4. RabbitMQ

当前做法：

- RabbitMQ 作为 Celery broker
- 通过 bootstrap 阶段预先声明 exchange / queue / routing key
- 任务执行和调度扫描使用不同队列

这些都是正确方向。

但当前实现离最佳实践还有明显距离：

- 没有开启 publisher confirms
- 没有展示 dead letter / retry queue 这类 RabbitMQ 进阶能力
- 业务代码不再直接使用 `pika` 消费，但也就少了对 ack/nack 细节的显式学习
- 还没有按任务类型做更复杂的优先级队列治理

结论：

- 学习消息队列基本概念：可以
- 学习“Celery 基于 RabbitMQ 的任务分发”：可以
- 学习“RabbitMQ 原生可靠消息投递细节”：还不够

建议：

- 如果要深入 RabbitMQ，本项目可以再加 DLX、TTL retry queue、优先级队列
- 如果要深入消息一致性，可以再加 outbox / publisher confirm

## 5. Celery

当前仓库已经接入 Celery。

当前形态是：

- `FastAPI + Celery + RabbitMQ + Redis`

已经具备的点：

- RabbitMQ 作为 broker
- Redis 作为 result backend
- `task_acks_late = True`
- `worker_prefetch_multiplier = 1`
- `autoretry_for`
- `retry_backoff`
- `celery beat`
- `flower`
- worker 与 scheduler 队列拆分
- API 层手动触发和定时调度统一复用 Celery 任务

还不够的点：

- 还没有针对业务错误与系统错误做更细粒度的重试策略区分
- 还没有 task chain / chord / group 这类高级工作流
- 还没有独立的 dead letter 策略展示
- 还没有对长任务做幂等恢复与中断续跑设计

如果你要继续深入学习 Celery，建议关注这些点：

- `broker_url` 指向 RabbitMQ
- `acks_late = True`
- `worker_prefetch_multiplier = 1`
- `autoretry_for` / `retry_backoff`
- `task_routes`
- `celery beat`

## 6. ClickHouse

当前做法：

- 使用 `MergeTree`
- 按天分区
- 采用批量 insert
- 用它存分析事件而不是业务主表

这些方向是正确的。

但还不是最佳实践：

- `ORDER BY (task_id, run_id, event_time)` 更偏写入顺序，不完全贴合查询形态
- 没有 TTL
- 没有物化视图或预聚合
- 没有控制批量大小和 flush 策略
- 在 FastAPI 中调用的是同步客户端

结论：

- 学习 ClickHouse 基础用法：可以
- 生产分析系统：还偏初级

建议：

- 根据查询模式重新设计主键和排序键
- 如果趋势查询是核心，考虑物化视图
- 增加 TTL 管理历史数据

## 7. Elasticsearch

当前做法：

- 用单独索引保存全文正文
- 支持标题、摘要、正文联合搜索
- 返回高亮结果

方向是对的，但还比较基础：

- 没有自定义 analyzer
- 没有索引模板 / alias / rollover / ILM
- `helpers.bulk(..., refresh=True)` 每批都 refresh，吞吐会明显下降
- 本地镜像关闭了安全认证，只适合学习环境

结论：

- 学习全文检索入门：够用
- 生产最佳实践：不够

建议：

- 把 `refresh=True` 改成批量写入后按需刷新
- 引入 alias 和索引生命周期策略
- 针对中英文内容分别设计 analyzer

## 8. Scheduler

当前做法：

- `Celery Beat`
- 调度扫描任务
- Redis 锁防重

这套做法比进程内定时器方案更接近分布式任务体系的最佳实践。

结论：

- 学习调度器原理：可以
- 生产级分布式调度：一般

建议：

- 如果你想继续深入，可以补更复杂的任务编排、失败补偿和调度审计

## 9. Docker / 基础设施镜像

当前主 `docker-compose.yml` 使用官方镜像直接起服务，这是非常常见、也完全合理的学习方式。

如果你是为了：

- 学习服务启动参数
- 学习配置文件挂载
- 单独逐个起服务做实验

那么单独写 `infra/*/Dockerfile` 是合理的。

但要注意：

- 对 MySQL / Redis / RabbitMQ / ClickHouse / Elasticsearch 来说，“单独 Dockerfile”不代表它比官方镜像更先进
- 真正的最佳实践重点在“配置管理、数据卷、资源限制、监控、备份、权限”，而不是“是否自己包了一层 Dockerfile”
