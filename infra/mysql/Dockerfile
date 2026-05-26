FROM mysql:8.4

# 自定义字符集和连接设置，方便本地实验时直接可用。
COPY my.cnf /etc/mysql/conf.d/z-study.cnf

# 初始化脚本只会在全新数据目录首次启动时执行。
COPY init/ /docker-entrypoint-initdb.d/
