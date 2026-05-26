FROM clickhouse/clickhouse-server:24.8

# 打开外部访问，并保留最小化配置，方便本地直接连接。
COPY config.d/01-listen.xml /etc/clickhouse-server/config.d/01-listen.xml
