FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID=
# INTERNAL_API_URL must be present at BUILD time: Next bakes rewrite destinations
# into routes-manifest.json during `next build`. Default targets the compose
# backend service so the /api proxy works inside the container network.
ARG INTERNAL_API_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV INTERNAL_API_URL=$INTERNAL_API_URL

RUN npm run build

EXPOSE 3000

CMD ["npx", "next", "start", "-p", "3000"]
