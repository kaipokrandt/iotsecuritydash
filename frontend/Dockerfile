# Use Node.js base image
FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy dependency manifests
COPY package*.json ./

# Install dependencies (using npm ci for reproducibility)
RUN npm install

# Copy environment and source files
COPY . .

# 🧩 Pass build-time environment variables from docker-compose
ARG REACT_APP_API_URL
ARG REACT_APP_WS_URL
ARG REACT_APP_WS_TOKEN

# ✅ Explicitly expose them so Create React App can see them
ENV REACT_APP_API_URL=${REACT_APP_API_URL}
ENV REACT_APP_WS_URL=${REACT_APP_WS_URL}
ENV REACT_APP_WS_TOKEN=${REACT_APP_WS_TOKEN}

# Expose the frontend port
EXPOSE 3000

# Increase memory limit for large builds
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Enable polling (for macOS Docker)
ENV CHOKIDAR_USEPOLLING=true

# Start the React development server
CMD ["npm", "start"]
