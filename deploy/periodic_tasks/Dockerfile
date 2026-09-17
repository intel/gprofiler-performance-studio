FROM alpine:3.18.5

RUN apk add --no-cache dcron wget rsync ca-certificates postgresql-client logrotate sudo

COPY crontab /etc/cron.d/my-cron-job
COPY aggregations.sh /aggregations.sh
COPY refresh_workload_snapshot.sh /refresh_workload_snapshot.sh
COPY logrotate_conf.sh /logrotate_conf.sh


RUN chmod +x /logrotate_conf.sh
RUN chmod 0644 /etc/cron.d/my-cron-job
RUN chmod +x /aggregations.sh
RUN chmod +x /refresh_workload_snapshot.sh


RUN crontab /etc/cron.d/my-cron-job

RUN mkdir -p /var/log/cron && touch /var/log/cron/cron.log

RUN addgroup -S non_root && adduser -S -G non_root -u 888 non_root && \
    chown -R non_root:non_root /aggregations.sh && \
    chown -R non_root:non_root /refresh_workload_snapshot.sh && \
    chown -R non_root:non_root /logrotate_conf.sh && \
    chown -R non_root:non_root /etc/logrotate.conf && \
    chown -R non_root:non_root /etc/cron.d/my-cron-job && \
    chown -R non_root:non_root /var/log/cron

RUN echo "non_root ALL=(ALL) NOPASSWD: $(which crond)" >> /etc/sudoers

USER non_root

# cron jobs do not inherit the container env, so psql couldn't find PGHOST/etc.
# Persist the runtime env to a file that the cron scripts load on each run.
# touch cron.log at runtime: a bind mount over /var/log/cron hides the build-time file.
CMD printenv > /tmp/cron.env && /logrotate_conf.sh && sudo crond && touch /var/log/cron/cron.log && tail -f /var/log/cron/cron.log
