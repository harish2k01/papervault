FROM node:22-alpine AS build

WORKDIR /app
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY apps/web/package*.json ./
RUN npm ci

COPY apps/web ./
RUN npm run build

FROM nginx:1.27-alpine

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

RUN addgroup -S -g 10001 papervault \
    && adduser -S -D -H -u 10001 -G papervault papervault \
    && chown -R 10001:10001 /var/cache/nginx /var/log/nginx /var/run /etc/nginx/conf.d /usr/share/nginx/html

USER 10001:10001

EXPOSE 8080
