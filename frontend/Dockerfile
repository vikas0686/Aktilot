FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
ARG VITE_API_URL=http://backend:8000
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_CHAT_MODEL=gpt-4o-mini
ENV VITE_CHAT_MODEL=$VITE_CHAT_MODEL
ARG VITE_EMBEDDING_MODEL=text-embedding-3-small
ENV VITE_EMBEDDING_MODEL=$VITE_EMBEDDING_MODEL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
