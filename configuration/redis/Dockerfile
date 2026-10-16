FROM redis:7-alpine
# Refresh security fixes even before the upstream Redis image is rebuilt.
RUN apk upgrade --no-cache
LABEL io.marinkino.security.managed="true"
