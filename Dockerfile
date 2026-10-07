FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV BTC_DASHBOARD_HOST=0.0.0.0 BTC_DASHBOARD_PORT=8790
EXPOSE 8790
CMD ["python","dashboard_server.py"]
