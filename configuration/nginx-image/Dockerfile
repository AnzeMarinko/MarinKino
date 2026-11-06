ARG APP_IMAGE=marinkino-app:current
FROM ${APP_IMAGE} AS application
FROM nginx:stable-alpine
# Refresh security fixes even before the upstream nginx image is rebuilt.
RUN apk upgrade --no-cache
LABEL io.marinkino.security.managed="true"
# Assets and their content-addressed release come from the exact app image.
COPY --from=application /app/src/static /usr/share/nginx/html/static
