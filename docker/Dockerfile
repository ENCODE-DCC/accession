FROM ubuntu:bionic@sha256:04d48df82c938587820d7b6006f5071dbbffceb7ca01d2814f81857c631d44df

LABEL maintainer="paulsud@stanford.edu"

WORKDIR /build

ARG ENCODED_RELEASE_TAG

ENV ES_JAVA_OPTS -Xms2g -Xmx2g
ENV JAVA_HOME /usr/lib/jvm/java-11-openjdk-amd64
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y apt-transport-https software-properties-common curl && \
    curl -s https://artifacts.elastic.co/GPG-KEY-elasticsearch | apt-key add - && \
    echo "deb https://artifacts.elastic.co/packages/5.x/apt stable main" | tee -a /etc/apt/sources.list.d/elastic-5.x.list && \
    curl -sSL https://deb.nodesource.com/gpgkey/nodesource.gpg.key | apt-key add - && \
    curl -sL https://deb.nodesource.com/setup_10.x | bash - && \
    add-apt-repository -y ppa:openjdk-r/ppa

# libjpeg8-dev and zlib1g-dev needed for Pillow
# https://stackoverflow.com/a/34631976
RUN apt-get update && apt-get install -y \
    bsdtar \
    elasticsearch \
    git \
    graphviz \
    libjpeg8-dev \
    libpq-dev \
    nginx \
    nodejs \
    openjdk-11-jdk \
    postgresql-10 \
    python3-dev \
    python3-pip \
    redis-server \
    zlib1g-dev \
&& rm -rf /var/lib/apt/lists/*

# Shouldn't be an issue if we run the container as root?
ENV PATH=/usr/share/elasticsearch/bin:/usr/lib/postgresql/10/bin:$PATH

# Fix terminal encoding issues that cause buildout to fail
# https://stackoverflow.com/a/56108986
ENV LC_ALL=C.UTF-8

RUN adduser --system encoded && chown -R encoded /etc/elasticsearch

RUN alias python=python3

RUN git clone https://github.com/ENCODE-DCC/encoded.git --branch "${ENCODED_RELEASE_TAG}" --single-branch && \
    cd encoded && \
    pip3 install --upgrade pip setuptools && \
    pip3 install zc.buildout && \
    buildout bootstrap && \
    bin/buildout

# encoded users needs write permission to be able to make ES scripts
# nginx runs with encoded user, need permissions to various folders
RUN chown -R encoded ./encoded /var/log/nginx /var/lib/nginx /run

WORKDIR /build/encoded

ENV NGINX_CONF develop/snovault/src/snovault

RUN rm "$NGINX_CONF/nginx-dev.conf"

COPY docker/nginx-dev.conf "$NGINX_CONF"

# Add app script to container to run multiple services
# See https://docs.docker.com/config/containers/multi-service_container/
ENV LOCAL_APP local_app.sh

COPY docker/$LOCAL_APP $LOCAL_APP

# Replace the encoded inserts with the accession ones, except for the access keys
ENV INSERTS_DIR src/encoded/tests/data/inserts

RUN find ${INSERTS_DIR} -mindepth 1 -maxdepth 1 | grep -v "access_key.json" | xargs rm

COPY tests/data/inserts ${INSERTS_DIR}

# Delete the line in the base.ini that specifies a specific aws config profile
RUN LINENO=$(grep -n file_upload_profile_name base.ini | cut -f 1 -d :) && sed -i "${LINENO}d" base.ini

# Delete the line in the development.ini (testing = true) that creates testing-only
# schemas that confuse encode utils
RUN LINENO=$(grep -n "testing = true" development.ini | cut -f 1 -d :) && sed -i "${LINENO}d" development.ini

# Don't try to connect to s3 when posting files by deleting the body of file.py create()
# START indicates the line of the function definition, we don't want to delete that. END
# is an offset relative to START. START + END - 1 would yield the line of the return
# statement, but we want to keep the return so we subtract two instead.
RUN START=$(grep -n "def create" src/encoded/types/file.py | cut -f 1 -d :) && \
    END=$(tail -n +${START} src/encoded/types/file.py | grep -n "return" | head -n 1 | cut -f 1 -d :) && \
    sed -i "$((START + 1)),$((START + END - 2))d" src/encoded/types/file.py

# Fix permissions of added files
RUN chown encoded "$NGINX_CONF/nginx-dev.conf" $LOCAL_APP && chmod +x $LOCAL_APP

# Expose the nginx proxy for the local app
EXPOSE 8000

# Make sure to run the app as encoded user
USER encoded

# Run the local app script by default
CMD ./$LOCAL_APP
