# СТАДИЯ 1: Сборка Angular
FROM node:24-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install --force

COPY . .
RUN npm run build -- --configuration production

# СТАДИЯ 2: Запуск через Nginx
FROM nginx:alpine

# Копируем собранные файлы (в новых версиях Angular папка называется browser)
COPY --from=build /app/dist/The-hydrogen-pinch/browser /usr/share/nginx/html

# Подключаем свой конфиг Nginx с проксированием API
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]