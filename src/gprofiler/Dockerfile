FROM node:20.19 AS frontend_dependencies

ARG VITE_PRODUCTION_ENV
ARG VITE_SERVER_HOST

ENV VITE_PRODUCTION_ENV=$VITE_PRODUCTION_ENV
ENV VITE_SERVER_HOST=$VITE_SERVER_HOST

WORKDIR /frontend
COPY gprofiler/frontend/package.json /frontend/
COPY gprofiler/frontend/yarn.lock /frontend/
RUN yarn --cwd /frontend/ install

COPY gprofiler/frontend /frontend
RUN yarn build

FROM python:3.12.3-bullseye

WORKDIR /usr/src/app
EXPOSE 80
CMD ["./run.sh"]

# These commands install nginx v1.23.2, based on official nginx docs:
# https://docs.nginx.com/nginx/admin-guide/installing-nginx/installing-nginx-open-source/#installing-prebuilt-debian-packages
COPY gprofiler/nginx/nginx_signing.key nginx_signing.key
RUN gpg --no-default-keyring --keyring ./temp-keyring.gpg --import nginx_signing.key
RUN gpg --no-default-keyring --keyring ./temp-keyring.gpg --export --output nginx_signing.gpg
RUN rm -f temp-keyring.gpg
RUN mkdir -p /etc/apt/keyrings/
RUN cp nginx_signing.gpg /etc/apt/keyrings/
RUN echo "deb [signed-by=/etc/apt/keyrings/nginx_signing.gpg] https://nginx.org/packages/mainline/debian/ bullseye nginx" >> /etc/apt/sources.list
RUN echo "deb-src [signed-by=/etc/apt/keyrings/nginx_signing.gpg] https://nginx.org/packages/mainline/debian bullseye nginx" >> /etc/apt/sources.list

# install dependencies
RUN apt-get update && apt-get install -y nginx bc logrotate && \
    mkdir /tmp/nginx/

RUN git clone 'https://github.com/Granulate/FlameGraph' -b granulate-master --depth=1 && chmod +x FlameGraph/flamegraph.pl


# copy minimum requirements for pip
COPY gprofiler-dev/requirements.txt gprofiler-dev/requirements.txt
COPY gprofiler-dev/postgres_requirements.txt gprofiler-dev/postgres_requirements.txt
COPY gprofiler-dev/setup.py gprofiler-dev/setup.py
COPY gprofiler/requirements.txt requirements.txt
COPY gprofiler/setup.py setup.py

# run pip
RUN pip install -e ./gprofiler-dev[postgres] && \
    pip install -e .

# copy all files
COPY gprofiler-dev gprofiler-dev
COPY gprofiler/nginx/nginx.conf /etc/nginx/nginx.conf
COPY gprofiler/run.sh run.sh
COPY --from=frontend_dependencies /frontend/build frontend
COPY gprofiler/backend backend
COPY gprofiler/nginx/logrotate.conf /etc/nginx/logrotate.conf

RUN useradd -m -s /bin/bash -u 888 non_root && \
    chown -R non_root:non_root /usr/src/app && \
    chown -R non_root:non_root /etc/nginx && \
    chown -R non_root:non_root /var/cache/nginx && \
    chown -R non_root:non_root /var/log/nginx && \
    chown -R non_root:non_root /tmp/nginx && \
    chown -R non_root:non_root /var/run && \
    chown -R non_root:non_root /run && \
    chown -R non_root:non_root /var/lib/logrotate

USER non_root

# run logrotate
RUN logrotate /etc/nginx/logrotate.conf

# finally, always(!) update external files
# https://github.com/instrumenta/kubeval use this source to retrieve schema
RUN mkdir backend/utils/daemonset_files && \
    curl -f "https://kubernetesjsonschema.dev/master/daemonsetspec.json" -o "backend/utils/daemonset_files/daemonsetspec.json" && \
    curl -Lf "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/k8s/gprofiler.yaml" -o "backend/utils/daemonset_files/daemonset.yml"

RUN mkdir backend/utils/ecs_files && \
    curl -Lf "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/ecs/gprofiler_task_definition.json" -o "backend/utils/ecs_files/task_definition.json"

RUN mkdir backend/utils/ansible_files && \
    curl -Lf "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/ansible/gprofiler_playbook.yml" -o "backend/utils/ansible_files/gprofiler_playbook.yml"

RUN mkdir backend/utils/docker_compose_files && \
    curl -Lf "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/docker-compose/docker-compose.yml" -o "backend/utils/docker_compose_files/docker-compose.yml"
