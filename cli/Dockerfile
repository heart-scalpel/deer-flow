FROM public-docker-remote.artnj.zte.com.cn/library/python:latest
COPY backend/packages/harness /harness
RUN pip install --no-cache-dir -e /harness -i https://artsz.zte.com.cn/artifactory/api/pypi/public-pypi-virtual/simple

ENV TIKTOKEN_CACHE_DIR=/deer-flow/cli/token_cache

CMD ["tail", "-f", "/dev/null"]