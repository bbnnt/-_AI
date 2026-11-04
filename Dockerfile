# 知途 · AI 出行与消费性价比决策 Agent —— DevCloud 部署镜像
# 基础镜像用 DockerHub 原名即可，DevCloud 预处理器会自动替换为京东内部镜像源
# 预处理器还会自动注入阿里云 pip/apt 镜像，无需手动配置
FROM python:3.11-slim

# 生产环境 Python 最佳实践：
# PYTHONDONTWRITEBYTECODE：不生成 .pyc，减小镜像体积
# PYTHONUNBUFFERED：日志实时输出到 stdout，DevCloud 才能收集容器日志
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先拷贝依赖清单并安装（利用 Docker 层缓存：代码变动不重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷贝业务代码（.dockerignore 已排除 .env / .venv / __pycache__ 等）
COPY . .

# DevCloud 平台硬性规则：仅路由容器 8080 端口，必须绑定 0.0.0.0
EXPOSE 8080

# 生产 WSGI 服务器：gunicorn
# --workers 2 --threads 4：大模型调用是 IO 密集型，线程提升并发吞吐
# --timeout 120：大模型推理 + 联网搜索可能耗时较长，默认 30s 会误杀 worker
# --access-logfile - --error-logfile -：日志输出到 stdout/stderr 供平台收集
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]