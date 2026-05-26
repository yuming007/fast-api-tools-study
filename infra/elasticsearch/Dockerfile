FROM docker.elastic.co/elasticsearch/elasticsearch:8.15.2

# 这是面向本地学习的单节点配置，不适合直接用于生产。
COPY --chown=elasticsearch:root elasticsearch.yml /usr/share/elasticsearch/config/elasticsearch.yml
