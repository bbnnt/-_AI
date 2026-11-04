# 知途 · AI 出行与消费性价比决策 Agent —— DevCloud 部署镜像
# DevCloud 预处理器会自动将基础镜像替换为京东内部镜像源，无需手动配置
FROM python:3.11-slim

WORKDIR /app

# 先拷贝依赖清单并安装（利用 Docker 层缓存：代码变动不重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷贝业务代码（.dockerignore 已排除 .env / .venv / __pycache__ 等）
COPY . .

# DevCloud 平台规则：仅路由容器 8080 端口，必须绑定 0.0.0.0
EXPOSE 8080

# 生产 WSGI 服务器：gunicorn
# --timeout 120：大模型推理 + 联网搜索可能耗时较长，默认 30s 会误杀 worker
# shell 形式 + ${PORT:-8080}：Render 注入 PORT 变量时自动适配；DevCloud 无 PORT 时默认 8080
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 app:app