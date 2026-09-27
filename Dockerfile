# Merkel 焓差法冷却塔核算服务 —— 一键构建镜像
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# 先装依赖（利用层缓存）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再拷应用代码
COPY app ./app

# 非 root 运行
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

# 容器一起来 Merkel 核算接口即可对外应答
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
