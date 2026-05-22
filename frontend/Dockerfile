FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src

EXPOSE 5173

CMD ["npm", "run", "dev"]
