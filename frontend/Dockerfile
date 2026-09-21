# ---- build the React app ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- serve it with nginx, proxying /api to the backend ----
FROM nginx:1.27-alpine
# the nginx image runs envsubst over /etc/nginx/templates/*.template at start-up
ENV API_UPSTREAM=http://127.0.0.1:8000 UI_PORT=8081
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8081
