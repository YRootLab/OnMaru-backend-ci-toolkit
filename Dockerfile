FROM python:3.11-slim AS runtime
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --disable-pip-version-check . \
    && useradd --create-home --uid 10001 toolkit
USER toolkit
ENTRYPOINT ["pipeline-toolkit"]
HEALTHCHECK CMD ["pipeline-toolkit", "version"]
