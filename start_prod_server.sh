gunicorn \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --bind '0.0.0.0:8000' \
    --forwarded-allow-ips '*' \
    --access-logfile '-' \
    --access-logformat '%(r)s %(s)s' \
    --timeout 0 \
    --preload \
    api.main:app