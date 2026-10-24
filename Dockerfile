FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

COPY requirements/ requirements/

RUN pip install --no-cache-dir -r requirements/prod.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

COPY --chown=app:app . .
RUN mkdir -p /app/media /app/staticfiles && chown app:app /app/media /app/staticfiles
USER app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]

FROM runtime AS development
USER root
RUN pip install --no-cache-dir -r requirements/dev.txt
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings.dev
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM runtime AS production
