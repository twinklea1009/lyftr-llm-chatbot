.PHONY: up down restart logs build test clean

# Start both backend and frontend services using Docker Compose
up:
	docker compose up --build -d

# Stop all running containers
down:
	docker compose down

# Restart all services
restart:
	docker compose restart

# Follow logs of all containers
logs:
	docker compose logs -f

# Build images without starting
build:
	docker compose build

# Run backend unit and integration tests locally
test:
	cd backend && python3 -m pytest -v

# Stop and remove containers, networks, and named volume
clean:
	docker compose down -v
