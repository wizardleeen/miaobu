FROM node:20-alpine

WORKDIR /app

# Use Chinese mirrors for faster package downloads
RUN npm config set registry https://registry.npmmirror.com

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

# Expose port
EXPOSE 5173

# Default command (can be overridden in docker-compose)
CMD ["npm", "run", "dev"]
