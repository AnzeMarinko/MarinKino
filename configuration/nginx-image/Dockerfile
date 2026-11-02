FROM nginx:stable-alpine
# Refresh security fixes even before the upstream nginx image is rebuilt.
RUN apk upgrade --no-cache
LABEL io.marinkino.security.managed="true"
