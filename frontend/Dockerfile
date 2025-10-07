# Use Node.js
FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json first for caching
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy all project files
COPY . .

# Expose port
EXPOSE 3000

# Increase Node memory for large builds
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Use polling for file watching (helpful for Docker on macOS)
ENV CHOKIDAR_USEPOLLING=true

# Start the React app
CMD ["npm", "start"]
